# ANTI-MATRIX — AUTOMATIC RECRUITMENT STATUS EMAIL TRIGGERS REPORT

**Date:** November 26, 2026  
**Target Application:** https://antimatrix.co.in (`/var/www/anti-matrix`)  
**Status:** Successfully Implemented, Verified, and Tested (8/8 Test Suite Passing)  

---

## 1. Executive Summary

We have implemented automatic transactional email notifications triggered whenever an administrator updates an applicant's recruitment stage on Anti-Matrix. The system automatically maps status transitions to corresponding email templates, replaces candidate and job metadata placeholders, sends the email through the existing Brevo email integration, logs the execution details (including provider message IDs and timestamps) in the `email_logs` database table, and prevents duplicate sends through strict idempotency controls.

The entire workflow is **non-fatal**: any email sending issue is logged cleanly as `FAILED` and presented to the administrator with a one-click **Retry Sending** button on the candidate dossier page, while ensuring the database status update is always safely committed.

---

## 2. Status-to-Event Mapping Architecture

| Recruitment Stage Update | Automation Event Key (`event_key`) | Default Template Slug (`template_type`) | Default Email Subject |
|---|---|---|---|
| `Applied → Under Review` | `candidate_under_review` | `under_review_notification` | "Your Application is Under Review — Anti-Matrix" |
| `Any → Shortlisted` | `candidate_shortlisted` | `offer_letter` | "Congratulations! You Have Been Shortlisted — {{Internship Role}} \| Anti Matrix" |
| `Any → Rejected` | `candidate_rejected` | `rejection_notification` | "Update on Your Application — Anti-Matrix" |
| `New Application Submitted` | `candidate_application_submitted` | `application_successful` | *(Intact: 5-minute delayed acknowledgment email)* |

---

## 3. Files Created and Modified

### A. New Service: `services/recruitment_notification_service.py`
- **`send_recruitment_status_email(application, new_status, old_status)`**:
  1. Checks if `new_status == old_status`; if identical, safely skips execution.
  2. Resolves `new_status` to `event_key` via `STATUS_TO_EVENT_KEY`.
  3. Queries `EmailTemplateMapping` for an active mapping and linked `EmailTemplate`.
  4. If mapping or template is missing or inactive:
     - For `Rejected`: returns a descriptive error reporting the missing template rather than failing silently.
  5. Performs **Idempotency Verification**: queries `EmailLog` for an existing `SENT` record matching `reference_id=application.formatted_code` and `template_type=event_key`. If already sent, skips duplicate sending.
  6. Renders dynamic placeholders in subject and body.
  7. Invokes `send_brevo_email(...)` with candidate's actual registered email (`application.email`).
  8. Records attempt in `EmailLog` with `status='SENT'` or `'FAILED'`, `provider_message_id`, `sent_at`, and error messages if any.
- **`retry_recruitment_status_email(application, event_key)`**:
  - Allows administrators to retry failed status notifications. Removes the prior `FAILED` log entry to clear the idempotency lock and re-dispatches the email.
- **`_render_template(text, application)`**:
  - Replaces `{{candidate_name}}`, `{{job_title}}`, `{{application_id}}`, `{{application_date}}`, `{{company_email}}`, `{{website}}`, and legacy offer letter aliases (`{{Student Name}}`, `{{Internship Role}}`, etc.).

### B. Modified: `services/email_template_service.py`
- Added `candidate_under_review` event definition to `SUPPORTED_RECRUITMENT_EVENTS`.
- Added official default template bodies:
  - `DEFAULT_UNDER_REVIEW_SUBJECT` / `DEFAULT_UNDER_REVIEW_BODY`
  - `DEFAULT_REJECTION_SUBJECT` / `DEFAULT_REJECTION_BODY`
- Updated `ensure_default_templates_and_mappings()`:
  - Seeds `under_review_notification` and `rejection_notification` `EmailTemplate` records if not present.
  - Seeds and activates default mappings for `candidate_under_review`, `candidate_shortlisted`, and `candidate_rejected`.
  - Non-destructive backfill for existing databases.

