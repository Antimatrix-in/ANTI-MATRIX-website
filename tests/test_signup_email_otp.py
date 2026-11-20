import re
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from app import create_app
from models import db, User, JobPosting, EmailVerificationOTP
from services.email_service import (
    render_signup_otp_email,
    DEFAULT_SIGNUP_OTP_SUBJECT,
    DEFAULT_SIGNUP_OTP_BODY
)


class SignupEmailOTPTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        EmailVerificationOTP.query.delete()
        User.query.delete()
        JobPosting.query.delete()
        db.session.commit()

        # Seed sample job for redirect testing
        self.job = JobPosting(
            title='AI Engineer Intern',
            job_code='AM-AI-01',
            department='Engineering',
            location='Remote',
            employment_type='Internship',
            duration='1_month',
            salary='Competitive Stipend',
            short_description='Build intelligent autonomous systems.',
            description='Work directly with Deep Learning, PyTorch, and Transformer pipelines.',
            is_active=True
        )
        db.session.add(self.job)
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        EmailVerificationOTP.query.delete()
        User.query.delete()
        JobPosting.query.delete()
        db.session.commit()
        self.app_context.pop()

    # -------------------------------------------------------------------------
    # SCENARIO 1: Valid name & email signup initiation
    # -------------------------------------------------------------------------
    def test_01_valid_name_and_email_signup_initiation(self):
        """Initiating signup with valid name and email creates OTP record and returns 200."""
        res = self.client.post('/auth/send-otp', json={
            'name': 'Rahul Verma',
            'email': 'rahul.verma@example.com'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['email'], 'rahul.verma@example.com')
        self.assertEqual(data['resend_in'], 60)

        # Check DB record
        otp_rec = EmailVerificationOTP.query.filter_by(email='rahul.verma@example.com').first()
        self.assertIsNotNone(otp_rec)
        self.assertEqual(otp_rec.candidate_name, 'Rahul Verma')
        self.assertFalse(otp_rec.is_verified)
        self.assertFalse(otp_rec.is_used)
        self.assertEqual(otp_rec.attempts, 0)
        # Plaintext OTP must NOT be stored
        self.assertNotEqual(len(otp_rec.otp_hash), 6)

    # -------------------------------------------------------------------------
    # SCENARIO 2: OTP email delivery with required subject/body
    # -------------------------------------------------------------------------
    def test_02_otp_email_delivery_with_required_subject_and_body(self):
        """Rendered OTP email contains the required subject and official body format."""
        candidate = "Rahul Verma"
        otp_code = "729401"
        rendered = render_signup_otp_email(candidate, otp_code)

        # Exact subject verification
        self.assertEqual(rendered['subject'], "Verify Your Anti-Matrix Account")

        # Official body text verification
        expected_body = f"""Hello {candidate},

Thank you for registering with Anti-Matrix.

Your email verification code is:

{otp_code}

This code expires in 5 minutes. Please do not share it with anyone.

Regards,
Anti-Matrix Team"""
        self.assertEqual(rendered['body_text'].strip(), expected_body.strip())
        self.assertIn("Verify Your Anti-Matrix Account", rendered['body_html'])
        self.assertIn(otp_code, rendered['body_html'])

    # -------------------------------------------------------------------------
    # SCENARIO 3: 5-minute OTP expiration handling
    # -------------------------------------------------------------------------
    def test_03_otp_expiration_handling(self):
        """Attempting to verify an OTP after 5 minutes returns expired error."""
        now_utc = datetime.now(timezone.utc)
        expired_rec = EmailVerificationOTP(
            email='expired.user@example.com',
            candidate_name='Expired User',
            attempts=0,
            is_verified=False,
            is_used=False,
            expires_at=now_utc - timedelta(seconds=10),
            resend_available_at=now_utc - timedelta(minutes=2)
        )
        expired_rec.set_otp('654321')
        db.session.add(expired_rec)
        db.session.commit()

        res = self.client.post('/auth/verify-otp', json={
            'email': 'expired.user@example.com',
            'otp': '654321'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')
        self.assertTrue(data.get('expired', False))
        self.assertIn('expired', data['message'].lower())

    # -------------------------------------------------------------------------
    # SCENARIO 4: Incorrect OTP rejection
    # -------------------------------------------------------------------------
    def test_04_incorrect_otp_rejection(self):
        """Submitting an invalid 6-digit OTP decrements remaining attempts and returns 400."""
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='wrong.otp@example.com',
            candidate_name='Wrong OTP Candidate',
            attempts=0,
            is_verified=False,
            is_used=False,
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('112233')
        db.session.add(rec)
        db.session.commit()

        res = self.client.post('/auth/verify-otp', json={
            'email': 'wrong.otp@example.com',
            'otp': '999999'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['remaining_attempts'], 4)
        self.assertIn('4 attempt(s) remaining', data['message'])

        # DB attempts updated
        db.session.refresh(rec)
        self.assertEqual(rec.attempts, 1)

    # -------------------------------------------------------------------------
    # SCENARIO 5: 5-attempt limit lockout
    # -------------------------------------------------------------------------
    def test_05_five_attempt_limit_lockout(self):
        """Exceeding 5 attempts locks out verification and returns lockout status."""
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='lockout@example.com',
            candidate_name='Lockout User',
            attempts=4,  # Next failure triggers lockout
            is_verified=False,
            is_used=False,
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('123456')
        db.session.add(rec)
        db.session.commit()

        # 5th attempt failure
        res = self.client.post('/auth/verify-otp', json={
            'email': 'lockout@example.com',
            'otp': '000000'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(data.get('lockout', False))
        self.assertIn('Maximum verification attempts exceeded', data['message'])

        # 6th attempt after lockout
        res2 = self.client.post('/auth/verify-otp', json={
            'email': 'lockout@example.com',
            'otp': '123456'
        })
        self.assertEqual(res2.status_code, 400)
        self.assertTrue(res2.get_json().get('lockout', False))

    # -------------------------------------------------------------------------
    # SCENARIO 6: Resend OTP 60-second cooldown enforcement
    # -------------------------------------------------------------------------
    def test_06_resend_otp_cooldown_enforcement(self):
        """Requesting resend before 60 seconds elapses returns HTTP 429 Too Many Requests."""
        # 1. First send
        res1 = self.client.post('/auth/send-otp', json={
            'name': 'Cooldown User',
            'email': 'cooldown@example.com'
        })
        self.assertEqual(res1.status_code, 200)

        # 2. Immediate resend attempt within 60s
        res2 = self.client.post('/auth/resend-otp', json={
            'email': 'cooldown@example.com'
        })
        self.assertEqual(res2.status_code, 429)
        data = res2.get_json()
        self.assertIn('Please wait', data['message'])
        self.assertGreater(data.get('retry_after', 0), 0)

    # -------------------------------------------------------------------------
    # SCENARIO 7: Previous OTP invalidation on resend
    # -------------------------------------------------------------------------
    def test_07_previous_otp_invalidation_on_resend(self):
        """When resend succeeds after cooldown, the previous OTP is invalidated."""
        now_utc = datetime.now(timezone.utc)
        # Create record whose cooldown has expired
        first_rec = EmailVerificationOTP(
            email='resend.user@example.com',
            candidate_name='Resend User',
            attempts=0,
            is_verified=False,
            is_used=False,
            expires_at=now_utc + timedelta(minutes=4),
            resend_available_at=now_utc - timedelta(seconds=5)  # past cooldown
        )
        first_rec.set_otp('111111')
        db.session.add(first_rec)
        db.session.commit()

        # Trigger resend
        res = self.client.post('/auth/resend-otp', json={
            'email': 'resend.user@example.com'
        })
        self.assertEqual(res.status_code, 200)

        # First OTP must now be marked is_used=True (invalidated)
        db.session.refresh(first_rec)
        self.assertTrue(first_rec.is_used)

        # Attempting to verify the old code '111111' must now fail
        verify_old = self.client.post('/auth/verify-otp', json={
            'email': 'resend.user@example.com',
            'otp': '111111'
        })
        self.assertEqual(verify_old.status_code, 400)

    # -------------------------------------------------------------------------
    # SCENARIO 8: OTP reuse prevention
    # -------------------------------------------------------------------------
    def test_08_otp_reuse_prevention(self):
        """Once an account is created using a verification token, the token cannot be reused."""
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='single.use@example.com',
            candidate_name='Single Use',
            attempts=1,
            is_verified=True,
            is_used=False,
            verification_token='token_single_use_abc123',
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('555555')
        db.session.add(rec)
        db.session.commit()

        # First signup succeeds
        signup_res1 = self.client.post('/signup', json={
            'name': 'Single Use',
            'email': 'single.use@example.com',
            'password': 'Password123!',
            'terms': True,
            'verification_token': 'token_single_use_abc123'
        })
        self.assertEqual(signup_res1.status_code, 200)

        # DB record is now marked used
        db.session.refresh(rec)
        self.assertTrue(rec.is_used)

        # Log out so the client is not already authenticated
        self.client.get('/logout')

        # Second signup attempt with same token fails
        signup_res2 = self.client.post('/signup', json={
            'name': 'Single Use Attempt 2',
            'email': 'single.use@example.com',
            'password': 'AnotherPassword123!',
            'terms': True,
            'verification_token': 'token_single_use_abc123'
        })
        self.assertEqual(signup_res2.status_code, 400)

    # -------------------------------------------------------------------------
    # SCENARIO 9: Password field hidden before verification
    # -------------------------------------------------------------------------
    def test_09_password_field_hidden_before_verification(self):
        """On initial GET /signup, step 3 (password section) is hidden with display: none."""
        res = self.client.get('/signup')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Confirm password step container is styled display: none
        self.assertIn('id="step-3-password"', html)
        self.assertIn('style="display: none;"', html)
        # Confirm Password input itself is not in form
        self.assertNotIn('name="confirm"', html)
        self.assertNotIn('id="signup-confirm"', html)

    # -------------------------------------------------------------------------
    # SCENARIO 10: Password field visible after verification
    # -------------------------------------------------------------------------
    def test_10_password_field_state_after_verification(self):
        """Verifying OTP returns verification_token enabling transition to step 3."""
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='step3.user@example.com',
            candidate_name='Step 3 User',
            attempts=0,
            is_verified=False,
            is_used=False,
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('777888')
        db.session.add(rec)
        db.session.commit()

        res = self.client.post('/auth/verify-otp', json={
            'email': 'step3.user@example.com',
            'otp': '777888'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('verification_token', data)
        self.assertTrue(len(data['verification_token']) >= 32)

    # -------------------------------------------------------------------------
    # SCENARIO 11: Rejection of signup without OTP verification
    # -------------------------------------------------------------------------
    def test_11_rejection_of_signup_without_otp_verification(self):
        """Submitting /signup directly without valid OTP verification token is rejected."""
        res = self.client.post('/signup', json={
            'name': 'No Token User',
            'email': 'notoken@example.com',
            'password': 'SecurePassword123!',
            'terms': True
            # Omitting verification_token
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('Email verification is required', data['message'])

    # -------------------------------------------------------------------------
    # SCENARIO 12: Rejection of already-registered email with login prompt
    # -------------------------------------------------------------------------
    def test_12_rejection_of_already_registered_email_with_login_prompt(self):
        """Attempting to initiate OTP with an already-registered email directs to login."""
        # Pre-seed user
        existing = User(
            name='Existing User',
            email='registered@example.com',
            role='member',
            email_verified=True
        )
        existing.set_password('Password123!')
        db.session.add(existing)
        db.session.commit()

        # Send OTP for this email
        res = self.client.post('/auth/send-otp', json={
            'name': 'Imposter',
            'email': 'registered@example.com'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')
        self.assertTrue(data.get('already_registered', False))
        self.assertIn('already exists', data['message'])

    # -------------------------------------------------------------------------
    # SCENARIO 13: Successful account creation with verified status
    # -------------------------------------------------------------------------
    def test_13_successful_account_creation_with_verified_status(self):
        """Submitting valid signup with verified OTP token creates user with email_verified=True."""
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='new.member@example.com',
            candidate_name='New Member',
            is_verified=True,
            is_used=False,
            verification_token='token_member_success_xyz',
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('123456')
        db.session.add(rec)
        db.session.commit()

        res = self.client.post('/signup', json={
            'name': 'New Member',
            'email': 'new.member@example.com',
            'password': 'ValidPassword123!',
            'terms': True,
            'verification_token': 'token_member_success_xyz'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')

        # Check DB user
        user = User.query.filter_by(email='new.member@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.name, 'New Member')
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_verified)

    # -------------------------------------------------------------------------
    # SCENARIO 14: Secure password hashing verification
    # -------------------------------------------------------------------------
    def test_14_secure_password_hashing(self):
        """Passwords are stored as secure hashes and never stored in plaintext."""
        raw_pass = 'MySuperSecretP@ss999!'
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='hash.check@example.com',
            candidate_name='Hash Check',
            is_verified=True,
            is_used=False,
            verification_token='token_hash_check_456',
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('654321')
        db.session.add(rec)
        db.session.commit()

        self.client.post('/signup', json={
            'name': 'Hash Check',
            'email': 'hash.check@example.com',
            'password': raw_pass,
            'terms': True,
            'verification_token': 'token_hash_check_456'
        })

        user = User.query.filter_by(email='hash.check@example.com').first()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password_hash, raw_pass)
        self.assertTrue(user.check_password(raw_pass))
        self.assertFalse(user.check_password('WrongPass!'))

    # -------------------------------------------------------------------------
    # SCENARIO 15: Terms acceptance validation
    # -------------------------------------------------------------------------
    def test_15_terms_acceptance_validation(self):
        """Signup without accepting terms is rejected with 400."""
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='noterms@example.com',
            candidate_name='No Terms',
            is_verified=True,
            is_used=False,
            verification_token='token_no_terms_789',
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('123456')
        db.session.add(rec)
        db.session.commit()

        res = self.client.post('/signup', json={
            'name': 'No Terms',
            'email': 'noterms@example.com',
            'password': 'ValidPassword123!',
            'terms': False,
            'verification_token': 'token_no_terms_789'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('terms', data['errors'])

    # -------------------------------------------------------------------------
    # SCENARIO 16: Preservation of /careers/apply/<job_id> redirect target
    # -------------------------------------------------------------------------
    def test_16_preservation_of_job_application_redirect(self):
        """Preserves selected job application URL across the signup process."""
        apply_url = f'/careers/apply/{self.job.id}'
        now_utc = datetime.now(timezone.utc)
        rec = EmailVerificationOTP(
            email='applicant.pooja@example.com',
            candidate_name='Pooja Sharma',
            is_verified=True,
            is_used=False,
            verification_token='token_pooja_app_redirect',
            expires_at=now_utc + timedelta(minutes=5),
            resend_available_at=now_utc + timedelta(seconds=60)
        )
        rec.set_otp('888999')
        db.session.add(rec)
        db.session.commit()

        # Submit signup with redirect target
        res = self.client.post('/signup', json={
            'name': 'Pooja Sharma',
            'email': 'applicant.pooja@example.com',
            'password': 'SecurePoojaPassword123!',
            'terms': True,
            'verification_token': 'token_pooja_app_redirect',
            'redirect': apply_url
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['redirect'], apply_url)

    # -------------------------------------------------------------------------
    # SCENARIO 17: Existing login flow remains unaffected
    # -------------------------------------------------------------------------
    def test_17_existing_login_flow_unaffected(self):
        """Existing password login route continues working with standard authentication."""
        existing = User(
            name='Standard Login User',
            email='standard.user@example.com',
            role='member',
            email_verified=True
        )
        existing.set_password('StandardPass123!')
        db.session.add(existing)
        db.session.commit()

        login_res = self.client.post('/login', json={
            'email': 'standard.user@example.com',
            'password': 'StandardPass123!'
        })
        self.assertEqual(login_res.status_code, 200)
        data = login_res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['user']['email'], 'standard.user@example.com')

    # -------------------------------------------------------------------------
    # SCENARIO 18: Rate limiting on OTP requests
    # -------------------------------------------------------------------------
    def test_18_rate_limiting_on_otp_requests(self):
        """Exceeding 10 OTP requests in 1 hour triggers rate limit HTTP 429."""
        email = 'ratelimit@example.com'
        now_utc = datetime.now(timezone.utc)

        # Seed 10 previous OTP requests within the last hour
        for i in range(10):
            past_rec = EmailVerificationOTP(
                email=email,
                candidate_name='Rate Limited',
                attempts=0,
                is_verified=False,
                is_used=True,
                expires_at=now_utc - timedelta(minutes=10),
                resend_available_at=now_utc - timedelta(minutes=15)
            )
            past_rec.set_otp('123456')
            db.session.add(past_rec)
        db.session.commit()

        # 11th request triggers rate limit
        res = self.client.post('/auth/send-otp', json={
            'name': 'Rate Limited',
            'email': email
        })
        self.assertEqual(res.status_code, 429)
        data = res.get_json()
        self.assertIn('Too many verification code requests', data['message'])

    # -------------------------------------------------------------------------
    # SCENARIO 19: Graceful handling of email delivery failures
    # -------------------------------------------------------------------------
    def test_19_graceful_handling_of_email_delivery_failures(self):
        """When the email delivery provider fails, returns HTTP 500 with user-friendly message."""
        with patch('routes.auth.send_signup_otp_email') as mock_send:
            mock_send.return_value = (False, "SMTP connection timed out", None)

            res = self.client.post('/auth/send-otp', json={
                'name': 'Failure Test',
                'email': 'failure.test@example.com'
            })
            self.assertEqual(res.status_code, 500)
            data = res.get_json()
            self.assertEqual(data['status'], 'error')
            self.assertIn('Unable to send verification code email', data['message'])


if __name__ == '__main__':
    unittest.main()
