# ANTI-MATRIX — CAREERS APPLY NOW LOGIN / SIGNUP AUTHENTICATION FLOW REPORT

**Document Version:** 1.0.0  
**Date:** 2026-11-20  
**Project:** Anti-Matrix Official Website  
**Production URL:** https://antimatrix.co.in  
**Application Architecture:** Flask + PostgreSQL (Production) / SQLite (Testing) + Gunicorn + Nginx  
**Status:** Verification & Automated Testing Complete — Ready for Review (Pre-Deployment)

---

## 1. Executive Summary

As requested in the **ANTI-MATRIX — CAREERS APPLY NOW LOGIN / SIGNUP AUTHENTICATION FLOW** specification, the public Careers application flow has been upgraded to mandate applicant authentication before accessing or submitting any job application form.

### Key Objectives Implemented
1. **Apply Now Authentication Gate:**
   - When an unauthenticated visitor clicks `Apply Now` or enters an application URL (e.g. `/careers/apply/145`), the server immediately issues an HTTP 302 redirect to the applicant Login / Signup page (`/login?next=/careers/apply/145`).
   - The user is greeted with a clear guidance alert: *"Please log in or create an account to continue your job application."*
   - If an applicant is already logged in, they proceed directly to the selected job's application form without re-authentication.

2. **Full Preservation of Selected Job Destination:**
   - Both Login and Signup pages preserve the exact application URL via the `next` / `redirect` mechanism.
   - Switching between "Sign In" and "Create one free" dynamically maintains the `next` parameter (`/signup?next=/careers/apply/<job_id>` and `/login?next=/careers/apply/<job_id>`).
   - Upon successful login or registration, the applicant is automatically returned directly to `/careers/apply/<job_id>` (never redirected to the homepage or generic dashboard).

3. **Open-Redirect Security Hardening:**
   - Evaluated by `get_safe_redirect(target_url, default='/')` to prevent open-redirect vulnerabilities.
   - Rejects external domains (`https://evil.com`), protocol-relative URLs (`//evil.com`), Windows backslash traversal (`/\evil.com`), and javascript schemes (`javascript:alert(1)`), safely defaulting to `/`.

4. **Server-Side Application Form & Route Protection:**
   - Protection is enforced strictly on the server within `apply_job(job_id)` in `routes/main.py`.
   - Both GET and POST requests are protected. Direct unauthenticated HTTP POST submissions are blocked and redirected to login; no application record or candidate entry is created.

5. **Duplicate Application & Candidate Safeguards:**
   - If an authenticated applicant has already applied for the selected job, they are informed with their existing Application ID (`AM-APP-XXXXXX`) and redirected safely without generating duplicate records.
   - If a candidate with the same email or mobile number already exists, duplicate creation is prevented with safe user feedback.
   - Concurrency safety and database unique constraints are preserved intact.

6. **Prefilling & Selected Job Context:**
   - When the authenticated applicant views the form, the selected job title is prominently displayed in the header.
   - The applicant's name and email are pre-filled directly from their authenticated user profile.

---

## 2. File Modifications Inventory

| File Path | Action | Description |
|:---|:---:|:---|
| `routes/main.py` | **Modified** | Enforced server-side `current_user.is_authenticated` guard at the top of `apply_job(job_id)`; added GET duplicate check redirecting already-applied candidates; ensured `user_id = current_user.id` is reliably bound to created applications. |
| `routes/auth.py` | **Modified** | Added contextual flash message for `/careers/apply` targets in `login()` and `signup()`; preserved `redirect_target` across login and signup flows. |
| `templates/auth/login.html` | **Modified** | Added contextual application guidance alert; ensured `next` and `redirect` hidden inputs exist in form; updated "Create one free" link to pass `next=redirect_target`. |
| `templates/auth/signup.html` | **Modified** | Added contextual application guidance alert; ensured `next` and `redirect` hidden inputs exist in form; updated "Sign in" link to pass `next=redirect_target`. |
| `tests/test_careers_auth_flow.py` | **Created** | Comprehensive test suite covering all 12 requested scenarios with 100% test coverage. |
| `tests/test_duplicate_application_prevention.py` | **Modified** | Updated test helper to simulate authenticated applicant submissions in compliance with server-side authentication rules. |

