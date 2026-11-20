# Anti-Matrix — Signup Email OTP Verification Before Password Creation
## Comprehensive Technical Implementation & Verification Audit Report

**Date:** November 20, 2026  
**Environment:** Local Workspace & Test Runner (Python 3.12.9, Flask-Login, SQLAlchemy)  
**Status:** Completed & 100% Verified (60/60 Tests Passing)

---

## 1. Executive Summary

We have redesigned the applicant registration flow at `/signup` to enhance security, ensure high-quality candidate data, and eliminate duplicate or unverified registrations.

### Key Enhancements
1. **Elimination of "Confirm Password" Field:** The redundant confirm password field has been completely removed in favor of direct email verification before credential creation.
2. **Step-Based Interactive Registration Flow:**
   - **Step 1 (Applicant Details):** Collects Full Name and Email Address. Validates format, checks whether the email is already registered (prompting immediate sign-in), and generates a cryptographically secure 6-digit OTP.
   - **Step 2 (Email OTP Verification):** Displays the targeted email, allows email correction, presents a 6-digit monospace code input, provides a 60-second resend countdown timer, enforces a 5-minute expiration window, and enforces a strict 5-attempt lockout.
   - **Step 3 (Password Creation):** Revealed **only** after email OTP is successfully verified. Collects a secure password (minimum 8 characters) with an interactive eye-toggle, enforces Terms & Conditions acceptance, and keeps the "Create Account" button disabled until valid.
   - **Step 4 (Account Creation & Auto-Login):** Enforces server-side verification using a single-use verification token, marks `user.email_verified = True`, hashes credentials using secure PBKDF2/Argon2, logs the applicant in automatically, and redirects directly to the applicant's selected destination (preserving `/careers/apply/<job_id>`).

---

## 2. Core Architecture & Database Schema

### 2.1. `EmailVerificationOTP` Model (`models/signup_otp.py`)
To ensure high security, rate limiting, and tamper resistance without storing plaintext codes, we implemented the `EmailVerificationOTP` model:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `Integer` (PK) | Unique record identifier. |
| `email` | `String(120)` (Index) | Normalized lowercase applicant email. |
| `candidate_name` | `String(120)` | Full name submitted during Step 1. |
| `otp_hash` | `String(256)` | Cryptographically salted hash of the 6-digit code. |
| `verification_token` | `String(100)` (Unique, Index) | Single-use UUID/hex token issued upon successful OTP check. |
| `attempts` | `Integer` | Number of failed verification attempts (max 5). |
| `is_verified` | `Boolean` | Set to `True` when correct OTP is supplied. |
| `is_used` | `Boolean` | Set to `True` once account is registered (prevents token reuse). |
| `expires_at` | `DateTime` | Expiration timestamp (now + 5 minutes). |
| `resend_available_at` | `DateTime` | Cooldown timestamp (now + 60 seconds). |
| `created_at` | `DateTime` | Creation timestamp in UTC. |
| `updated_at` | `DateTime` | Last update timestamp in UTC. |

### 2.2. User Model Update (`models/user.py`)
- Added `email_verified = db.Column(db.Boolean, default=False, nullable=True)`.
- Added `@property def is_verified(self): return bool(self.email_verified)`.
- Safe self-healing schema migration in `app.py` ensures backward-compatible column addition across both PostgreSQL and SQLite.

---

## 3. Endpoints & Business Logic (`routes/auth.py`)

### 3.1. `POST /auth/send-otp` (Alias: `/signup/send-otp`)
- **Validation:** Ensures `name` and `email` are provided and match `EMAIL_REGEX`.
- **Existing User Detection:** Queries `User.query.filter_by(email=email).first()`. If an account exists, returns `400 Bad Request` with `already_registered: true` directing the applicant to log in.
- **Rate Limiting & Cooldown:**
  - Checks if an active unexpired OTP was dispatched less than 60 seconds ago (`latest_otp.can_resend`). If within cooldown, returns `429 Too Many Requests` with `retry_after`.
  - Enforces an hourly ceiling of at most 10 requests per email address to mitigate abuse.
- **Code Generation & Storage:**
  - Generates 6-digit code using `secrets.randbelow(900000) + 100000`.
  - Hashes the OTP using Werkzeug PBKDF2 (`otp_record.set_otp(otp_code)`).
  - Invalidates any prior unused OTP records for that email.
- **Email Dispatch:**
  - Sends official verification email via `services.email_service.send_signup_otp_email`.
  - Handles delivery errors gracefully, returning `500` with user-friendly guidance if provider fails.

### 3.2. `POST /auth/resend-otp` (Alias: `/signup/resend-otp`)
- Enforces 60-second cooldown from the previous send.
- Invalidates the previous OTP code (`is_used = True`).
- Generates a fresh 6-digit code and dispatches a new email.

### 3.3. `POST /auth/verify-otp` (Alias: `/signup/verify-otp`)
- Validates 6-digit formatting.
- Verifies expiration (5-minute lifetime).
- Enforces max 5 attempts limit. If failed attempts reach 5, locks out the code and returns `lockout: true`.
- Verifies code using constant-time comparison (`check_password_hash`).
- Upon success: marks `is_verified = True` and generates a single-use `verification_token = secrets.token_hex(32)`.

