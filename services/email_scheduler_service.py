import os
import time
import threading
from datetime import datetime, timezone, timedelta
from flask import current_app
from models import db, JobApplication, EmailTemplate, EmailLog
from services.email_service import (
    render_application_successful_email,
    send_brevo_email,
    DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT,
    DEFAULT_APPLICATION_SUCCESSFUL_BODY
)


def schedule_application_acknowledgment(application, delay_minutes=5):
    """
    Schedules an acknowledgment email for an application.
    Marks status as 'Pending' and ensures persistence in the database.
    Does NOT block the HTTP request or send the email immediately.
    """
    if not application:
        return
    application.application_success_email_status = 'Pending'
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if current_app:
            current_app.logger.warning(f"Could not persist Pending status for app {application.id}: {e}")


def get_due_applications(delay_minutes=None):
    """
    Returns candidate applications whose acknowledgment email is due.
    Checks the configured delay in EmailTemplateMapping if delay_minutes is None.
    Uses UTC consistently for database storage and comparisons.
    Ensures safe, offset-aware UTC datetime comparisons:
    1. application_success_email_status is in ('Pending', 'PENDING', 'Failed', 'FAILED')
    2. ack_email_scheduled_at <= now_utc (guaranteed offset-aware UTC comparison)
    """
    if delay_minutes is None:
        try:
            from models import EmailTemplateMapping
            mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').first()
            if mapping and mapping.delay_minutes is not None:
                delay_minutes = mapping.delay_minutes
            else:
                delay_minutes = 5
        except Exception:
            delay_minutes = 5

    now_utc = datetime.now(timezone.utc)

    # Fetch candidate applications with pending or failed acknowledgment status
    candidates = JobApplication.query.filter(
        JobApplication.application_success_email_status.in_(['Pending', 'PENDING', 'Failed', 'FAILED'])
    ).all()

    due = []
    for app_record in candidates:
        sched = app_record.ack_email_scheduled_at
        if sched and sched <= now_utc:
            due.append(app_record)

    return due


def process_due_acknowledgment_emails(app=None, delay_minutes=None):
    """
    Checks for due acknowledgment emails and sends them.
    Implements:
    - Atomic status transition from 'Pending' -> 'Processing' -> 'Sent' / 'Failed'
    - Concurrency-safety: Prevents duplicate emails across threads or worker instances
    - Respects dynamic delay and template mapping from EmailTemplateMapping
    - Safe retry logic up to 3 attempts
    Returns: count of successfully sent emails.
    """
    if app and not current_app:
        with app.app_context():
            return _execute_email_processing(delay_minutes)
    return _execute_email_processing(delay_minutes)


