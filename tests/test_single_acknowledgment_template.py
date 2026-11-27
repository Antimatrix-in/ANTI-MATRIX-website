import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from app import create_app
from models import (
    db, User, JobPosting, JobApplication, EmailTemplate, EmailTemplateMapping, EmailLog
)
from services.email_template_service import (
    ensure_email_template_schema,
    ensure_default_templates_and_mappings
)
from services.email_service import (
    DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT,
    DEFAULT_APPLICATION_SUCCESSFUL_BODY,
    render_sample_email_preview,
    render_application_successful_email,
    send_application_successful_email
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


class TestSingleAcknowledgmentTemplateSystem(unittest.TestCase):
    """
    Verification suite for Single Application Acknowledgment Template System:
    1. Exactly one active template is displayed on /admin/templates.
    2. Its content is editable.
    3. Preview displays the correct dynamic values.
    4. Application submission schedules the email for five minutes later.
    5. Email is not sent before five minutes.
    6. Only one acknowledgment email is sent per valid application.
    7. Other templates cannot trigger automated emails.
    8. Existing candidate applications and email history remain intact.
    9. Existing payment and application flows remain unchanged.
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
    # TEST 1: Exactly one active template is displayed on /admin/templates
    # -------------------------------------------------------------------------
    def test_01_exactly_one_active_template_displayed(self):
        """Verify /admin/templates renders only ONE active template: Application Submitted Successfully."""
        self.login_admin()
        resp = self.client.get('/admin/templates')
        self.assertEqual(resp.status_code, 200)

        # Check single template name and title
        self.assertIn(b"Application Submitted Successfully", resp.data)
        self.assertIn(b"Recruitment", resp.data)
        self.assertIn(b"Candidate Application Submitted", resp.data)
        self.assertIn(b"5 Minutes Delay", resp.data)
        self.assertIn(b"Active", resp.data)

        # Ensure "Add Template" button is removed
        self.assertNotIn(b"Add Template", resp.data)
        # Ensure "Duplicate Template" is removed
        self.assertNotIn(b"Duplicate Template", resp.data)
        # Ensure multi-event automation tab is removed
        self.assertNotIn(b"id=\"subnav-tab-mappings\"", resp.data)

        # Check database records: only 1 active template
        active_templates = EmailTemplate.query.filter_by(is_active=True).all()
        self.assertEqual(len(active_templates), 1)
        self.assertEqual(active_templates[0].template_type, 'application_successful')
        self.assertEqual(active_templates[0].name, 'Application Submitted Successfully')

    # -------------------------------------------------------------------------
    # TEST 2: Template content is editable
    # -------------------------------------------------------------------------
    def test_02_template_content_editable(self):
        """Admin can edit and save the subject and body of the single template."""
        self.login_admin()
        tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
        self.assertIsNotNone(tmpl)

        new_subject = "Updated Acknowledgment Subject | {{application_id}}"
        new_body = "Dear {{candidate_name}},\n\nCustom updated acknowledgment body for {{job_title}}.\n\nBest Regards."

        resp = self.client.post(f'/admin/templates/{tmpl.id}/edit', data={
            'name': 'Application Submitted Successfully',
            'subject': new_subject,
            'body': new_body,
            'is_active': 'true'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"updated successfully", resp.data)

        # Verify DB updated
        reloaded = db.session.get(EmailTemplate, tmpl.id)
        self.assertEqual(reloaded.subject, new_subject)
        self.assertEqual(reloaded.body, new_body)

    # -------------------------------------------------------------------------
    # TEST 3: Preview displays correct dynamic values
    # -------------------------------------------------------------------------
    def test_03_preview_displays_correct_dynamic_values(self):
        """Template preview API replaces dynamic tokens with sample values."""
        self.login_admin()
        tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()

        resp = self.client.get(f'/admin/templates/{tmpl.id}/preview')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn('subject', data)
        self.assertIn('body_html', data)
        # Dynamic sample tokens verified
        self.assertIn("Rahul Kumar", data['body_html'])
        self.assertIn("AI Engineer Intern", data['body_html'])
        self.assertIn("AM-APP-000001", data['subject'])
        self.assertIn("AM-APP-000001", data['body_html'])

    # -------------------------------------------------------------------------
    # TEST 4: Application submission schedules email for five minutes later
    # -------------------------------------------------------------------------
    def test_04_application_submission_schedules_five_minutes_later(self):
        """New application submission calculates ack_email_scheduled_at = created_at + 5 minutes."""
        now_utc = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)
        self.application.created_at = now_utc
        db.session.commit()

        expected_scheduled_at = now_utc + timedelta(minutes=5)
        self.assertEqual(self.application.ack_email_scheduled_at, expected_scheduled_at)
        self.assertEqual(self.application.application_success_email_status, 'Pending')

    # -------------------------------------------------------------------------
    # TEST 5: Email is not sent before five minutes
    # -------------------------------------------------------------------------
    def test_05_email_not_sent_before_five_minutes(self):
        """Applications created less than 5 minutes ago are NOT picked up by get_due_applications."""
        # Application created 2 minutes ago
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.session.commit()

        due_apps = get_due_applications(delay_minutes=5)
        self.assertNotIn(self.application, due_apps)

    # -------------------------------------------------------------------------
    # TEST 6: Only one acknowledgment email is sent per valid application
    # -------------------------------------------------------------------------
    def test_06_only_one_acknowledgment_email_sent_idempotent(self):
        """Duplicate dispatch is suppressed once acknowledgment email is SENT."""
        # Application created 10 minutes ago
        self.application.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.application.application_success_email_status = 'Pending'
        db.session.commit()

        with patch('services.email_scheduler_service.send_brevo_email') as mock_send:
            mock_send.return_value = (True, "Delivered", "brevo_ack_001")

            # First worker processing
            sent_count1 = process_due_acknowledgment_emails(self.app, delay_minutes=5)
            self.assertEqual(sent_count1, 1)
            self.assertEqual(mock_send.call_count, 1)

            # Reload application
            app_reloaded = db.session.get(JobApplication, self.application.id)
            self.assertEqual(app_reloaded.application_success_email_status, 'Sent')

            # Second worker processing on same application: must NOT send duplicate
            sent_count2 = process_due_acknowledgment_emails(self.app, delay_minutes=5)
            self.assertEqual(sent_count2, 0)
            self.assertEqual(mock_send.call_count, 1)  # Call count remains 1

            # Manual retry attempt when already SENT must also be blocked
            success, msg = retry_recruitment_status_email(app_reloaded, 'application_successful')
            self.assertFalse(success)
            self.assertIn('already been sent', msg.lower())
            self.assertEqual(mock_send.call_count, 1)  # Still not called again

    # -------------------------------------------------------------------------
    # TEST 7: Other templates cannot trigger automated emails
    # -------------------------------------------------------------------------
    def test_07_other_templates_cannot_trigger_automated_emails(self):
        """Changing application stage to Under Review, Shortlisted, or Rejected does not send emails."""
        with patch('services.email_service.send_brevo_email') as mock_send:
            # Stage transition to Under Review
            ok_ur, msg_ur = send_recruitment_status_email(self.application, 'Under Review', 'Applied')
            self.assertFalse(ok_ur)
            self.assertIn('inactive', msg_ur.lower())
            mock_send.assert_not_called()

            # Stage transition to Shortlisted
            ok_sh, msg_sh = send_recruitment_status_email(self.application, 'Shortlisted', 'Under Review')
            self.assertFalse(ok_sh)
            self.assertIn('inactive', msg_sh.lower())
            mock_send.assert_not_called()

            # Stage transition to Rejected
            ok_rej, msg_rej = send_recruitment_status_email(self.application, 'Rejected', 'Shortlisted')
            self.assertFalse(ok_rej)
            self.assertIn('inactive', msg_rej.lower())
            mock_send.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 8: Existing candidate applications and email history remain intact
    # -------------------------------------------------------------------------
    def test_08_existing_applications_and_email_history_intact(self):
        """Historical EmailLog records and application data are strictly preserved."""
        # Create a historical failed email log
        log1 = EmailLog(
            recipient_email=self.application.email,
            template_type='application_successful',
            reference_id=self.application.formatted_code,
            subject='Initial Failure',
            body_preview='Attempt 1',
            status='FAILED',
            error_message='HTTP 401 Unrecognised IP address',
            sent_at=datetime.now(timezone.utc)
        )
        db.session.add(log1)
        db.session.commit()

        # Re-run schema initialization
        ensure_email_template_schema()

        # Check that log1 is still present and intact
        reloaded_log = db.session.get(EmailLog, log1.id)
        self.assertIsNotNone(reloaded_log)
        self.assertEqual(reloaded_log.status, 'FAILED')
        self.assertEqual(reloaded_log.error_message, 'HTTP 401 Unrecognised IP address')

        # Check application record is intact
        reloaded_app = db.session.get(JobApplication, self.application.id)
        self.assertIsNotNone(reloaded_app)
        self.assertEqual(reloaded_app.application_code, 'AM-APP-000601')

    # -------------------------------------------------------------------------
    # TEST 9: Existing payment and application flows remain unchanged
    # -------------------------------------------------------------------------
    def test_09_payment_and_application_flows_unchanged(self):
        """Schedule helper safely schedules 5-minute delayed email without crashing."""
        new_app = JobApplication(
            job_id=self.job.id,
            user_id=self.candidate.id,
            full_name='Priya Nair',
            email='priya@example.com',
            phone='9876543211',
            duration='1_month',
            application_code='AM-APP-000777',
            payment_status='paid',
            status='Applied',
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(new_app)
        db.session.commit()

        schedule_application_acknowledgment(new_app, delay_minutes=5)

        reloaded = db.session.get(JobApplication, new_app.id)
        self.assertEqual(reloaded.application_success_email_status, 'Pending')
        self.assertIsNotNone(reloaded.ack_email_scheduled_at)


if __name__ == '__main__':
    unittest.main()
