import io
import unittest
from datetime import datetime, timezone, timedelta
from app import create_app
from models import db, User, JobPosting, JobApplication, EmailVerificationOTP
from routes.auth import get_safe_redirect


class CareersAuthFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        JobApplication.query.delete()
        JobPosting.query.delete()
        User.query.delete()
        db.session.commit()

        # Seed Active Job Posting
        self.job = JobPosting(
            title='AI Engineer Intern',
            department='Artificial Intelligence',
            location='Remote',
            employment_type='Internship',
            duration='1_month',
            salary='Competitive Stipend',
            short_description='Build intelligent autonomous systems.',
            description='Work directly with Deep Learning, PyTorch, and Transformer pipelines.',
            is_active=True
        )
        db.session.add(self.job)

        # Seed Inactive Job Posting
        self.inactive_job = JobPosting(
            title='Legacy Systems Maintainer',
            department='Infrastructure',
            location='On-site',
            employment_type='Full-time',
            short_description='Closed role.',
            description='This role is retired.',
            is_active=False
        )
        db.session.add(self.inactive_job)

        # Seed Existing Candidate User
        self.candidate = User(
            name='Rohit Sharma',
            email='rohit.candidate@example.com',
            role='candidate'
        )
        self.candidate.set_password('CandidateSecret123!')
        db.session.add(self.candidate)

        # Seed Admin User
        self.admin = User(
            name='Anti-Matrix Admin',
            email='admin@antimatrix.ai',
            role='admin'
        )
        self.admin.set_password('AdminPass123!')
        db.session.add(self.admin)

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=False)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # -------------------------------------------------------------------------
    # SCENARIO 1 & 2: Logged-out visitor clicks Apply Now -> Redirected to Login with notice
    # -------------------------------------------------------------------------
    def test_01_logged_out_visitor_clicks_apply_now_redirects_to_login(self):
        """Unauthenticated visitor clicking Apply Now is redirected to login with next parameter preserved."""
        apply_url = f'/careers/apply/{self.job.id}'
        res = self.client.get(apply_url, follow_redirects=False)

        # Must return 302 redirect
        self.assertEqual(res.status_code, 302)
        # Location header must point to /login with next preserving the exact apply URL
        self.assertIn('/login', res.headers['Location'])
        self.assertIn(f'next={apply_url}', res.headers['Location'])

    def test_02_login_page_displays_application_notice(self):
        """Login page displays the required guidance message when redirected from job application."""
        apply_url = f'/careers/apply/{self.job.id}'
        res = self.client.get(apply_url, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Guidance message requirement
        self.assertIn("Please log in or create an account to continue your job application.", html)
        # Form has redirect / next hidden input with target job apply URL
        self.assertIn(f'value="{apply_url}"', html)
        # Signup link preserves next target
        self.assertIn(f'/signup?next={apply_url}', html)

    # -------------------------------------------------------------------------
    # SCENARIO 3 & 4: Visitor creates account via Signup -> Returns to job application
    # -------------------------------------------------------------------------
    def test_03_visitor_creates_account_and_04_returns_to_job_application(self):
        """Visitor registers a new account and is seamlessly redirected to the selected job application form."""
        apply_url = f'/careers/apply/{self.job.id}'

        # Seed verified EmailVerificationOTP token for applicant
        now_utc = datetime.now(timezone.utc)
        otp_rec = EmailVerificationOTP(
            email='pooja.hegde@example.com',
            candidate_name='Pooja Hegde',
            is_verified=True,
            is_used=False,
            verification_token='token_pooja_verified_123',
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        otp_rec.set_otp('123456')
        db.session.add(otp_rec)
        db.session.commit()

        signup_res = self.client.post('/signup', data={
            'name': 'Pooja Hegde',
            'email': 'pooja.hegde@example.com',
            'password': 'SecurePoojaPassword123!',
            'terms': 'on',
            'verification_token': 'token_pooja_verified_123',
            'redirect': apply_url
        }, follow_redirects=False)

        # Must redirect directly to apply_url
        self.assertEqual(signup_res.status_code, 302)
        self.assertEqual(signup_res.headers['Location'], apply_url)

        # Follow redirect to application form
        app_page = self.client.get(apply_url)
        self.assertEqual(app_page.status_code, 200)
        page_html = app_page.get_data(as_text=True)

        # Selected job title must be prominently displayed
        self.assertIn('AI Engineer Intern', page_html)
        # Newly registered applicant email and name prefilled
        self.assertIn('pooja.hegde@example.com', page_html)
        self.assertIn('Pooja Hegde', page_html)

    # -------------------------------------------------------------------------
    # SCENARIO 5 & 6: Existing applicant logs in -> Returns to selected job application
    # -------------------------------------------------------------------------
    def test_05_existing_applicant_logs_in_and_06_returns_to_job_application(self):
        """Existing candidate logs in with next parameter and is directed straight to job application form."""
        apply_url = f'/careers/apply/{self.job.id}'

        login_res = self.client.post('/login', data={
            'email': self.candidate.email,
            'password': 'CandidateSecret123!',
            'redirect': apply_url
        }, follow_redirects=False)

        # Must redirect directly to apply_url, not homepage or admin
        self.assertEqual(login_res.status_code, 302)
        self.assertEqual(login_res.headers['Location'], apply_url)

        # Following redirect loads application form
        form_res = self.client.get(apply_url)
        self.assertEqual(form_res.status_code, 200)
        html = form_res.get_data(as_text=True)

        # Shows selected job title and prefilled credentials
        self.assertIn('AI Engineer Intern', html)
        self.assertIn(self.candidate.email, html)
        self.assertIn(self.candidate.name, html)

    # -------------------------------------------------------------------------
    # SCENARIO 7: Logged-in applicant clicks Apply Now -> Direct access
    # -------------------------------------------------------------------------
    def test_07_logged_in_applicant_direct_access(self):
        """An already logged-in applicant accesses the application form directly without login prompts."""
        self.login(self.candidate.email, 'CandidateSecret123!')

        apply_url = f'/careers/apply/{self.job.id}'
        res = self.client.get(apply_url)

        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('AI Engineer Intern', html)
        self.assertNotIn('Sign in to your Anti-Matrix account', html)
        self.assertNotIn('Please log in or create an account to continue', html)

    # -------------------------------------------------------------------------
    # SCENARIO 8: Direct unauthenticated access to /careers/apply/<job_id>
    # -------------------------------------------------------------------------
    def test_08_direct_unauthenticated_access_blocked_on_server(self):
        """Server blocks direct unauthenticated GET and POST requests to the application route."""
        apply_url = f'/careers/apply/{self.job.id}'

        # Unauthenticated GET
        get_res = self.client.get(apply_url, follow_redirects=False)
        self.assertEqual(get_res.status_code, 302)
        self.assertIn('/login', get_res.headers['Location'])

        # Unauthenticated POST (tampered direct form post)
        post_res = self.client.post(apply_url, data={
            'full_name': 'Hacker Sneak',
            'email': 'sneak@evil.com',
            'phone': '9811223344',
            'duration': '1_month',
            'college': 'Unknown'
        }, follow_redirects=False)

        self.assertEqual(post_res.status_code, 302)
        self.assertIn('/login', post_res.headers['Location'])

        # Verify no rogue application record was created in the database
        rogue = JobApplication.query.filter_by(email='sneak@evil.com').first()
        self.assertIsNone(rogue)

    # -------------------------------------------------------------------------
    # SCENARIO 9: Open redirect prevention (invalid/external next URL rejected)
    # -------------------------------------------------------------------------
    def test_09_invalid_or_external_next_url_is_rejected(self):
        """Security guard get_safe_redirect rejects open redirect attack vectors."""
        self.assertEqual(get_safe_redirect('https://evil.com'), '/')
        self.assertEqual(get_safe_redirect('http://phishing.site/login'), '/')
        self.assertEqual(get_safe_redirect('//evil.com/fake-login'), '/')
        self.assertEqual(get_safe_redirect('/\\evil.com'), '/')
        self.assertEqual(get_safe_redirect('javascript:alert(1)'), '/')

        # Safe internal URLs are preserved
        self.assertEqual(get_safe_redirect(f'/careers/apply/{self.job.id}'), f'/careers/apply/{self.job.id}')
        self.assertEqual(get_safe_redirect('/my-applications'), '/my-applications')

        # When logging in with malicious redirect, server falls back to default
        res = self.client.post('/login', data={
            'email': self.candidate.email,
            'password': 'CandidateSecret123!',
            'redirect': 'https://evil.com/steal-creds'
        }, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/')

    # -------------------------------------------------------------------------
    # SCENARIO 10: Authenticated applicant submits application successfully
    # -------------------------------------------------------------------------
    def test_10_authenticated_applicant_submits_application_successfully(self):
        """Authenticated applicant fills form, submits, binds user_id, and receives unique Application ID."""
        self.login(self.candidate.email, 'CandidateSecret123!')

        apply_url = f'/careers/apply/{self.job.id}'
        mock_resume = (io.BytesIO(b'%PDF-1.4 Mock valid resume content'), 'rohit_resume.pdf')

        res = self.client.post(apply_url, data={
            'full_name': 'Rohit Sharma',
            'email': self.candidate.email,
            'phone': '9876543210',
            'duration': '1_month',
            'college': 'Indian Institute of Science, Bangalore',
            'resume': mock_resume
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(res.status_code, 200)

        # Check database persistence
        app = JobApplication.query.filter_by(email=self.candidate.email).first()
        self.assertIsNotNone(app)
        self.assertEqual(app.user_id, self.candidate.id)
        self.assertEqual(app.job_id, self.job.id)
        self.assertEqual(app.full_name, 'Rohit Sharma')
        self.assertEqual(app.duration, '1_month')
        self.assertTrue(app.application_code.startswith('AM-APP-'))

    # -------------------------------------------------------------------------
    # SCENARIO 11: Duplicate application submission handled safely
    # -------------------------------------------------------------------------
    def test_11_duplicate_application_submission_handled_safely(self):
        """Attempting to submit or re-visit an application for an already applied role prevents duplicate records."""
        self.login(self.candidate.email, 'CandidateSecret123!')

        # First Submission
        apply_url = f'/careers/apply/{self.job.id}'
        mock_resume = (io.BytesIO(b'%PDF-1.4 Mock resume 1'), 'resume1.pdf')
        self.client.post(apply_url, data={
            'full_name': 'Rohit Sharma',
            'email': self.candidate.email,
            'phone': '9876543210',
            'duration': '1_month',
            'college': 'IISc Bangalore',
            'resume': mock_resume
        }, content_type='multipart/form-data', follow_redirects=True)

        initial_count = JobApplication.query.count()
        first_app = JobApplication.query.filter_by(email=self.candidate.email).first()
        initial_app_code = first_app.application_code

        # Attempt duplicate submission for the same job
        mock_resume2 = (io.BytesIO(b'%PDF-1.4 Mock resume 2'), 'resume2.pdf')
        dup_res = self.client.post(apply_url, data={
            'full_name': 'Rohit Sharma',
            'email': self.candidate.email,
            'phone': '9876543210',
            'duration': '1_month',
            'college': 'IISc Bangalore',
            'resume': mock_resume2
        }, content_type='multipart/form-data', follow_redirects=True)

        # Total count must remain unchanged
        self.assertEqual(JobApplication.query.count(), initial_count)
        # Existing Application ID preserved
        refreshed_app = JobApplication.query.filter_by(email=self.candidate.email).first()
        self.assertEqual(refreshed_app.application_code, initial_app_code)

        # Visiting the apply URL on GET after applying safely informs and redirects
        get_res = self.client.get(apply_url, follow_redirects=True)
        self.assertEqual(get_res.status_code, 200)
        self.assertIn(initial_app_code, get_res.get_data(as_text=True))

    # -------------------------------------------------------------------------
    # SCENARIO 12: Careers page filters and job details continue working
    # -------------------------------------------------------------------------
    def test_12_existing_careers_filters_and_job_details_continue_working(self):
        """Careers directory page displays active jobs, search input, drawer specifications, and blocks inactive jobs."""
        res = self.client.get('/careers')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Active job displayed
        self.assertIn('AI Engineer Intern', html)
        self.assertIn('Artificial Intelligence', html)
        self.assertIn('Apply Now', html)

        # Inactive job must NOT be displayed
        self.assertNotIn('Legacy Systems Maintainer', html)

        # Inactive job cannot be applied for even by logged in user
        self.login(self.candidate.email, 'CandidateSecret123!')
        inactive_res = self.client.get(f'/careers/apply/{self.inactive_job.id}', follow_redirects=True)
        self.assertEqual(inactive_res.status_code, 200)
        self.assertIn('This position is currently not accepting new applications.', inactive_res.get_data(as_text=True))
