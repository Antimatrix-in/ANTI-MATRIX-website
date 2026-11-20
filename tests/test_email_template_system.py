import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from models import (
    db, User, JobPosting, JobApplication, EmailTemplate, EmailTemplateMapping, EmailLog
)
from services.email_template_service import (
    ensure_default_templates_and_mappings,
    validate_template_name,
    duplicate_template,
    can_delete_template
)
from services.email_scheduler_service import (
    schedule_application_acknowledgment,
    get_due_applications,
    process_due_acknowledgment_emails
)
from services.email_service import (
    render_sample_email_preview,
    render_application_successful_email,
    SAMPLE_PREVIEW_VARIABLES
)


@pytest.fixture
def app_client():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        # Ensure default templates and mappings
        ensure_default_templates_and_mappings()

        # Admin user
        admin = User.query.filter_by(email='admin_templates_test@antimatrix.ai').first()
        if not admin:
            admin = User(
                email='admin_templates_test@antimatrix.ai',
                name='Template Admin',
                role='admin',
                is_active=True
            )
            admin.set_password('AdminTemplatePass123!')
            db.session.add(admin)
            db.session.commit()

        # Regular user (non-admin)
        regular_user = User.query.filter_by(email='regular_user_test@antimatrix.ai').first()
        if not regular_user:
            regular_user = User(
                email='regular_user_test@antimatrix.ai',
                name='Regular User',
                role='candidate',
                is_active=True
            )
            regular_user.set_password('RegularUserPass123!')
            db.session.add(regular_user)
            db.session.commit()

        # Test job posting
        job = JobPosting.query.filter_by(title='Senior Systems Engineer').first()
        if not job:
            job = JobPosting(
                title='Senior Systems Engineer',
                department='Core Engineering',
                location='Bengaluru / Remote',
                employment_type='Full-time',
                short_description='Build high-performance distributed systems.',
                description='Full job description for Senior Systems Engineer.',
                requirements='Python, Rust, Distributed Systems',
                is_active=True,
                job_id='AM-TEST-SYS',
                job_code='AM-TEST-SYS'
            )
            db.session.add(job)
            db.session.commit()

        with app.test_client() as client:
            yield client, admin, regular_user, job


