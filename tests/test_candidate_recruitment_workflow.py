import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from models import db, User, JobPosting, JobApplication, EmailTemplate, EmailLog
from services.email_scheduler_service import (
    schedule_application_acknowledgment,
    get_due_applications,
    process_due_acknowledgment_emails
)
from services.email_service import (
    render_application_successful_email,
    render_sample_email_preview
)


@pytest.fixture
def app_client():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        # Ensure test admin user exists
        admin = User.query.filter_by(email='admin_workflow_test@antimatrix.ai').first()
        if not admin:
            admin = User(
                email='admin_workflow_test@antimatrix.ai',
                name='Workflow Admin',
                role='admin',
                is_active=True
            )
            admin.set_password('AdminWorkflowPass123!')
            db.session.add(admin)
            db.session.commit()

        # Ensure test job posting exists
        job = JobPosting.query.filter_by(title='AI Research Scientist').first()
        if not job:
            job = JobPosting(
                title='AI Research Scientist',
                department='Deep Learning',
                location='Bengaluru / Remote',
                employment_type='Full-time',
                short_description='Conduct frontier AI research.',
                description='Full job description for frontier AI research.',
                requirements='Python, PyTorch, Transformers',
                is_active=True,
                job_id='AM-TEST-AI',
                job_code='AM-TEST-AI'
            )
            db.session.add(job)
            db.session.commit()

        # Ensure acknowledgment email template exists
        tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
        if not tmpl:
            tmpl = EmailTemplate(
                template_type='application_successful',
                name='Application Acknowledgment',
                subject='Thank You for Showing Interest in Anti-Matrix',
                body='Dear {{candidate_name}},\n\nThank you for applying for {{job_title}}.\nYour ID is {{application_id}}.'
            )
            db.session.add(tmpl)
            db.session.commit()

        with app.test_client() as client:
            yield client, admin, job


def login_admin(client, admin):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True


