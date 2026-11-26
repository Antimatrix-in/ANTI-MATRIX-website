"""
Anti-Matrix — Recruitment Status Email Notification Service
===========================================================
Dispatches automatic status-change emails to candidates when an administrator
updates their recruitment pipeline stage.

Supported triggers:
  Applied → Under Review  →  event: candidate_under_review
  Any     → Shortlisted   →  event: candidate_shortlisted
  Any     → Rejected      →  event: candidate_rejected

Design principles:
- Non-fatal: email failures never roll back or block the status change.
- Idempotent: a SENT EmailLog entry for the same (reference_id, event_key) prevents duplicate sends.
- Template-driven: body/subject always read from admin-editable EmailTemplate records.
- Logged: every attempt (success or failure) is recorded in EmailLog.
"""

from datetime import datetime, timezone
from flask import current_app
from models import db, EmailTemplateMapping, EmailLog


# =====================================================================
# STATUS → EVENT KEY MAPPING
# =====================================================================

# Only these status transitions should trigger an automatic notification.
# 'Applied' has no trigger (the acknowledgment email handles that separately).
STATUS_TO_EVENT_KEY = {
    'Under Review': 'candidate_under_review',
    'Shortlisted':  'candidate_shortlisted',
    'Rejected':     'candidate_rejected',
}


# =====================================================================
# PLACEHOLDER RENDERING
# =====================================================================

def _render_template(text, application):
    """
    Replace {{placeholder}} tokens in a template body or subject with
    real candidate/application data.

    Supported placeholders:
      {{candidate_name}}    — application.full_name
      {{job_title}}         — application.job.title (or job_title field)
      {{application_id}}    — application.formatted_code
      {{application_date}}  — formatted created_at date
      {{company_email}}     — static company address
      {{website}}           — static website URL
      {{Student Name}}      — alias for candidate_name (offer letter compat.)
      {{Application ID}}    — alias for application_id
      {{Internship Role}}   — alias for job_title
      {{Company Email}}     — alias for company_email
      {{Website}}           — alias for website
    """
    if not text:
        return text

    # Resolve field values
    candidate_name = (application.full_name or '').strip() or 'Candidate'

    job_title = ''
    if hasattr(application, 'job') and application.job:
        job_title = getattr(application.job, 'title', '') or ''
    if not job_title:
        job_title = getattr(application, 'job_title', '') or ''
    if not job_title:
        job_title = 'the applied position'

    app_id = application.formatted_code or str(application.id)

    app_date = ''
    if application.created_at:
        try:
            app_date = application.created_at.strftime('%d %B %Y')
        except Exception:
            app_date = str(application.created_at)

    company_email = 'info@antimatrix.co.in'
    website = 'https://antimatrix.co.in'

    replacements = {
        '{{candidate_name}}':  candidate_name,
        '{{job_title}}':       job_title,
        '{{application_id}}':  app_id,
        '{{application_date}}': app_date,
        '{{company_email}}':   company_email,
        '{{website}}':         website,
        # Offer-letter style aliases
        '{{Student Name}}':    candidate_name,
        '{{Application ID}}':  app_id,
        '{{Internship Role}}': job_title,
        '{{Company Email}}':   company_email,
        '{{Website}}':         website,
    }

    result = text
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


# =====================================================================
# IDEMPOTENCY CHECK
# =====================================================================

EVENT_LOG_ALIASES = {
    'candidate_under_review': ['candidate_under_review', 'under_review_notification', 'under_review'],
    'candidate_shortlisted':  ['candidate_shortlisted', 'offer_letter', 'shortlisted'],
    'candidate_rejected':     ['candidate_rejected', 'rejection_notification', 'rejected'],
    'candidate_application_submitted': ['application_successful', 'candidate_application_submitted', 'acknowledgment'],
}


def _already_sent(reference_id, event_key):
    """
    Returns True if a SENT EmailLog entry exists for this reference_id and event_key (or its known aliases).
    Uses event_key / template_type in EmailLog to ensure idempotency and prevent duplicates.
    """
    try:
        keys_to_check = EVENT_LOG_ALIASES.get(event_key, [event_key])
        existing = EmailLog.query.filter(
            EmailLog.reference_id == reference_id,
            EmailLog.template_type.in_(keys_to_check),
            EmailLog.status == 'SENT'
        ).first()
        return existing is not None
    except Exception as e:
        if current_app:
            current_app.logger.warning(
                f"[RecruitmentNotification] Could not check idempotency for "
                f"ref={reference_id} event={event_key}: {e}"
            )
        return False  # Safe default: allow the send attempt