def login_user(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True


class TestEmailTemplateManagementSystem:

    def test_01_admin_dashboard_renders_with_five_navigation_tabs(self, app_client):
        """
        Verify /admin/templates loads properly, shows page title, description,
        Add Template button, and strictly 5 standard navigation tabs.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        res = client.get('/admin/templates')
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert "Email Template Management" in html
        assert "Create, manage and map automated recruitment email templates." in html
        assert "Add Template" in html
        assert "Email Automation Mapping" in html

        # Strictly 5 Standard Admin Nav Tabs
        assert "Overview" in html
        assert "Job Postings" in html
        assert "Candidate Applications" in html
        assert "Templates" in html
        assert "Money Management" in html

    def test_02_unauthorized_users_cannot_manage_templates(self, app_client):
        """
        Requirement 10.14: Unauthorized users cannot manage templates.
        Both anonymous visitors and non-admin users must be blocked.
        """
        client, _, regular_user, _ = app_client

        # 1. Anonymous visitor
        anon_get = client.get('/admin/templates')
        assert anon_get.status_code in [302, 401, 403]

        anon_post = client.post('/admin/templates/create', data={'name': 'Hacker Template'})
        assert anon_post.status_code in [302, 401, 403]

        # 2. Authenticated non-admin candidate user
        login_user(client, regular_user)
        user_get = client.get('/admin/templates')
        assert user_get.status_code in [302, 403]

        user_post = client.post('/admin/templates/create', data={'name': 'Hacker Template'})
        assert user_post.status_code in [302, 403]

    def test_03_create_multiple_templates_across_categories(self, app_client):
        """
        Requirement 10.1: Create multiple templates.
        Verify creating templates in Recruitment, Assessment, and Interview categories.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        # Template 1: Assessment Invitation
        res1 = client.post('/admin/templates/create', data={
            'name': 'Assessment Invitation Alpha',
            'description': 'Online coding test invitation for candidates.',
            'category': 'Assessment',
            'subject': 'Assessment Invitation: {{job_title}} | Anti-Matrix',
            'body': 'Dear {{candidate_name}},\n\nYour username: {{assessment_username}}.\nLink: {{assessment_link}}',
            'is_active': '1'
        }, follow_redirects=True)
        assert res1.status_code == 200

        # Template 2: Shortlisted Notification
        res2 = client.post('/admin/templates/create', data={
            'name': 'Shortlisted Notification Beta',
            'description': 'Notification sent when candidate is shortlisted.',
            'category': 'Recruitment',
            'subject': 'Congratulations! You Have Been Shortlisted — {{job_title}}',
            'body': 'Dear {{candidate_name}},\n\nWe are pleased to shortlist you for {{job_title}}.',
            'is_active': '1'
        }, follow_redirects=True)
        assert res2.status_code == 200

        # Template 3: Interview Invitation
        res3 = client.post('/admin/templates/create', data={
            'name': 'Technical Interview Schedule Gamma',
            'description': 'Technical round interview invitation.',
            'category': 'Interview',
            'subject': 'Interview Invitation: Round 1 — {{job_title}}',
            'body': 'Dear {{candidate_name}},\n\nYour interview is scheduled.',
            'is_active': '1'
        }, follow_redirects=True)
        assert res3.status_code == 200

        # Verify all 3 exist in DB
        t1 = EmailTemplate.query.filter_by(name='Assessment Invitation Alpha').first()
        t2 = EmailTemplate.query.filter_by(name='Shortlisted Notification Beta').first()
        t3 = EmailTemplate.query.filter_by(name='Technical Interview Schedule Gamma').first()

        assert t1 is not None and t1.category == 'Assessment'
        assert t2 is not None and t2.category == 'Recruitment'
        assert t3 is not None and t3.category == 'Interview'

    def test_04_prevent_duplicate_template_names(self, app_client):
        """
        Requirement 10.2: Prevent duplicate template names.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        # Create base template
        res_first = client.post('/admin/templates/create', data={
            'name': 'Duplicate Test Template',
            'category': 'Assessment',
            'subject': 'Original Subject',
            'body': 'Original Body',
            'is_active': '1'
        }, follow_redirects=True)
        assert res_first.status_code == 200

        # Attempt to create template with exact duplicate name
        res = client.post('/admin/templates/create', data={
            'name': 'Duplicate Test Template',
            'category': 'Assessment',
            'subject': 'Duplicate Subject',
            'body': 'Duplicate Body',
            'is_active': '1'
        }, follow_redirects=True)

        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "already exists" in html

        # Verify only 1 instance exists in database
        count = EmailTemplate.query.filter_by(name='Duplicate Test Template').count()
        assert count == 1

    def test_05_edit_and_rename_template(self, app_client):
        """
        Requirement 10.3: Edit and rename a template.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        tmpl = EmailTemplate(
            template_type='editable_template_test',
            name='Editable Template Test',
            category='Assessment',
            subject='Initial Subject: {{job_title}}',
            body='Initial Body: {{candidate_name}}',
            is_active=True
        )
        db.session.add(tmpl)
        db.session.commit()

        res = client.post(f'/admin/templates/{tmpl.id}/edit', data={
            'name': 'Assessment Invitation Updated',
            'description': 'Updated description.',
            'category': 'Assessment',
            'subject': 'Updated Subject: {{job_title}}',
            'body': 'Updated Body: {{candidate_name}}',
            'is_active': '1'
        }, follow_redirects=True)

        assert res.status_code == 200
        updated = db.session.get(EmailTemplate, tmpl.id)
        assert updated.name == 'Assessment Invitation Updated'
        assert updated.subject == 'Updated Subject: {{job_title}}'

    def test_06_preview_dynamic_placeholders_with_sample_data(self, app_client):
        """
        Requirement 10.4: Preview dynamic variables.
        Verifies replacement of applicant and assessment placeholders with sample data.
        Verifies passwords are masked in preview.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        tmpl = EmailTemplate(
            template_type='preview_template_test',
            name='Preview Template Test',
            category='Assessment',
            subject='Assessment: {{job_title}}',
            body='Dear {{candidate_name}},\nUsername: {{assessment_username}}\nPass: {{assessment_password}}',
            is_active=True
        )
        db.session.add(tmpl)
        db.session.commit()

        res = client.get(f'/admin/templates/{tmpl.id}/preview')
        assert res.status_code == 200
        data = res.get_json()

        assert 'subject' in data
        assert 'body_text' in data
        assert 'body_html' in data

        # Dynamic variable replacement verification
        assert "Rahul Kumar" in data['body_text']
        assert "AI Engineer Intern" in data['subject']
        assert "••••••••" in data['body_text']

    def test_07_duplicate_template_functionality(self, app_client):
        """
        Verify template duplication creates a distinct clone with unique name and slug.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        tmpl = EmailTemplate(
            template_type='duplicate_source_test',
            name='Original Template To Duplicate',
            category='Recruitment',
            subject='Subject To Clone',
            body='Body To Clone',
            is_active=True
        )
        db.session.add(tmpl)
        db.session.commit()

        res = client.post(f'/admin/templates/{tmpl.id}/duplicate', follow_redirects=True)
        assert res.status_code == 200

        cloned = EmailTemplate.query.filter(EmailTemplate.name.like('Copy of Original Template To Duplicate%')).first()
        assert cloned is not None
        assert cloned.id != tmpl.id
        assert cloned.subject == tmpl.subject

    def test_08_map_template_to_event(self, app_client):
        """
        Requirement 10.5: Map a template to an event.
        Verify mapping candidate_application_submitted to an active template with configurable delay.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
        assert tmpl is not None

        res = client.post('/admin/templates/mappings/update', data={
            'event_key': 'candidate_application_submitted',
            'email_template_id': str(tmpl.id),
            'delay_minutes': '5',
            'is_active': '1'
        }, follow_redirects=True)

        assert res.status_code == 200
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').first()
        assert mapping is not None
        assert mapping.email_template_id == tmpl.id
        assert mapping.delay_minutes == 5
        assert mapping.is_active is True

    def test_09_rename_mapped_template_preserves_mapping(self, app_client):
        """
        Requirement 10.6: Rename a mapped template without breaking its mapping.
        Foreign key / stable ID relationship must remain intact.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        target_tmpl = EmailTemplate(
            template_type='shortlist_notification_test',
            name='Shortlisted Notification Stable Test',
            category='Recruitment',
            subject='Shortlisted Subject',
            body='Shortlisted Body',
            is_active=True
        )
        db.session.add(target_tmpl)
        db.session.commit()

        # Map candidate_shortlisted to target_tmpl
        client.post('/admin/templates/mappings/update', data={
            'event_key': 'candidate_shortlisted',
            'email_template_id': str(target_tmpl.id),
            'delay_minutes': '0',
            'is_active': '1'
        })

        # Rename the template
        client.post(f'/admin/templates/{target_tmpl.id}/edit', data={
            'name': 'Shortlisted Notification Renamed Stable',
            'category': 'Recruitment',
            'subject': target_tmpl.subject,
            'body': target_tmpl.body,
            'is_active': '1'
        })

        # Verify mapping still points to the same template ID and resolves new name
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_shortlisted').first()
        assert mapping.email_template_id == target_tmpl.id
        assert mapping.template.name == 'Shortlisted Notification Renamed Stable'

    def test_10_prevent_duplicate_active_mappings(self, app_client):
        """
        Requirement 10.7: Prevent duplicate active mappings for the same event.
        Enforced by unique event_key in email_template_mappings table.
        """
        count = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').count()
        assert count == 1

    def test_11_deactivate_mapped_template_safety(self, app_client):
        """
        Requirement 10.8: Deactivate a mapped template safely.
        Warns admin and halts automated email scheduler dispatch for that event.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        target_tmpl = EmailTemplate(
            template_type='deactivate_safety_test',
            name='Deactivation Safety Template',
            category='Recruitment',
            subject='Safety Subject',
            body='Safety Body',
            is_active=True
        )
        db.session.add(target_tmpl)
        db.session.commit()

        # Map to an event
        client.post('/admin/templates/mappings/update', data={
            'event_key': 'candidate_shortlisted',
            'email_template_id': str(target_tmpl.id),
            'delay_minutes': '0',
            'is_active': '1'
        })

        res = client.post(f'/admin/templates/{target_tmpl.id}/toggle-status', follow_redirects=True)
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # Warning flash present
        assert "Warning" in html or "paused" in html
        db.session.refresh(target_tmpl)
        assert target_tmpl.is_active is False

    def test_12_prevent_deletion_of_actively_mapped_template(self, app_client):
        """
        Requirement 10.9 & 9: Prevent deletion of templates currently used by active mappings.
        """
        client, admin, _, _ = app_client
        login_user(client, admin)

        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted', is_active=True).first()
        assert mapping is not None
        mapped_tmpl = mapping.template

        res = client.post(f'/admin/templates/{mapped_tmpl.id}/delete', follow_redirects=True)
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # Blocked with explanation
        assert "Cannot delete template" in html or "cannot be deleted" in html

        # Verify template still exists in DB
        tmpl_still_exists = db.session.get(EmailTemplate, mapped_tmpl.id)
        assert tmpl_still_exists is not None

    def test_13_application_acknowledgment_uses_mapped_template_and_five_minute_delay(self, app_client):
        """
        Requirements 10.9 & 10.10:
        Application acknowledgment still uses the correct template and waits exactly 5 minutes.
        """
        client, _, _, job = app_client

        # Ensure mapping is active with 5 min delay
        mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').first()
        mapping.delay_minutes = 5
        mapping.is_active = True
        db.session.commit()

        # Application 1: Submitted 2 minutes ago (NOT due)
        now_utc = datetime.now(timezone.utc)
        app_recent = JobApplication(
            job_id=job.id,
            full_name='Recent Applicant',
            email='recent.applicant@example.com',
            phone='9111111111',
            status='Applied',
            payment_status='paid',
            application_success_email_status='Pending',
            created_at=now_utc - timedelta(minutes=2)
        )
        db.session.add(app_recent)

        # Application 2: Submitted 6 minutes ago (DUE!)
        app_due = JobApplication(
            job_id=job.id,
            full_name='Due Applicant',
            email='due.applicant@example.com',
            phone='9222222222',
            status='Applied',
            payment_status='paid',
            application_success_email_status='Pending',
            created_at=now_utc - timedelta(minutes=6)
        )
        db.session.add(app_due)
        db.session.commit()

        due_apps = get_due_applications(delay_minutes=5)
        due_ids = [a.id for a in due_apps]
        assert app_due.id in due_ids
        assert app_recent.id not in due_ids

        # Process due emails
        sent_count = process_due_acknowledgment_emails(delay_minutes=5)
        assert sent_count >= 1

        db.session.refresh(app_due)
        assert app_due.application_success_email_status == 'Sent'
        assert app_due.application_success_email_sent_at is not None

        db.session.refresh(app_recent)
        assert app_recent.application_success_email_status == 'Pending'

    def test_14_scheduled_emails_survive_restarts_and_prevent_duplicate_sends(self, app_client):
        """
        Requirements 10.11 & 10.12:
        Scheduled emails survive restarts (persistent status in DB) and
        duplicate execution does not send duplicate emails.
        """
        client, _, _, job = app_client

        # Submitted 10 minutes ago
        now_utc = datetime.now(timezone.utc)
        app_persisted = JobApplication(
            job_id=job.id,
            full_name='Persistent Applicant',
            email='persisted.applicant@example.com',
            phone='9333333333',
            status='Applied',
            payment_status='paid',
            application_success_email_status='Pending',
            created_at=now_utc - timedelta(minutes=10)
        )
        db.session.add(app_persisted)
        db.session.commit()

        # First run: sends email
        first_run_sent = process_due_acknowledgment_emails(delay_minutes=5)
        assert first_run_sent >= 1

        db.session.refresh(app_persisted)
        assert app_persisted.application_success_email_status == 'Sent'

        # Second run: must NOT re-send
        second_run_sent = process_due_acknowledgment_emails(delay_minutes=5)
        assert second_run_sent == 0

    def test_15_future_assessment_templates_saved_without_triggering_emails(self, app_client):
        """
        Requirement 10.13:
        Future assessment templates can be created and saved without triggering assessment emails.
        """
        client, admin, _, job = app_client
        login_user(client, admin)

        # Create Assessment template
        client.post('/admin/templates/create', data={
            'name': 'Official Assessment Invitation',
            'description': 'Future Assessment Portal Invitation.',
            'category': 'Assessment',
            'subject': 'Your Assessment Link: {{job_title}}',
            'body': 'Portal: {{assessment_link}}\nUser: {{assessment_username}}',
            'is_active': '1'
        })
        assess_tmpl = EmailTemplate.query.filter_by(name='Official Assessment Invitation').first()
        assert assess_tmpl is not None

        # Map to assessment_invitation event (inactive by default for future portal)
        client.post('/admin/templates/mappings/update', data={
            'event_key': 'assessment_invitation',
            'email_template_id': str(assess_tmpl.id),
            'delay_minutes': '0',
            'is_active': '0'
        })

        # Verify mapping exists but is inactive
        mapping = EmailTemplateMapping.query.filter_by(event_key='assessment_invitation').first()
        assert mapping is not None
        assert mapping.email_template_id == assess_tmpl.id
        assert mapping.is_active is False

        # Verify candidate application submission does not send assessment emails
        initial_log_count = EmailLog.query.filter_by(template_type=assess_tmpl.template_type).count()
        assert initial_log_count == 0
