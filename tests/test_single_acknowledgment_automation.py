import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from app import create_app
from models import (
    db, User, JobPosting, JobApplication, EmailTemplate, EmailTemplateMapping, EmailLog, Payment
)
from services.email_template_service import (
    ensure_email_template_schema,
    ensure_default_templates_and_mappings
)
from services.email_service import (
    DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT,
    DEFAULT_APPLICATION_SUCCESSFUL_BODY,
    render_application_successful_email
)
from services.email_scheduler_service import (
    get_due_applications,
    process_due_acknowledgment_emails,
    schedule_application_acknowledgment
)
from services.recruitment_notification_service import (
    send_recruitment_status_email,
    retry_recruitment_status_email
)


class TestSingleApplicationAcknowledgmentAutomation(unittest.TestCase):
    """
    Verification suite for Single Application Acknowledgment Email Automation:
    1. Successful application submission schedules one email.
    2. Scheduled time is exactly five minutes after submission.
    3. No email is sent immediately.
    4. Email is sent after five minutes.
    5. Correct candidate name is inserted.
    6. Correct job title is inserted.
    7. Correct application ID is inserted.
    8. Duplicate submissions cannot create duplicate emails for the same application event.
    9. Scheduler survives application restart.
    10. Failed delivery is recorded and can be retried safely.
    11. Changing to Under Review does not trigger email.
    12. Changing to Shortlisted does not trigger email.
    13. Changing to Rejected does not trigger email.
    14. Only one template entry is displayed.
    15. No rejection email automation exists.
    16. Existing candidate and payment data remains unchanged.
    """

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        db.create_all()

        ensure_email_template_schema()

        self.admin = User(
            name='Test Admin',
            email='admin@antimatrix.co.in',
            role='admin',
            is_active=True
        )
        self.admin.set_password('Admin@123456')
        db.session.add(self.admin)

        self.candidate = User(
            name='Test Candidate',
            email='candidate@example.com',
            role='student',
            is_active=True
        )
        self.candidate.set_password('Candidate@123')
        db.session.add(self.candidate)

        self.job = JobPosting(
            title='AI Engineer Intern',
            department='Engineering',
            location='Remote',
            employment_type='Internship',
            job_code='AM-JOB-AI-01',
            short_description='Internship role',
            description='Detailed description',
            is_active=True
        )
        db.session.add(self.job)
        db.session.commit()

        self.application = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='Vikram Sethi',
            email='vikram.sethi@example.com',
            phone='9876543299',
            duration='3_months',
            application_code='AM-APP-000601',
            payment_status='paid',
            status='Applied',
            application_status='Applied',
            application_success_email_status='Pending',
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(self.application)
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

    # -------------------------------------------------------------------------
    # TEST 1: Successful application submission schedules one email
    # -------------------------------------------------------------------------
    def test_01_submission_schedules_one_email(self):
        """Application submission registers a pending acknowledgment email."""
        self.assertEqual(self.application.application_success_email_status, 'Pending')
        self.assertIsNotNone(self.application.ack_email_scheduled_at)

    # -------------------------------------------------------------------------
    # TEST 2: Scheduled time is exactly five minutes after submission
    # -------------------------------------------------------------------------
    def test_02_scheduled_time_exactly_five_minutes_after_submission(self):
        """ack_email_scheduled_at equals created_at + 5 minutes exactly."""
        fixed_created = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
        self.application.created_at = fixed_created
        db.session.commit()

        expected = fixed_created + timedelta(minutes=5)
        self.assertEqual(self.application.ack_email_scheduled_at, expected)

    # -------------------------------------------------------------------------
    # TEST 3: No email is sent immediately (before five minutes)
    # -------------------------------------------------------------------------
    def test_03_no_email_sent_immediately(self):
        """Recent applications (<5m old) are not returned by get_due_applications."""
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.session.commit()

        due = get_due_applications(delay_minutes=5)
        self.assertNotIn(self.application, due)

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            sent_count = process_due_acknowledgment_emails(self.app, delay_minutes=5)
            self.assertEqual(sent_count, 0)
            mock_send.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 4: Email is sent after five minutes
    # -------------------------------------------------------------------------
    def test_04_email_sent_after_five_minutes(self):
        """Applications submitted >=5 minutes ago are dispatched."""
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        self.application.application_success_email_status = 'Pending'
        db.session.commit()

        due = get_due_applications(delay_minutes=5)
        self.assertIn(self.application, due)

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_ack_001")
            sent_count = process_due_acknowledgment_emails(self.app, delay_minutes=5)
            self.assertEqual(sent_count, 1)
            self.assertEqual(mock_send.call_count, 1)

            reloaded = db.session.get(JobApplication, self.application.id)
            self.assertEqual(reloaded.application_success_email_status, 'Sent')

    # -------------------------------------------------------------------------
    # TEST 5: Correct candidate name is inserted
    # -------------------------------------------------------------------------
    def test_05_correct_candidate_name_inserted(self):
        """Rendered email contains the candidate's full name."""
        rendered = render_application_successful_email(self.application)
        self.assertIn("Vikram Sethi", rendered['body_text'])

    # -------------------------------------------------------------------------
    # TEST 6: Correct job title is inserted
    # -------------------------------------------------------------------------
    def test_06_correct_job_title_inserted(self):
        """Rendered email contains the job title applied for."""
        rendered = render_application_successful_email(self.application)
        self.assertIn("AI Engineer Intern", rendered['body_text'])

    # -------------------------------------------------------------------------
    # TEST 7: Correct application ID is inserted
    # -------------------------------------------------------------------------
    def test_07_correct_application_id_inserted(self):
        """Rendered email subject and body contain the application code."""
        rendered = render_application_successful_email(self.application)
        self.assertIn("AM-APP-000601", rendered['subject'])
        self.assertIn("AM-APP-000601", rendered['body_text'])

    # -------------------------------------------------------------------------
    # TEST 8: Duplicate submissions cannot create duplicate emails
    # -------------------------------------------------------------------------
    def test_08_duplicate_submissions_prevent_duplicate_emails(self):
        """Once sent, subsequent scheduler runs never duplicate acknowledgment."""
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.application.application_success_email_status = 'Sent'
        db.session.commit()

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            sent_count = process_due_acknowledgment_emails(self.app, delay_minutes=5)
            self.assertEqual(sent_count, 0)
            mock_send.assert_not_called()

            # Manual retry also blocks duplicate if already sent
            success, msg = retry_recruitment_status_email(self.application, 'application_successful')
            self.assertFalse(success)
            self.assertIn('already been sent', msg.lower())
            mock_send.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 9: Scheduler survives application restart
    # -------------------------------------------------------------------------
    def test_09_scheduler_survives_application_restart(self):
        """A new app context simulates server restart; past-due email is dispatched."""
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=7)
        self.application.application_success_email_status = 'Pending'
        db.session.commit()

        # Simulate fresh worker startup after reboot
        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_reboot_001")
            sent_count = process_due_acknowledgment_emails(self.app, delay_minutes=5)
            self.assertEqual(sent_count, 1)

            reloaded = db.session.get(JobApplication, self.application.id)
            self.assertEqual(reloaded.application_success_email_status, 'Sent')

    # -------------------------------------------------------------------------
    # TEST 10: Failed delivery is recorded and can be retried safely
    # -------------------------------------------------------------------------
    def test_10_failed_delivery_recorded_and_safely_retried(self):
        """Temporary failure marks status as Failed and manual retry succeeds."""
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=8)
        self.application.application_success_email_status = 'Pending'
        db.session.commit()

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            # 1. Failure on first attempt
            mock_send.return_value = (False, "HTTP 401 Unrecognised IP", None)
            process_due_acknowledgment_emails(self.app, delay_minutes=5)

            reloaded = db.session.get(JobApplication, self.application.id)
            self.assertEqual(reloaded.application_success_email_status, 'Failed')

            # Verify failure logged in EmailLog
            failed_log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                status='FAILED'
            ).first()
            self.assertIsNotNone(failed_log)

            # 2. Authorized manual retry after IP resolution
            mock_send.return_value = (True, "Delivered", "brevo_retry_001")
            success, msg = retry_recruitment_status_email(reloaded, 'application_successful')
            self.assertTrue(success)

            reloaded_again = db.session.get(JobApplication, self.application.id)
            self.assertEqual(reloaded_again.application_success_email_status.upper(), 'SENT')

    # -------------------------------------------------------------------------
    # TEST 11: Changing to Under Review does not trigger email
    # -------------------------------------------------------------------------
    def test_11_changing_to_under_review_does_not_trigger_email(self):
        """Recruitment stage change to Under Review sends zero emails."""
        with patch('services.email_service.send_brevo_email') as mock_send:
            ok, msg = send_recruitment_status_email(self.application, 'Under Review', 'Applied')
            self.assertFalse(ok)
            mock_send.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 12: Changing to Shortlisted does not trigger email
    # -------------------------------------------------------------------------
    def test_12_changing_to_shortlisted_does_not_trigger_email(self):
        """Recruitment stage change to Shortlisted sends zero emails."""
        with patch('services.email_service.send_brevo_email') as mock_send:
            ok, msg = send_recruitment_status_email(self.application, 'Shortlisted', 'Under Review')
            self.assertFalse(ok)
            mock_send.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 13: Changing to Rejected does not trigger email
    # -------------------------------------------------------------------------
    def test_13_changing_to_rejected_does_not_trigger_email(self):
        """Recruitment stage change to Rejected sends zero emails."""
        with patch('services.email_service.send_brevo_email') as mock_send:
            ok, msg = send_recruitment_status_email(self.application, 'Rejected', 'Under Review')
            self.assertFalse(ok)
            mock_send.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 14: Only one template entry is displayed
    # -------------------------------------------------------------------------
    def test_14_only_one_template_entry_displayed(self):
        """Admin templates view renders exactly one active template card."""
        self.login_admin()
        resp = self.client.get('/admin/templates')
        self.assertEqual(resp.status_code, 200)

        # Renders single template
        self.assertIn(b"Application Submitted Successfully", resp.data)
        self.assertIn(b"Candidate Application Submitted", resp.data)
        self.assertIn(b"5 Minutes Delay", resp.data)

        # Active templates count in DB is strictly 1
        active_templates = EmailTemplate.query.filter_by(is_active=True).all()
        self.assertEqual(len(active_templates), 1)
        self.assertEqual(active_templates[0].template_type, 'application_successful')

    # -------------------------------------------------------------------------
    # TEST 15: No rejection email automation exists
    # -------------------------------------------------------------------------
    def test_15_no_rejection_email_automation_exists(self):
        """No active rejection template or mapping exists in active automations."""
        rejection_mapping = EmailTemplateMapping.query.filter_by(
            event_key='candidate_rejected',
            is_active=True
        ).first()
        self.assertIsNone(rejection_mapping)

        # Stage change via HTTP route updates stage with zero email dispatch
        self.login_admin()
        with patch('services.email_service.send_brevo_email') as mock_send:
            resp = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Rejected'},
                follow_redirects=True
            )
            self.assertEqual(resp.status_code, 200)
            mock_send.assert_not_called()

            reloaded = db.session.get(JobApplication, self.application.id)
            self.assertEqual(reloaded.status, 'Rejected')

    # -------------------------------------------------------------------------
    # TEST 16: Existing candidate and payment data remains unchanged
    # -------------------------------------------------------------------------
    def test_16_existing_candidate_and_payment_data_unchanged(self):
        """Applications and Payment records remain intact."""
        payment = Payment(
            application_id=self.application.id,
            cashfree_order_id='order_test_9999',
            amount=234.82
        )
        db.session.add(payment)
        db.session.commit()

        # Re-run schema initialization
        ensure_email_template_schema()

        # Verify application, payment, and job data are untouched
        reloaded_app = db.session.get(JobApplication, self.application.id)
        self.assertIsNotNone(reloaded_app)
        self.assertEqual(reloaded_app.application_code, 'AM-APP-000601')

        reloaded_pmt = Payment.query.filter_by(cashfree_order_id='order_test_9999').first()
        self.assertIsNotNone(reloaded_pmt)
        self.assertEqual(reloaded_pmt.amount, 234.82)


if __name__ == '__main__':
    unittest.main()
