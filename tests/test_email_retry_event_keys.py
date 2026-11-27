import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from app import create_app
from models import (
    db, User, JobPosting, JobApplication, EmailTemplate, EmailTemplateMapping, EmailLog
)
from services.email_template_service import ensure_email_template_schema
from services.recruitment_notification_service import retry_recruitment_status_email


class TestEmailRetryEventKeys(unittest.TestCase):
    """
    Test suite for email retry routing and event key mapping:
    - Retrying 'application_successful' and 'candidate_application_submitted' (Acknowledgment)
    - Retrying 'under_review_notification' and 'candidate_under_review' (Under Review)
    - Retrying 'offer_letter' and 'candidate_shortlisted' (Shortlisted)
    - Retrying 'rejection_notification' and 'candidate_rejected' (Rejected)
    - Preserving failed notification history in EmailLog (no deletion)
    - Duplicate send prevention when already sent
    - Clean error reporting on invalid event keys
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
            email='candidate@test.com',
            role='student',
            is_active=True
        )
        self.candidate.set_password('Candidate@123')
        db.session.add(self.candidate)

        self.job = JobPosting(
            title='Python AI Engineer Intern',
            department='Engineering',
            location='Remote',
            employment_type='Internship',
            job_code='AM-JOB-003',
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
            email='vikram.test@example.com',
            phone='9876543299',
            duration='3_months',
            application_code='AM-APP-000601',
            payment_status='paid',
            status='Under Review',
            application_status='Under Review',
            application_success_email_status='Failed',
            created_at=datetime(2026, 11, 26, 3, 8, 28, tzinfo=timezone.utc)
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

    def test_01_retry_acknowledgment_with_application_successful(self):
        """Retrying with 'application_successful' correctly dispatches acknowledgment email."""
        # Record a prior FAILED log
        failed_log = EmailLog(
            recipient_email=self.application.email,
            template_type='application_successful',
            reference_id=self.application.formatted_code,
            subject='Acknowledgment Failure',
            body_preview='Failed attempt 1',
            status='FAILED',
            error_message='HTTP 401 Unrecognised IP address',
            sent_at=datetime.now(timezone.utc)
        )
        db.session.add(failed_log)
        db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_ack_retry_001")

            success, msg = retry_recruitment_status_email(self.application, 'application_successful')
            self.assertTrue(success)

            # Application status is updated to SENT
            app_reloaded = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_reloaded.application_success_email_status, 'SENT')

            # Prior FAILED log is preserved
            all_logs = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='application_successful'
            ).all()
            self.assertEqual(len(all_logs), 2)
            statuses = [l.status for l in all_logs]
            self.assertIn('FAILED', statuses)
            self.assertIn('SENT', statuses)

    def test_02_retry_acknowledgment_duplicate_blocked(self):
        """If acknowledgment has already been sent, retry returns error and does not re-send."""
        self.application.application_success_email_status = 'SENT'
        db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            success, msg = retry_recruitment_status_email(self.application, 'application_successful')
            self.assertFalse(success)
            self.assertIn('already been sent', msg.lower())
            mock_send.assert_not_called()

    def test_03_retry_under_review_notification(self):
        """Retrying with 'under_review_notification' correctly dispatches Under Review email when active."""
        # Enable mapping for this specific test
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_under_review').first()
        self.assertIsNotNone(mapping)
        mapping.is_active = True
        if mapping.template:
            mapping.template.is_active = True
        db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_ur_retry_002")

            success, msg = retry_recruitment_status_email(self.application, 'under_review_notification')
            self.assertTrue(success)
            self.assertEqual(mock_send.call_count, 1)

            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_under_review',
                status='SENT'
            ).first()
            self.assertIsNotNone(log)

            # Calling retry again must be blocked as duplicate
            success2, msg2 = retry_recruitment_status_email(self.application, 'under_review_notification')
            self.assertFalse(success2)
            self.assertIn('already been sent', msg2.lower())
            self.assertEqual(mock_send.call_count, 1)  # Not called again

    def test_04_retry_shortlisted_notification(self):
        """Retrying with 'offer_letter' correctly dispatches Shortlisted email when active."""
        # Enable mapping for this specific test
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_shortlisted').first()
        self.assertIsNotNone(mapping)
        mapping.is_active = True
        if mapping.template:
            mapping.template.is_active = True
        db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_sh_retry_003")

            success, msg = retry_recruitment_status_email(self.application, 'offer_letter')
            self.assertTrue(success)

            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_shortlisted',
                status='SENT'
            ).first()
            self.assertIsNotNone(log)

    def test_05_retry_rejected_notification(self):
        """Retrying with 'rejection_notification' correctly dispatches Rejected email when active."""
        # Enable mapping for this specific test
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_rejected').first()
        self.assertIsNotNone(mapping)
        mapping.is_active = True
        if mapping.template:
            mapping.template.is_active = True
        db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_rej_retry_004")

            success, msg = retry_recruitment_status_email(self.application, 'rejection_notification')
            self.assertTrue(success)

            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_rejected',
                status='SENT'
            ).first()
            self.assertIsNotNone(log)

    def test_06_invalid_event_key_handled_safely(self):
        """Invalid event key returns descriptive failure without crashing."""
        success, msg = retry_recruitment_status_email(self.application, 'unknown_bogus_key')
        self.assertFalse(success)
        self.assertIn('Invalid event key', msg)

    def test_07_admin_http_endpoint_retry_flow(self):
        """Testing the full HTTP POST route /admin/applications/<id>/retry-notification."""
        self.login_admin()

        # Ensure application status is Failed prior to retry request
        self.application.application_success_email_status = 'Failed'
        db.session.commit()

        # Clear any prior SENT log for this application from the test setup / login trigger
        EmailLog.query.filter_by(reference_id=self.application.formatted_code).delete()
        db.session.commit()

        # Patch automatic scheduler in before_request so it doesn't race the manual admin retry
        with patch('services.email_scheduler_service.process_due_acknowledgment_emails'):
            with patch('services.email_service.send_brevo_email') as mock_send:
                mock_send.return_value = (True, "Delivered", "brevo_http_retry_005")

                resp = self.client.post(
                    f'/admin/applications/{self.application.id}/retry-notification',
                    data={'event_key': 'application_successful'},
                    follow_redirects=True
                )
                self.assertEqual(resp.status_code, 200)
                self.assertIn(b"Notification re-sent successfully", resp.data)


if __name__ == '__main__':
    unittest.main()