# =====================================================================
# EMAIL LOG RECORDING
# =====================================================================

def _record_email_log(application, event_key, subject, body_preview,
                      success, provider_message_id, error_message):
    """
    Record the notification send attempt in EmailLog.
    Non-fatal: any log-write failure is caught and logged to app logger.
    """
    try:
        log_entry = EmailLog(
            recipient_email=application.email,
            template_type=event_key,
            reference_id=application.formatted_code,
            subject=subject or '',
            body_preview=(body_preview or '')[:500],
            status='SENT' if success else 'FAILED',
            provider_message_id=provider_message_id,
            error_message=error_message,
            sent_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        if current_app:
            current_app.logger.error(
                f"[RecruitmentNotification] Failed to record EmailLog for "
                f"app={application.formatted_code} event={event_key}: {e}"
            )


# =====================================================================
# MAIN DISPATCH FUNCTION
# =====================================================================

def send_recruitment_status_email(application, new_status, old_status):
    """
    Dispatch an automatic recruitment status change notification email.

    Called after a successful DB commit of the status change.

    Args:
        application: JobApplication ORM instance (fully loaded).
        new_status:  Normalized status string, e.g. 'Under Review'.
        old_status:  Previous status string before the change.

    Returns:
        (success: bool, message: str)

    Guarantees:
        - Never raises; all exceptions are caught and logged.
        - If the status did not actually change, returns immediately.
        - Duplicate sends are prevented via EmailLog idempotency check.
        - Email failures do not affect the saved status change.
    """
    try:
        # 1. Guard: no status change
        if new_status == old_status:
            return False, "No status change — skipped."

        # 2. Map new_status → event_key
        event_key = STATUS_TO_EVENT_KEY.get(new_status)
        if not event_key:
            return False, f"No email configured for status '{new_status}'."

        # 3. Resolve active template mapping
        mapping = EmailTemplateMapping.query.filter_by(event_key=event_key).first()
        if not mapping:
            msg = (
                f"No EmailTemplateMapping found for event '{event_key}'. "
                f"Configure it in the admin Email Templates panel."
            )
            if current_app:
                current_app.logger.warning(f"[RecruitmentNotification] {msg} app={application.formatted_code}")
            return False, msg

        if not mapping.is_active:
            msg = (
                f"EmailTemplateMapping for event '{event_key}' is inactive. "
                f"Enable it in the admin Email Templates panel to send automatic notifications."
            )
            if current_app:
                current_app.logger.info(f"[RecruitmentNotification] {msg} app={application.formatted_code}")
            return False, msg

        template = mapping.template  # EmailTemplate via relationship
        if not template:
            msg = (
                f"EmailTemplateMapping for event '{event_key}' has no linked template. "
                f"Assign a template in the admin Email Templates panel."
            )
            if current_app:
                current_app.logger.warning(f"[RecruitmentNotification] {msg} app={application.formatted_code}")
            return False, msg

        if not template.is_active:
            msg = f"Email template '{template.name}' (type={template.template_type}) is inactive."
            if current_app:
                current_app.logger.info(f"[RecruitmentNotification] {msg} app={application.formatted_code}")
            return False, msg

        # 4. Idempotency check
        ref_id = application.formatted_code
        if _already_sent(ref_id, event_key):
            msg = (
                f"Notification '{event_key}' already sent for application {ref_id}. "
                f"Skipping duplicate send."
            )
            if current_app:
                current_app.logger.info(f"[RecruitmentNotification] {msg}")
            return False, msg

        # 5. Render subject and body
        rendered_subject = _render_template(template.subject, application)
        rendered_body = _render_template(template.body, application)

        # 6. Send via Brevo
        from services.email_service import send_brevo_email, markdown_to_html_email
        body_html = markdown_to_html_email(rendered_body, title=rendered_subject)

        success, msg, provider_id = send_brevo_email(
            recipient_email=application.email,
            recipient_name=application.full_name or application.email,
            subject=rendered_subject,
            body_text=rendered_body,
            body_html=body_html
        )

        # 7. Record in EmailLog
        _record_email_log(
            application=application,
            event_key=event_key,
            subject=rendered_subject,
            body_preview=rendered_body,
            success=success,
            provider_message_id=provider_id if success else None,
            error_message=None if success else msg
        )

        if success:
            if current_app:
                current_app.logger.info(
                    f"[RecruitmentNotification] '{event_key}' email sent to "
                    f"{application.email} for app {ref_id}. Provider ID: {provider_id}"
                )
            return True, f"Notification email sent to {application.email}."
        else:
            if current_app:
                current_app.logger.error(
                    f"[RecruitmentNotification] Failed to send '{event_key}' email to "
                    f"{application.email} for app {ref_id}: {msg}"
                )
            return False, f"Email delivery failed: {msg}"

    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        if current_app:
            current_app.logger.error(
                f"[RecruitmentNotification] Unexpected error dispatching "
                f"'{new_status}' notification for app "
                f"{getattr(application, 'formatted_code', '?')}: {exc}",
                exc_info=True
            )
        return False, f"Unexpected error: {exc}"


# =====================================================================
# RETRY HELPER (called by admin retry route)
# =====================================================================

# Supported retry event aliases mapping input event keys/slugs to their canonical handler
RETRY_EVENT_HANDLERS = {
    # 1. Application Acknowledgment
    'candidate_application_submitted': 'acknowledgment',
    'application_successful':          'acknowledgment',
    'acknowledgment':                  'acknowledgment',

    # 2. Under Review
    'candidate_under_review':          'Under Review',
    'under_review_notification':       'Under Review',
    'under_review':                    'Under Review',

    # 3. Shortlisted / Offer Letter
    'candidate_shortlisted':           'Shortlisted',
    'offer_letter':                    'Shortlisted',
    'shortlisted':                     'Shortlisted',

    # 4. Rejected
    'candidate_rejected':              'Rejected',
    'rejection_notification':          'Rejected',
    'rejected':                        'Rejected',
}


def retry_recruitment_status_email(application, event_key):
    """
    Retry a previously-failed or pending email notification.
    Preserves audit history of failed attempts in EmailLog while preventing duplicates.

    Supported events:
      - Acknowledgment: 'application_successful', 'candidate_application_submitted'
      - Under Review:   'candidate_under_review', 'under_review_notification'
      - Shortlisted:    'candidate_shortlisted', 'offer_letter'
      - Rejected:       'candidate_rejected', 'rejection_notification'

    Args:
        application: JobApplication ORM instance.
        event_key:   Event key or template slug (e.g. 'application_successful', 'candidate_under_review').

    Returns:
        (success: bool, message: str)
    """
    if not application:
        return False, "Invalid application record."

    clean_key = (event_key or '').strip().lower()
    handler = RETRY_EVENT_HANDLERS.get(clean_key)
    if not handler:
        return False, (
            f"Invalid event key: '{event_key}'. "
            f"Supported events: Acknowledgment (application_successful), "
            f"Under Review (candidate_under_review), Shortlisted (candidate_shortlisted), "
            f"Rejected (candidate_rejected)."
        )

    # Case 1: Acknowledgment Email Retry
    if handler == 'acknowledgment':
        from services.email_service import send_application_successful_email
        # Duplicate check: prevent resending if already successfully sent
        current_st = (application.application_success_email_status or '').strip().upper()
        if current_st == 'SENT':
            return False, "Acknowledgment email has already been sent successfully for this application."

        success, msg = send_application_successful_email(application)
        return success, msg

    # Case 2: Status Notification Retry (Under Review, Shortlisted, Rejected)
    target_status = handler  # 'Under Review', 'Shortlisted', or 'Rejected'
    target_event_key = STATUS_TO_EVENT_KEY.get(target_status)

    # Check if a successful send already exists in EmailLog (Duplicate Prevention)
    if _already_sent(application.formatted_code, target_event_key):
        return False, f"{target_status} notification has already been sent successfully for this application."

    # Call send_recruitment_status_email with old_status='' so status-change guard allows retry
    return send_recruitment_status_email(
        application=application,
        new_status=target_status,
        old_status=''
    )