class TestCandidateRecruitmentWorkflow:

    def test_application_id_format_and_initial_stage(self, app_client):
        client, admin, job = app_client

        # Create a test application
        app_record = JobApplication(
            job_id=job.id,
            full_name='Priya Sharma',
            email='priya.sharma.test@example.com',
            phone='9876543210',
            college='IIT Madras',
            status='Applied',
            application_status='Applied',
            payment_status='paid',
            application_success_email_status='Pending'
        )
        db.session.add(app_record)
        db.session.flush()

        app_record.application_code = JobApplication.generate_unique_application_code(app_id=app_record.id)
        db.session.commit()

        # Verify Application ID format: AM-APP-######
        assert app_record.application_code.startswith('AM-APP-')
        assert len(app_record.application_code) == 13  # AM-APP- (7) + 6 digits
        assert app_record.formatted_code == app_record.application_code
        assert app_record.stage == 'Applied'
        assert app_record.ack_email_status == 'Pending'

    def test_delayed_email_scheduling_logic(self, app_client):
        client, admin, job = app_client

        # Application submitted now: email should be scheduled for +5 minutes
        now = datetime.now(timezone.utc)
        app_record = JobApplication(
            job_id=job.id,
            full_name='Amit Patel',
            email='amit.patel.test@example.com',
            phone='9876543211',
            status='Applied',
            application_status='Applied',
            payment_status='paid',
            created_at=now
        )
        db.session.add(app_record)
        db.session.flush()
        app_record.application_code = JobApplication.generate_unique_application_code(app_id=app_record.id)
        db.session.commit()

        schedule_application_acknowledgment(app_record, delay_minutes=5)
        db.session.refresh(app_record)

        # Status must be Pending
        assert app_record.ack_email_status == 'Pending'
        # Scheduled time should be approximately 5 minutes in future
        assert app_record.ack_email_scheduled_at is not None
        diff_seconds = (app_record.ack_email_scheduled_at - now).total_seconds()
        assert 295 <= diff_seconds <= 305

        # Query due applications with standard 5-minute cutoff: this application should NOT be due yet
        due_now = get_due_applications(delay_minutes=5)
        assert app_record.id not in [a.id for a in due_now]

    def test_email_worker_processing_when_due(self, app_client):
        client, admin, job = app_client

        # Create application created 6 minutes ago (due for acknowledgment)
        six_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
        app_record = JobApplication(
            job_id=job.id,
            full_name='Vikram Reddy',
            email='vikram.reddy.test@example.com',
            phone='9876543212',
            status='Applied',
            application_status='Applied',
            payment_status='paid',
            application_success_email_status='Pending',
            created_at=six_minutes_ago
        )
        db.session.add(app_record)
        db.session.flush()
        app_record.application_code = JobApplication.generate_unique_application_code(app_id=app_record.id)
        db.session.commit()

        # Run worker with 5-minute delay
        sent_count = process_due_acknowledgment_emails(delay_minutes=5)
        assert sent_count >= 1

        db.session.refresh(app_record)
        assert app_record.ack_email_status == 'Sent'
        assert app_record.ack_email_sent_at is not None

        # Verify idempotency: running worker again should NOT re-send
        second_sent_count = process_due_acknowledgment_emails(delay_minutes=5)
        # Should not process Vikram Reddy again
        db.session.refresh(app_record)
        assert app_record.ack_email_status == 'Sent'

    def test_stage_transitions(self, app_client):
        client, admin, job = app_client
        login_admin(client, admin)

        app_record = JobApplication(
            job_id=job.id,
            full_name='Ananya Sen',
            email='ananya.sen.test@example.com',
            phone='9876543213',
            status='Applied',
            application_status='Applied',
            payment_status='paid'
        )
        db.session.add(app_record)
        db.session.flush()
        app_record.application_code = JobApplication.generate_unique_application_code(app_id=app_record.id)
        db.session.commit()

        # 1. Transition to Under Review
        resp = client.post(f'/admin/applications/{app_record.id}/stage', data={'stage': 'Under Review'}, follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(app_record)
        assert app_record.stage == 'Under Review'

        # 2. Transition to Shortlisted
        resp = client.post(f'/admin/applications/{app_record.id}/stage', data={'stage': 'Shortlisted'}, follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(app_record)
        assert app_record.stage == 'Shortlisted'

        # 3. Transition to Rejected
        resp = client.post(f'/admin/applications/{app_record.id}/stage', data={'stage': 'Rejected'}, follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(app_record)
        assert app_record.stage == 'Rejected'

    def test_template_rendering_and_placeholders(self, app_client):
        client, admin, job = app_client

        app_record = JobApplication(
            job_id=job.id,
            full_name='Karan Johar',
            email='karan.test@example.com',
            phone='9876543214',
            status='Applied',
            application_status='Applied'
        )
        db.session.add(app_record)
        db.session.flush()
        app_record.application_code = JobApplication.generate_unique_application_code(app_id=app_record.id)
        db.session.commit()

        # Render application acknowledgment email
        rendered = render_application_successful_email(app_record)
        assert app_record.full_name in rendered['body_text'] or 'Karan' in rendered['body_text']
        assert job.title in rendered['body_text']
        assert app_record.formatted_code in rendered['body_text']

        # Test sample preview endpoint
        preview = render_sample_email_preview('application_successful')
        assert 'subject' in preview
        assert 'body_html' in preview
        assert 'Rahul Kumar' in preview['body_text']
        assert 'AM-APP-' in preview['body_text']

    def test_templates_admin_view_and_update(self, app_client):
        client, admin, job = app_client
        login_admin(client, admin)

        # GET /admin/templates
        resp = client.get('/admin/templates')
        assert resp.status_code == 200
        assert b'Templates' in resp.data
        assert b'Application Acknowledgment' in resp.data

        # POST update template subject & body
        new_subject = 'Updated Thank You for Showing Interest in Anti-Matrix'
        new_body = 'Dear {{candidate_name}},\n\nCustomized body for {{job_title}}.\nID: {{application_id}}.'

        resp = client.post('/admin/templates/email/application_successful', data={
            'subject': new_subject,
            'body': new_body
        }, follow_redirects=True)
        assert resp.status_code == 200

        # Verify DB updated
        tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
        assert tmpl.subject == new_subject
        assert tmpl.body == new_body

    def test_admin_applications_list_navigation_and_filters(self, app_client):
        client, admin, job = app_client
        login_admin(client, admin)

        # GET /admin/applications
        resp = client.get('/admin/applications')
        assert resp.status_code == 200
        # Verify 5 standard navigation tabs exist
        assert b'Overview' in resp.data
        assert b'Job Postings' in resp.data
        assert b'Candidate Applications' in resp.data
        assert b'Templates' in resp.data
        assert b'Money Management' in resp.data

        # Verify removed elements are NOT in page
        assert b'Create Employee' not in resp.data
        assert b'href="/admin/employees"' not in resp.data
        assert b'href="/admin/inquiries"' not in resp.data
        assert b'href="/admin/internship-benefits"' not in resp.data

        # Filter by stage
        resp_applied = client.get('/admin/applications?status=applied')
        assert resp_applied.status_code == 200
        resp_review = client.get('/admin/applications?status=under_review')
        assert resp_review.status_code == 200
        resp_shortlist = client.get('/admin/applications?status=shortlisted')
        assert resp_shortlist.status_code == 200
        resp_rejected = client.get('/admin/applications?status=rejected')
        assert resp_rejected.status_code == 200