### C. Modified: `routes/admin.py`
- **`update_application_stage(app_id)`**:
  - Captures `old_stage = application.stage` before updating.
  - Commits `application.status = normalized` and `application.application_status = normalized`.
  - Calls `send_recruitment_status_email(application, normalized, old_stage)`.
  - Flashes success message when email is sent, or a descriptive warning if an email could not be sent (e.g. missing template).
  - Skips redundant processing if `old_stage == normalized`.
- **`retry_application_notification(app_id)`** (`POST /admin/applications/<app_id>/retry-notification`):
  - Added new administrative route to retry failed status notifications.
- **`application_detail(app_id)`**:
  - Queries `EmailLog` records for `application.formatted_code` and passes `email_logs` to the template.

### D. Modified: `templates/admin/application_detail.html`
- Added **CARD 3: Status Notifications**:
  - Displays all status notification email logs for the candidate.
  - Shows event type badge, delivery timestamp, Brevo message ID, and status (`Sent` or `Failed`).
  - Displays error details and an inline **Retry Sending** button for failed notifications.

### E. New Test Suite: `tests/test_recruitment_status_emails.py`
- 8 dedicated unit and integration tests covering:
  1. `Applied → Under Review` email trigger and Brevo call verification.
  2. `Under Review → Shortlisted` email trigger and Brevo call verification.
  3. `Any → Rejected` email trigger when template exists.
  4. Missing rejection template graceful reporting and warning flash without crashing.
  5. Idempotency and duplicate send prevention across repeated requests.
  6. Failure logging and admin retry route execution.
  7. Dynamic template placeholder substitution accuracy.
  8. Acknowledgment email (5-minute delayed) independence and status preservation.

---

## 4. Test Verification Results

All 8 tests in `tests/test_recruitment_status_emails.py` passed:

```
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_01_applied_to_under_review_triggers_email PASSED [ 12%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_02_under_review_to_shortlisted_triggers_email PASSED [ 25%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_03_any_to_rejected_triggers_email_when_template_exists PASSED [ 37%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_04_rejected_reports_missing_template_safely PASSED [ 50%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_05_idempotency_prevents_duplicate_sends PASSED [ 62%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_06_failure_logging_and_retry_endpoint PASSED [ 75%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_07_placeholder_substitution PASSED [ 87%]
tests/test_recruitment_status_emails.py::TestRecruitmentStatusEmails::test_08_acknowledgment_email_remains_independent PASSED [100%]

============================= 8 passed in 30.61s ==============================
```

In addition, the full regression test suite passed:
- `test_homepage_recovery.py`: 9/9 passed.
- `test_signup_email_otp.py`: 19/19 passed.
- `test_careers_auth_flow.py`: 10/10 passed.
- `test_admin_login_routing.py`: 18/18 passed.
- `test_partner_earnings_records.py`: 18/18 passed.

---

## 5. Duplicate Prevention & Idempotency Proof

1. **Pre-Dispatch Guard in Route:**
   If `old_stage == normalized`, `update_application_stage()` immediately flashes `"Application stage is already '<stage>'."` and redirects without touching the mailer.
2. **Pre-Dispatch Guard in Service:**
   If `new_status == old_status`, `send_recruitment_status_email()` immediately returns `(False, "No status change — skipped.")`.
3. **Database Idempotency Check (`EmailLog`):**
   Before initiating network calls to Brevo, `_already_sent()` executes:
   ```python
   EmailLog.query.filter_by(
       reference_id=application.formatted_code,
       template_type=event_key,
       status='SENT'
   ).first()
   ```
   If a `SENT` log already exists for this application and event key, sending is skipped and logged.

---

## 6. Safety and Constraint Adherence

1. **Zero Credential Exposure:** No passwords, secret keys, or `.env` files were accessed or printed.
2. **Non-Destructive Database Operations:** No tables were dropped, truncated, or recreated. All schema operations rely on idempotent `ensure_email_template_schema()` checks.
3. **Non-Fatal Email Execution:** An email delivery failure (e.g. Brevo rate limit or outage) records a `FAILED` log and warns the admin, but never prevents the status update from being committed to the database.
4. **Preservation of 5-Minute Delayed Acknowledgment:** The acknowledgment scheduler worker (`services/email_scheduler_service.py`) and candidate application submission workflow remain completely independent and unaltered.
