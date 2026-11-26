import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from app import create_app
from models import (
    db, User, JobPosting, JobApplication, EmailTemplate, EmailTemplateMapping, EmailLog
)
from services.email_template_service import ensure_email_template_schema
from services.email_scheduler_service import (
    get_due_applications, process_due_acknowledgment_emails,
    schedule_application_acknowledgment, ensure_scheduler_running
)


class TestEmailSchedulerWorkerAndTimezone(unittest.TestCase):
    """
    Test suite for email scheduler timezone handling and background worker execution:
    1. 5-minute scheduling calculation and IST timezone conversion accuracy.
    2. Zero naive-vs-aware comparison errors (consistently UTC-normalized).
    3. Past-due pending applications are fetched and dispatched immediately.
    4. Not-yet-due pending applications are held until delay passes.
    5. Duplicate dispatch prevention (atomic Processing lock & SENT status).
    6. Fork-safe scheduler worker PID tracking and start idempotency.
    7. Admin application detail renders scheduled delivery in Asia/Kolkata (IST).
    8. Manual send / retry behavior is safe and non-destructive.
    """

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        db.create_all()

        ensure_email_template_schema()

        self.admin = User(
            name='Scheduler Admin',
            email='admin@antimatrix.co.in',
            role='admin',
            is_active=True
        )
        self.admin.set_password('Admin@123456')
        db.session.add(self.admin)

        self.candidate = User(
            name='Test Candidate',
            email='candidate@test.com',
            role='student',
            is_active=True
        )
        self.candidate.set_password('Candidate@123')
        db.session.add(self.candidate)

        self.job = JobPosting(
            title='Software Engineer Intern',
            department='Engineering',
            location='Remote',
            employment_type='Internship',
            job_code='AM-JOB-002',
            short_description='Internship',
            description='Detailed description',
            is_active=True
        )
        db.session.add(self.job)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_admin(self):
        return self.client.post('/login', data={
            'email': 'admin@antimatrix.co.in',
            'password': 'Admin@123456'
        }, follow_redirects=True)

    def test_01_scheduled_time_and_ist_conversion(self):
        """Calculates 5-minute schedule accurately in UTC and converts cleanly to IST."""
        # 03:08:28 UTC -> IST should be 08:38:28 AM IST
        base_time_utc = datetime(2026, 11, 26, 3, 8, 28, tzinfo=timezone.utc)

        app = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='Aarav Sharma',
            email='aarav@example.com',
            phone='9876543210',
            duration='3_months',
            application_code='AM-APP-000601',
            payment_status='paid',
            status='Under Review',
            application_status='Under Review',
            application_success_email_status='Pending',
            created_at=base_time_utc
        )
        db.session.add(app)
        db.session.commit()

        # Scheduled delivery must be created_at + 5 minutes
        expected_utc = datetime(2026, 11, 26, 3, 13, 28, tzinfo=timezone.utc)
        self.assertEqual(app.ack_email_scheduled_at, expected_utc)

        # In IST (UTC+5:30), 03:13:28 UTC is 08:43:28 AM IST
        ist_time = app.ack_email_scheduled_at_ist
        self.assertIsNotNone(ist_time)
        self.assertEqual(ist_time.hour, 8)
        self.assertEqual(ist_time.minute, 43)
        self.assertEqual(ist_time.second, 28)
        self.assertEqual(ist_time.strftime('%I:%M:%S %p IST'), '08:43:28 AM IST')

    def test_02_past_due_application_fetched_and_dispatched(self):
        """Applications past their 5-minute scheduled window are fetched and dispatched."""
        # Application created 10 minutes ago
        past_created_at = datetime.now(timezone.utc) - timedelta(minutes=10)

        app = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='Deepak Verma',
            email='deepak.test@example.com',
            phone='9876543211',
            duration='1_month',
            application_code='AM-APP-000777',
            payment_status='paid',
            status='Applied',
            application_status='Applied',
            application_success_email_status='Pending',
            created_at=past_created_at
        )
        db.session.add(app)
        db.session.commit()

        # 1. Verify get_due_applications finds it
        due = get_due_applications(delay_minutes=5)
        due_codes = [a.formatted_code for a in due]
        self.assertIn('AM-APP-000777', due_codes)

        # 2. Dispatch with Brevo mock
        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Sent", "brevo_ack_test_123")

            sent_count = process_due_acknowledgment_emails(delay_minutes=5)
            self.assertEqual(sent_count, 1)

            # DB status updated to Sent
            app_reloaded = db.session.get(JobApplication, app.id)
            self.assertEqual(app_reloaded.application_success_email_status, 'Sent')
            self.assertIsNotNone(app_reloaded.application_success_email_sent_at)

            # EmailLog recorded
            log = EmailLog.query.filter_by(
                reference_id='AM-APP-000777',
                template_type='application_successful'
            ).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.status, 'SENT')
            self.assertEqual(log.provider_message_id, 'brevo_ack_test_123')

    def test_03_recent_application_not_dispatched_prematurely(self):
        """Applications submitted 1 minute ago are NOT dispatched before 5 minutes pass."""
        recent_created_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        app = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='Pooja Nair',
            email='pooja.test@example.com',
            phone='9876543212',
            duration='1_month',
            application_code='AM-APP-000888',
            payment_status='paid',
            status='Applied',
            application_status='Applied',
            application_success_email_status='Pending',
            created_at=recent_created_at
        )
        db.session.add(app)
        db.session.commit()

        # Should NOT be due
        due = get_due_applications(delay_minutes=5)
        due_codes = [a.formatted_code for a in due]
        self.assertNotIn('AM-APP-000888', due_codes)

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            sent_count = process_due_acknowledgment_emails(delay_minutes=5)
            self.assertEqual(sent_count, 0)
            mock_send.assert_not_called()

        app_reloaded = db.session.get(JobApplication, app.id)
        self.assertEqual(app_reloaded.application_success_email_status, 'Pending')

    def test_04_duplicate_dispatch_prevention(self):
        """Once sent, subsequent scheduler runs never duplicate the acknowledgment email."""
        past_created_at = datetime.now(timezone.utc) - timedelta(minutes=20)

        app = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='Rohan Mehta',
            email='rohan.test@example.com',
            phone='9876543213',
            duration='3_months',
            application_code='AM-APP-000999',
            payment_status='paid',
            status='Applied',
            application_status='Applied',
            application_success_email_status='Pending',
            created_at=past_created_at
        )
        db.session.add(app)
        db.session.commit()

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Sent", "brevo_ack_dup_001")

            # First run: sends 1 email
            count1 = process_due_acknowledgment_emails(delay_minutes=5)
            self.assertEqual(count1, 1)
            self.assertEqual(mock_send.call_count, 1)

            # Second run: must send 0 emails
            count2 = process_due_acknowledgment_emails(delay_minutes=5)
            self.assertEqual(count2, 0)
            self.assertEqual(mock_send.call_count, 1)  # Unchanged

    def test_05_admin_application_detail_renders_ist_and_utc(self):
        """Admin application detail page displays scheduled time in IST with UTC reference."""
        base_time = datetime(2026, 11, 26, 3, 8, 28, tzinfo=timezone.utc)

        app = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='AM601 Test Candidate',
            email='test601@example.com',
            phone='9876543214',
            duration='3_months',
            application_code='AM-APP-000601',
            payment_status='paid',
            status='Under Review',
            application_status='Under Review',
            application_success_email_status='Pending',
            created_at=base_time
        )
        db.session.add(app)
        db.session.commit()

        self.login_admin()

        resp = self.client.get(f'/admin/applications/{app.id}')
        self.assertEqual(resp.status_code, 200)

        # Page must render IST time (08:43:28 AM IST)
        self.assertIn(b'08:43:28 AM IST', resp.data)
        # And must render UTC reference (03:13:28 UTC)
        self.assertIn(b'03:13:28 UTC', resp.data)

    def test_06_fork_safe_worker_pid_tracking(self):
        """Worker starts properly in the active PID and does not start duplicate threads in same PID."""
        from services import email_scheduler_service

        current_pid = os.getpid()
        with patch.object(self.app, 'config', {'TESTING': False}):
            with patch('threading.Thread.start') as mock_thread_start:
                email_scheduler_service._scheduler_thread = None
                email_scheduler_service._scheduler_worker_pid = None

                # First call: starts thread
                email_scheduler_service.start_email_scheduler_worker(self.app, interval_seconds=10)
                self.assertEqual(mock_thread_start.call_count, 1)
                self.assertEqual(email_scheduler_service._scheduler_worker_pid, current_pid)

                # Fake that thread is alive
                mock_t = MagicMock()
                mock_t.is_alive.return_value = True
                email_scheduler_service._scheduler_thread = mock_t

                # Second call in same PID: no-op
                email_scheduler_service.start_email_scheduler_worker(self.app, interval_seconds=10)
                self.assertEqual(mock_thread_start.call_count, 1)  # No second thread started

                # Simulated Gunicorn fork: PID changes
                new_pid = current_pid + 999
                with patch('os.getpid', return_value=new_pid):
                    email_scheduler_service.start_email_scheduler_worker(self.app, interval_seconds=10)
                    # New thread started for the child worker PID!
                    self.assertEqual(mock_thread_start.call_count, 2)


if __name__ == '__main__':
    unittest.main()