---

## 3. Automated Test Execution Results

### 3.1 Careers Authentication Flow Test Suite (`tests/test_careers_auth_flow.py`)

All 10 tests covering the 12 scenarios passed with 100% success:

```text
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_01_logged_out_visitor_clicks_apply_now_redirects_to_login PASSED [ 10%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_02_login_page_displays_application_notice PASSED [ 20%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_03_visitor_creates_account_and_04_returns_to_job_application PASSED [ 30%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_05_existing_applicant_logs_in_and_06_returns_to_job_application PASSED [ 40%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_07_logged_in_applicant_direct_access PASSED [ 50%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_08_direct_unauthenticated_access_blocked_on_server PASSED [ 60%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_09_invalid_or_external_next_url_is_rejected PASSED [ 70%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_10_authenticated_applicant_submits_application_successfully PASSED [ 80%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_11_duplicate_application_submission_handled_safely PASSED [ 90%]
tests/test_careers_auth_flow.py::CareersAuthFlowTestCase::test_12_existing_careers_filters_and_job_details_continue_working PASSED [100%]

============================= 10 passed in 20.24s =============================
```

### 3.2 Regression Test Suite Execution

Batch regression testing across authentication, duplicate prevention, partner earnings, and admin navigation:

```text
tests/test_careers_auth_flow.py ......................... 10 passed
tests/test_duplicate_application_prevention.py .......... 10 passed
tests/test_partner_earnings_records.py .................. 11 passed
tests/test_admin_five_modules_navigation.py .............  6 passed

============================= 37 passed in 47.43s =============================
```

**Total Tests Verified:** 37 passed, 0 failed.

---

## 4. Scenario Verification Matrix

| # | Scenario | Expected Behavior | Status |
|:---:|:---|:---|:---:|
| 1 | Logged-out visitor clicks Apply Now | HTTP 302 Redirect to `/login?next=/careers/apply/<job_id>` | **VERIFIED** |
| 2 | Visitor redirected to login | Message *"Please log in or create an account to continue your job application."* displayed | **VERIFIED** |
| 3 | Visitor creates account via Signup | User registered, session authenticated | **VERIFIED** |
| 4 | Visitor returns to job application | Automatically redirected to `/careers/apply/<job_id>`, form displayed with job title | **VERIFIED** |
| 5 | Existing applicant logs in | Authenticates with email/password | **VERIFIED** |
| 6 | Existing applicant returns to application | Automatically redirected to `/careers/apply/<job_id>` | **VERIFIED** |
| 7 | Logged-in applicant clicks Apply Now | HTTP 200 Direct access to application form; no login prompt | **VERIFIED** |
| 8 | Direct unauthenticated access to apply URL | GET and POST requests blocked on server; redirected to `/login` | **VERIFIED** |
| 9 | Malicious / external `next` URL | Rejected by `get_safe_redirect`, safely defaults to `/` | **VERIFIED** |
| 10 | Authenticated applicant submits form | Application saved, `user_id` bound, unique `AM-APP-XXXXXX` generated | **VERIFIED** |
| 11 | Duplicate submission / page refresh | Existing application detected; informed with Application ID; no duplicates created | **VERIFIED** |
| 12 | Careers filters & job details | Department filters, keyword search, and in-card drawer continue operating smoothly | **VERIFIED** |

---

## 5. Security & Architectural Integrity

1. **CSRF & Password Hashing:**
   - Standard WTForms / Flask-WTF CSRF tokens validated on all submissions.
   - Secure Argon2 / Werkzeug PBKDF2 password hashing preserved.
2. **Session Integrity:**
   - Flask-Login secure session cookies with `HttpOnly` and `SameSite` flags.
3. **Database Unchanged:**
   - No database tables were dropped, truncated, or re-initialized.
   - Existing user records, job postings, and applications remain 100% intact.
   - `ALLOW_STARTUP_DB_INIT=false` preserved.
4. **Pre-Deployment Safety:**
   - In accordance with production directives, all changes remain in the approved local working tree.
   - **No deployment or push to GitHub has been performed.**
   - Standing by for explicit user approval.