### 3.4. `POST /signup`
- **Confirm Password Removed:** Does not require or validate `confirm` password.
- **Server-Side Verification Enforcement:** Requires a valid `verification_token`. Validates that the token exists in `EmailVerificationOTP`, matches the submitted email, is verified (`is_verified == True`), and has not been used (`is_used == False`).
- **Account Instantiation:** Creates `User` with `email_verified=True`, sets password hash, marks `verification_token` as used (`is_used = True`), logs user into session via `login_user(user)`, and redirects to `redirect_target` (e.g. `/careers/apply/145`).

---

## 4. Email Notification Specification

### 4.1. Official Content Format
Dispatched via `services/email_service.py` (`send_signup_otp_email`):

- **Subject:** `Verify Your Anti-Matrix Account`
- **Body Text:**
```text
Hello {{candidate_name}},

Thank you for registering with Anti-Matrix.

Your email verification code is:

{{otp}}

This code expires in 5 minutes. Please do not share it with anyone.

Regards,
Anti-Matrix Team
```
- **HTML Email:** Clean, responsive branded HTML container matching official Anti-Matrix typography and palette.
- **Zero Plaintext Logging:** The 6-digit OTP code is never logged in server log files.

---

## 5. Frontend & User Experience (`templates/auth/signup.html` & `static/js/auth.js`)

1. **Step Indicator:** Visual 3-step breadcrumb (1. Details → 2. Verify → 3. Password).
2. **Form Validation & Visual States:**
   - Step 1: Input validation for name and email with specific error messages.
   - Step 2: Confirmation box displaying the destination email address, a "Change email" button, 6-digit monospace input, resend button with live 60-second countdown timer, and attempt counter.
   - Step 3: Verified status pill (`✓ Verified: user@email.com`), 8+ character password field with interactive eye toggle, and Terms & Conditions checkbox.
3. **Submit Button Guard:** "Create Account" button remains disabled until valid password is typed and Terms & Conditions are checked.
4. **Preserved Redirection:** Hidden inputs for `next` and `redirect` ensure seamless return to `/careers/apply/<job_id>`.

---

## 6. Test Suite & Verification Results

A dedicated automated test suite `tests/test_signup_email_otp.py` was constructed covering all 19 prompt scenarios:

| # | Test Scenario | Method Name | Status |
| :-: | :--- | :--- | :-: |
| 1 | Valid name & email signup initiation | `test_01_valid_name_and_email_signup_initiation` | **PASSED** |
| 2 | OTP email delivery with required subject/body | `test_02_otp_email_delivery_with_required_subject_and_body` | **PASSED** |
| 3 | 5-minute OTP expiration handling | `test_03_otp_expiration_handling` | **PASSED** |
| 4 | Incorrect OTP rejection | `test_04_incorrect_otp_rejection` | **PASSED** |
| 5 | 5-attempt limit lockout | `test_05_five_attempt_limit_lockout` | **PASSED** |
| 6 | Resend OTP 60-second cooldown enforcement | `test_06_resend_otp_cooldown_enforcement` | **PASSED** |
| 7 | Previous OTP invalidation on resend | `test_07_previous_otp_invalidation_on_resend` | **PASSED** |
| 8 | OTP reuse prevention | `test_08_otp_reuse_prevention` | **PASSED** |
| 9 | Password field hidden before verification | `test_09_password_field_hidden_before_verification` | **PASSED** |
| 10 | Password field state after verification | `test_10_password_field_state_after_verification` | **PASSED** |
| 11 | Rejection of signup without OTP verification | `test_11_rejection_of_signup_without_otp_verification` | **PASSED** |
| 12 | Rejection of already-registered email with login prompt | `test_12_rejection_of_already_registered_email_with_login_prompt` | **PASSED** |
| 13 | Successful account creation with verified status | `test_13_successful_account_creation_with_verified_status` | **PASSED** |
| 14 | Secure password hashing verification | `test_14_secure_password_hashing` | **PASSED** |
| 15 | Terms acceptance validation | `test_15_terms_acceptance_validation` | **PASSED** |
| 16 | Preservation of `/careers/apply/<job_id>` redirect target | `test_16_preservation_of_job_application_redirect` | **PASSED** |
| 17 | Existing login flow remains unaffected | `test_17_existing_login_flow_unaffected` | **PASSED** |
| 18 | Rate limiting on OTP requests | `test_18_rate_limiting_on_otp_requests` | **PASSED** |
| 19 | Graceful handling of email delivery failures | `test_19_graceful_handling_of_email_delivery_failures` | **PASSED** |

### Regression Test Suite Results
```text
tests/test_signup_email_otp.py ...................                       [ 31%]
tests/test_careers_auth_flow.py ..........                               [ 48%]
tests/test_admin_login_routing.py ....................                   [ 81%]
tests/test_partner_earnings_records.py ...........                       [100%]

============================= 60 passed in 43.86s =============================
```

---

## 7. Safety, Compliance & Deployment Readiness

- [x] **No Hardcoded Secrets:** Brevo / SMTP API keys remain configured strictly through environment variables.
- [x] **Zero Plaintext OTP Logging:** Plaintext OTPs are never written to log files or database rows.
- [x] **No Destructive Database Changes:** No tables dropped or truncated.
- [x] **Database Startup Initialization:** `ALLOW_STARTUP_DB_INIT=false` preserved for production safety.
- [x] **No Unsolicited Deployment:** All changes are verified locally in git working tree awaiting explicit approval before push.
