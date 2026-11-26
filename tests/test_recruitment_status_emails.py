import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from app import create_app
from models import (
    db, User, JobPosting, JobApplication, EmailTemplate, EmailTemplateMapping, EmailLog
)
from services.email_template_service import ensure_email_template_schema
from services.recruitment_notification_service import (
    send_recruitment_status_email, retry_recruitment_status_email
)


class TestRecruitmentStatusEmails(unittest.TestCase):
    """
    Test Suite for Automatic Recruitment Status Email Triggers:
    1. Applied -> Under Review
    2. Under Review -> Shortlisted
    3. Any -> Rejected (with template)
    4. Rejected (when template is missing / unmapped)
    5. Duplicate prevention / Idempotency check
    6. Non-fatal failure logging & retry endpoint
    7. Candidate email recipient validation & placeholder substitution
    8. Independent 5-minute acknowledgment email
    """

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        db.create_all()

        # Seed schema, default templates and mappings
        ensure_email_template_schema()

        # Create Admin Account
        self.admin = User(
            name='Test Administrator',
            email='admin@antimatrix.co.in',
            role='admin',
            is_active=True
        )
        self.admin.set_password('Admin@123456')
        db.session.add(self.admin)

        # Create Candidate User
        self.candidate_user = User(
            name='Test Candidate',
            email='candidate@test.com',
            role='student',
            is_active=True
        )
        self.candidate_user.set_password('Candidate@123')
        db.session.add(self.candidate_user)

        # Create Job Posting
        self.job = JobPosting(
            title='AI Research Intern',
            department='Engineering',
            location='Remote',
            employment_type='Internship',
            job_code='AM-JOB-001',
            short_description='AI Research Internship',
            description='Detailed internship description',
            is_active=True
        )
        db.session.add(self.job)
        db.session.commit()

        # Create Job Application
        self.application = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate_user.id,
            full_name='Aarav Sharma',
            email='aarav.sharma@example.com',
            phone='9876543210',
            duration='3_months',
            application_code='AM-APP-009999',
            payment_status='paid',
            status='Applied',
            application_status='Applied'
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

    def test_01_applied_to_under_review_triggers_email(self):
        """Applied -> Under Review automatically dispatches Under Review email."""
        self.login_admin()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_msg_ur_001")

            response = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Under Review'},
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            # 1. DB status is updated
            app_db = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_db.stage, 'Under Review')

            # 2. send_brevo_email was called once with candidate's email
            self.assertEqual(mock_send.call_count, 1)
            call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
            call_args = mock_send.call_args[0]
            recipient_email = call_kwargs.get('recipient_email') or call_args[0]
            self.assertEqual(recipient_email, 'aarav.sharma@example.com')

            # 3. EmailLog was created
            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_under_review'
            ).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.status, 'SENT')
            self.assertEqual(log.provider_message_id, 'brevo_msg_ur_001')
            self.assertIn('Aarav Sharma', log.body_preview)
            self.assertIn('AM-APP-009999', log.body_preview)

    def test_02_under_review_to_shortlisted_triggers_email(self):
        """Under Review -> Shortlisted automatically dispatches Shortlisted email."""
        self.login_admin()

        # Set stage to Under Review first
        self.application.status = 'Under Review'
        self.application.application_status = 'Under Review'
        db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_msg_short_002")

            response = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Shortlisted'},
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            app_db = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_db.stage, 'Shortlisted')

            # Verify send
            self.assertEqual(mock_send.call_count, 1)
            call_kwargs = mock_send.call_args.kwargs or {}
            recipient = call_kwargs.get('recipient_email') or (mock_send.call_args[0][0] if mock_send.call_args[0] else None)
            self.assertEqual(recipient, 'aarav.sharma@example.com')

            # Verify EmailLog
            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_shortlisted'
            ).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.status, 'SENT')
            self.assertEqual(log.provider_message_id, 'brevo_msg_short_002')

    def test_03_any_to_rejected_triggers_email_when_template_exists(self):
        """Any -> Rejected automatically dispatches rejection email if template exists."""
        self.login_admin()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_msg_rej_003")

            response = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Rejected'},
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            app_db = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_db.stage, 'Rejected')

            self.assertEqual(mock_send.call_count, 1)
            call_kwargs = mock_send.call_args.kwargs or {}
            recipient = call_kwargs.get('recipient_email') or (mock_send.call_args[0][0] if mock_send.call_args[0] else None)
            self.assertEqual(recipient, 'aarav.sharma@example.com')

            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_rejected'
            ).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.status, 'SENT')

    def test_04_rejected_reports_missing_template_safely(self):
        """When rejection template is missing or unlinked, reports error without crashing."""
        self.login_admin()

        # Delete rejection template to simulate missing template
        rej_tmpl = EmailTemplate.query.filter_by(template_type='rejection_notification').first()
        if rej_tmpl:
            # Unlink from mapping first
            mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_rejected').first()
            if mapping:
                mapping.email_template_id = None
                db.session.commit()
            db.session.delete(rej_tmpl)
            db.session.commit()

        with patch('services.email_service.send_brevo_email') as mock_send:
            response = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Rejected'},
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            # Status must still update to Rejected
            app_db = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_db.stage, 'Rejected')

            # No email sent
            mock_send.assert_not_called()

            # Warning flash message reported to admin
            self.assertIn(b'Status notification email could not be sent', response.data)

    def test_05_idempotency_prevents_duplicate_sends(self):
        """Same stage resubmit or duplicate requests do not send multiple emails."""
        self.login_admin()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_msg_first")

            # First transition: Applied -> Under Review
            res1 = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Under Review'},
                follow_redirects=True
            )
            self.assertEqual(res1.status_code, 200)
            self.assertEqual(mock_send.call_count, 1)

            # Second submit with the SAME stage: Under Review
            res2 = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Under Review'},
                follow_redirects=True
            )
            self.assertEqual(res2.status_code, 200)
            # Call count remains 1 - no duplicate email sent
            self.assertEqual(mock_send.call_count, 1)
            self.assertIn(b"Application stage is already", res2.data)
            self.assertIn(b"Under Review", res2.data)

            # Even if send_recruitment_status_email is invoked directly, EmailLog check blocks duplicate
            app_db = db.session.get(JobApplication, self.application.id)
            success, msg = send_recruitment_status_email(app_db, 'Under Review', 'Applied')
            self.assertFalse(success)
            self.assertIn('already sent', msg.lower())

            # Only 1 EmailLog record exists
            logs = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_under_review'
            ).all()
            self.assertEqual(len(logs), 1)

    def test_06_failure_logging_and_retry_endpoint(self):
        """Email delivery failure is logged as FAILED and can be retried successfully."""
        self.login_admin()

        # Step 1: Simulate Brevo failure on stage update
        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (False, "Brevo API rate limited", None)

            response = self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Under Review'},
                follow_redirects=True
            )
            self.assertEqual(response.status_code, 200)

            # Status is still updated
            app_db = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_db.stage, 'Under Review')

            # Failure is recorded in EmailLog
            log = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_under_review'
            ).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.status, 'FAILED')
            self.assertEqual(log.error_message, "Brevo API rate limited")

        # Step 2: Retry via admin retry endpoint
        with patch('services.email_service.send_brevo_email') as mock_send_retry:
            mock_send_retry.return_value = (True, "Delivered on retry", "brevo_msg_retry_099")

            retry_response = self.client.post(
                f'/admin/applications/{self.application.id}/retry-notification',
                data={'event_key': 'candidate_under_review'},
                follow_redirects=True
            )
            self.assertEqual(retry_response.status_code, 200)
            self.assertIn(b"Notification re-sent successfully", retry_response.data)

            # EmailLog now contains SENT status
            log_retried = EmailLog.query.filter_by(
                reference_id=self.application.formatted_code,
                template_type='candidate_under_review'
            ).first()
            self.assertIsNotNone(log_retried)
            self.assertEqual(log_retried.status, 'SENT')
            self.assertEqual(log_retried.provider_message_id, 'brevo_msg_retry_099')

    def test_07_placeholder_substitution(self):
        """Dynamic placeholders (name, job title, application ID) are properly rendered."""
        from services.recruitment_notification_service import _render_template

        template_text = (
            "Hello {{candidate_name}}, your application {{application_id}} "
            "for {{job_title}} at {{company_email}} on {{website}}."
        )

        rendered = _render_template(template_text, self.application)
        self.assertIn("Aarav Sharma", rendered)
        self.assertIn("AM-APP-009999", rendered)
        self.assertIn("AI Research Intern", rendered)
        self.assertIn("info@antimatrix.co.in", rendered)
        self.assertIn("https://antimatrix.co.in", rendered)

    def test_08_acknowledgment_email_remains_independent(self):
        """The 5-minute acknowledgment email scheduling remains separate and unaffected."""
        # Check initial acknowledgment status
        self.assertEqual(self.application.application_success_email_status, 'PENDING')

        self.login_admin()

        with patch('services.email_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_ur_msg")

            # Changing status to Under Review
            self.client.post(
                f'/admin/applications/{self.application.id}/stage',
                data={'stage': 'Under Review'},
                follow_redirects=True
            )

            # Application success acknowledgment status is untouched (still PENDING)
            app_db = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_db.application_success_email_status, 'PENDING')


if __name__ == '__main__':
    unittest.main()