def _execute_email_processing(delay_minutes=None):
    from models import EmailTemplateMapping

    mapping = None
    try:
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').first()
    except Exception:
        pass

    effective_delay = 5 if delay_minutes is None else delay_minutes
    effective_template_type = 'application_successful'

    if mapping:
        if not mapping.is_active:
            # Automation is disabled by administrator. Do not send automated emails.
            return 0
        if delay_minutes is None and mapping.delay_minutes is not None:
            effective_delay = mapping.delay_minutes
        if not mapping.template or not mapping.template.is_active:
            # Mapped template is missing or inactive. Pause automated dispatch safely.
            if current_app:
                current_app.logger.warning("Application acknowledgment dispatch paused: mapped template is inactive or missing.")
            return 0
        if mapping.template:
            effective_template_type = mapping.template.template_type or 'application_successful'

    # Fetch candidate applications where email is due using normalized UTC comparison
    due_apps = get_due_applications(delay_minutes=effective_delay)
    sent_count = 0

    for app_record in due_apps:
        # Check retry limit: count failed attempts in EmailLog
        app_code = app_record.formatted_code
        failed_attempts = 0
        try:
            failed_attempts = EmailLog.query.filter_by(
                reference_id=app_code,
                status='FAILED'
            ).count()
        except Exception:
            pass

        if failed_attempts >= 3:
            # Reached max retries; do not retry further
            app_record.application_success_email_status = 'Failed_Max_Retries'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            continue

        # Atomic lock: transition status to 'Processing'
        # Ensures that if another thread/worker also queries at the same time, only one wins
        rows_updated = JobApplication.query.filter(
            JobApplication.id == app_record.id,
            JobApplication.application_success_email_status.in_(['Pending', 'PENDING', 'Failed', 'FAILED'])
        ).update({'application_success_email_status': 'Processing'}, synchronize_session=False)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            continue

        if rows_updated == 0:
            # Another worker already claimed this record
            continue

        # Re-fetch instance after atomic lock
        app_instance = db.session.get(JobApplication, app_record.id)
        if not app_instance:
            continue

        recipient_email = (app_instance.email or '').strip()
        if not recipient_email:
            app_instance.application_success_email_status = 'Failed'
            db.session.commit()
            continue

        try:
            rendered = render_application_successful_email(app_instance)
            subject = rendered.get('subject') or DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT
            body_text = rendered.get('body_text') or DEFAULT_APPLICATION_SUCCESSFUL_BODY
            body_html = rendered.get('body_html')

            success, msg, provider_id = send_brevo_email(
                recipient_email=recipient_email,
                recipient_name=app_instance.full_name or recipient_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )

            ts = datetime.now(timezone.utc)
            if success:
                app_instance.application_success_email_status = 'Sent'
                app_instance.application_success_email_sent_at = ts

                # Record in EmailLog
                try:
                    email_log = EmailLog(
                        recipient_email=recipient_email,
                        template_type=effective_template_type,
                        reference_id=app_instance.formatted_code,
                        subject=subject,
                        body_preview=(body_text or '')[:200],
                        status='SENT',
                        provider_message_id=provider_id,
                        sent_at=ts
                    )
                    db.session.add(email_log)
                except Exception:
                    pass

                db.session.commit()
                sent_count += 1
            else:
                app_instance.application_success_email_status = 'Failed'

                # Record failure in EmailLog
                try:
                    email_log = EmailLog(
                        recipient_email=recipient_email,
                        template_type=effective_template_type,
                        reference_id=app_instance.formatted_code,
                        subject=subject,
                        body_preview=(body_text or '')[:200],
                        status='FAILED',
                        error_message=str(msg),
                        sent_at=ts
                    )
                    db.session.add(email_log)
                except Exception:
                    pass

                db.session.commit()

        except Exception as exc:
            db.session.rollback()
            try:
                app_instance.application_success_email_status = 'Failed'
                email_log = EmailLog(
                    recipient_email=recipient_email,
                    template_type='application_successful',
                    reference_id=app_instance.formatted_code,
                    subject='Application Acknowledgment',
                    body_preview='',
                    status='FAILED',
                    error_message=str(exc),
                    sent_at=datetime.now(timezone.utc)
                )
                db.session.add(email_log)
                db.session.commit()
            except Exception:
                db.session.rollback()

    return sent_count


_scheduler_worker_pid = None
_scheduler_thread = None
_scheduler_lock = threading.Lock()


def start_email_scheduler_worker(app=None, interval_seconds=20):
    """
    Fork-safe, multi-worker resilient background email scheduler.
    Spawns a daemon thread in the current OS process if not already running.
    Tracks os.getpid() so if Gunicorn forks worker processes, each worker
    or the active process starts its own worker cleanly without deadlocks.
    """
    global _scheduler_worker_pid, _scheduler_thread

    current_pid = os.getpid()
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive() and _scheduler_worker_pid == current_pid:
            return

        if app and app.config.get('TESTING'):
            return

        _scheduler_worker_pid = current_pid

        def _worker():
            time.sleep(2)  # Brief initial delay
            while True:
                try:
                    if app:
                        with app.app_context():
                            process_due_acknowledgment_emails(app, delay_minutes=5)
                    elif current_app:
                        with current_app.app_context():
                            process_due_acknowledgment_emails(current_app, delay_minutes=5)
                except Exception as e:
                    try:
                        log_obj = app.logger if app else (current_app.logger if current_app else None)
                        if log_obj:
                            log_obj.warning(f"[AckEmailWorker] Background processing note: {e}")
                    except Exception:
                        pass
                time.sleep(interval_seconds)

        _scheduler_thread = threading.Thread(
            target=_worker,
            daemon=True,
            name=f"AntiMatrixAckEmailWorker-{current_pid}"
        )
        _scheduler_thread.start()


def ensure_scheduler_running(app=None):
    """
    Convenience helper to ensure scheduler worker is running in the current process.
    Can be invoked from before_request hooks or request lifecycle handlers.
    """
    try:
        target_app = app or (current_app._get_current_object() if current_app else None)
        if target_app:
            start_email_scheduler_worker(target_app)
    except Exception as e:
        if current_app:
            current_app.logger.warning(f"[SchedulerCheck] Could not verify scheduler: {e}")

