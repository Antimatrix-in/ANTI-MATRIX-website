# Anti-Matrix — Single Application Acknowledgment Email Automation Report

**Document Reference:** `audit-reports/SINGLE_APPLICATION_ACKNOWLEDGMENT_AUTOMATION_REPORT.md`  
**Date:** 26 November 2026  
**Environment:** Staging / Local Working Copy (Production Target: `https://antimatrix.co.in` / `/var/www/anti-matrix`)  
**Status:** Complete — All 38 Tests Passing — Awaiting Production Deployment Approval  

---

## 1. Executive Summary & Architectural Guarantee

Anti-Matrix operates **strictly ONE automated recruitment email**:

- **Email Name:** `Application Submitted Successfully`
- **Trigger:** Candidate successfully submits a job application (and completes payment where required).
- **Scheduled Delay:** Exactly 5 minutes after submission (`ack_email_scheduled_at = created_at + 5 minutes`).
- **Recruitment Stage Behavior:** Changing recruitment stages (`Applied`, `Under Review`, `Shortlisted`, `Rejected`) is strictly for candidate management and **NEVER triggers any automated email**.
- **Important Guarantee:** There is **NO automated rejection email**, **NO rejection countdown**, and **NO stage-based email automation**.

---

## 2. Files Changed

| File | Purpose & Changes |
| :--- | :--- |
| `services/email_service.py` | Configured `DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT` (`Application Received Successfully – Anti-Matrix \| {{application_id}}`) and `DEFAULT_APPLICATION_SUCCESSFUL_BODY` to exact prompt specification. Updated `render_sample_email_preview` to return "Application Submitted Successfully". |
| `services/email_template_service.py` | Configured `SUPPORTED_TEMPLATE_CATEGORIES = ['Recruitment']`; single active mapping `candidate_application_submitted` with `delay_minutes=5`; deactivated/archived all obsolete templates (`under_review_notification`, `offer_letter`, `rejection_notification`) and event mappings. |
| `services/email_scheduler_service.py` | Idempotent, restart-safe 5-minute delayed background scheduler. Evaluates `ack_email_scheduled_at <= now_utc`, enforces atomic `Pending -> Processing -> Sent/Failed` state transitions, suppresses duplicate dispatches, and handles temporary failures. |
| `services/recruitment_notification_service.py` | Replaced stage dispatch with strict no-op returning `(False, "Status notification for '...' is inactive. Recruitment stage changes do not trigger automated emails. Anti-Matrix currently uses a single Application Submitted Successfully acknowledgment email.")`. Preserved safe retry handling for acknowledgment emails. |
| `routes/admin.py` | Stripped stage-change email triggers from `update_application_stage`; updated `templates()` route to render only the single active template card; updated `edit_template` to allow editing Subject, Body, and toggling acknowledgment automation (`is_active`). |
| `templates/admin/templates.html` | Redesigned into single-card UI for `Application Submitted Successfully`. Provided Subject and Markdown Body editor, live dynamic token preview modal, and an Enable/Disable Acknowledgment Automation toggle. Removed multiple template cards, Add Template, and Duplicate buttons. |
| `templates/admin/applications.html` | Enhanced `Acknowledgment Email` column to display real-time live countdowns (`Scheduled — 04:59`), `Sending`, `Application Acknowledgment Sent`, and `Failed` (with one-click authorized retry). Added client-side interval script calculating live countdown from server timestamp. |
| `tests/test_single_acknowledgment_automation.py` | Created comprehensive 16-test suite verifying every requirement in the specification. |
| `tests/test_single_acknowledgment_template.py` | 9-test template management suite verifying single-card rendering, editing, and preview. |
| `tests/test_email_scheduler_worker_and_timezone.py` | 6-test suite verifying worker thread PID tracking, IST/UTC timezone conversions, and atomic idempotency. |
| `tests/test_email_retry_event_keys.py` | 7-test suite verifying event aliases and retry safety without duplicate dispatch. |

---

## 3. Single Template Configuration

In `/admin/templates`, exactly **ONE** template entry is displayed:

- **Template Name:** `Application Submitted Successfully`
- **Category:** `Recruitment`
- **Mapped Event:** `Candidate Application Submitted`
- **Delay:** `5 Minutes`
- **Status:** `Active` (or `Disabled` when toggled off)

### Content Specification:
**Subject:**
```text
Application Received Successfully – Anti-Matrix | {{application_id}}
```

**Body:**
```markdown
Dear {{candidate_name}},

Thank you for showing interest in Anti-Matrix and applying for the position of {{job_title}}.

We are pleased to inform you that your application has been successfully submitted.

Your application is currently under review by our recruitment team.

If your profile is shortlisted for the next round of the selection process, you will receive a separate email from us with further instructions.

We appreciate your interest in joining Anti-Matrix and thank you for your patience.

Application ID: {{application_id}}

Best Regards,
Anti-Matrix Recruitment Team
https://antimatrix.co.in
```

### Supported Dynamic Placeholders:
- `{{candidate_name}}`: Applicant's full name.
- `{{job_title}}`: Position applied for (from linked Job Posting).
- `{{application_id}}`: Unique candidate code (e.g. `AM-APP-000601`).

### Administrator Capabilities:
1. **Edit Subject:** Modifiable via modal input.
2. **Edit Body:** Modifiable via Markdown textarea.
3. **Live Preview:** Renders styled HTML with sample candidate data (`Rahul Kumar`, `AI Engineer Intern`, `AM-APP-000001`).
4. **Enable/Disable Automation:** Checkbox toggle in the Edit Modal synchronizes `is_active` across both `EmailTemplate` and `EmailTemplateMapping`. When disabled, automated sends are safely held until re-enabled.

---

## 4. Five-Minute Email Scheduling Implementation

1. **Trigger Condition:**
   - Candidate submits an application via `/careers/apply/<job_id>`.
   - Application record is validated and saved to `job_applications`.
   - `schedule_application_acknowledgment(application, delay_minutes=5)` sets:
     - `application_success_email_status = 'Pending'`
     - `status = 'Applied'`
     - `ack_email_scheduled_at = created_at + 5 minutes`
2. **Non-Blocking & Restart Survival:**
   - Never calls `time.sleep()` in request threads.
   - Server reboots and Gunicorn worker restarts do not lose scheduled emails. When the server restarts, `get_due_applications()` queries `JobApplication.application_success_email_status.in_(['Pending', 'PENDING'])` and `ack_email_scheduled_at <= now_utc`.
3. **Duplicate Prevention (Concurrency & Idempotency):**
   - Atomic database status transition (`JobApplication.query.filter(id==app.id, status=='Pending').update({'application_success_email_status': 'Processing'})`) ensures that across multi-worker deployments, only one worker can process any given application.
   - Once dispatched, status is marked `Sent` (`application_success_email_sent_at = now_utc`), preventing further dispatches.
   - Manual retry via `/admin/applications/<id>/retry-notification` blocks duplicate sends if already marked `Sent`.
4. **Failure Tracking & Safe Retries:**
   - Failed attempts log an `EmailLog` entry with `status = 'FAILED'` and the provider error.
   - Status updates to `Failed`. Up to 3 automatic attempts are allowed before marking `Failed_Max_Retries`.
   - Authorized admins can trigger a manual retry from the application row.

---

## 5. Candidate Applications UI & Real-Time Countdown

In `/admin/applications`, the **Acknowledgment Email** column displays real-time, meaningful states:

| Status State | UI Display | Visual Styling | Details |
| :--- | :--- | :--- | :--- |
| **Scheduled** | `Scheduled — 04:59` | Amber badge with clock icon | Server scheduled timestamp (`data-scheduled-at="{{ app.ack_email_scheduled_at.isoformat() }}"`). |
| **Sending** | `Sending` | Blue badge with spinner | Displays during active Brevo API dispatch. |
| **Sent** | `Application Acknowledgment Sent` | Green badge with check-circle | Displays after delivery confirmation. |
| **Failed** | `Failed` + `[Retry]` | Red badge with alert-circle | Shows failure count and provides authorized one-click Retry button. |

### Real-Time Client-Side Countdown
A lightweight JavaScript interval script runs every second on `/admin/applications`:
```javascript
function updateAcknowledgmentCountdowns() {
  const elements = document.querySelectorAll('.ack-countdown-badge[data-scheduled-at]');
  const now = new Date().getTime();
  elements.forEach(function (el) {
    const schedStr = el.getAttribute('data-scheduled-at');
    if (!schedStr) return;
    const target = new Date(schedStr).getTime();
    const diffSeconds = Math.floor((target - now) / 1000);
    const timerSpan = el.querySelector('.countdown-timer');
    const labelSpan = el.querySelector('.countdown-label');
    if (diffSeconds > 0) {
      const mins = Math.floor(diffSeconds / 60);
      const secs = diffSeconds % 60;
      const formatted = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
      if (timerSpan) timerSpan.textContent = formatted;
    } else {
      if (labelSpan) {
        labelSpan.textContent = 'Sending...';
        el.style.color = '#3b82f6';
        el.style.background = 'rgba(59,130,246,0.12)';
        el.style.borderColor = 'rgba(59,130,246,0.25)';
      }
    }
  });
}
setInterval(updateAcknowledgmentCountdowns, 1000);
updateAcknowledgmentCountdowns();
```
Updates occur automatically in the administrator's browser without requiring a page refresh.

---

## 6. Recruitment Stage Behavior Verification

The existing recruitment stages are preserved for candidate tracking:
- `Applied`
- `Under Review`
- `Shortlisted`
- `Rejected`

### Stage Change Email Behavior:
- Changing stage to `Applied`: **Zero emails sent.**
- Changing stage to `Under Review`: **Zero emails sent.**
- Changing stage to `Shortlisted`: **Zero emails sent.**
- Changing stage to `Rejected`: **Zero emails sent.**
- **No automated rejection email or countdown exists.**

---

## 7. Verification Test Results (38/38 Passing)

All tests passed cleanly:

```powershell
python -m pytest tests/test_single_acknowledgment_automation.py tests/test_single_acknowledgment_template.py tests/test_email_scheduler_worker_and_timezone.py tests/test_email_retry_event_keys.py -v
```

### Test Breakdown:

#### Suite 1: Single Acknowledgment Automation (`test_single_acknowledgment_automation.py`) — 16 Tests
- `test_01_submission_schedules_one_email`: **PASSED**
- `test_02_scheduled_time_exactly_five_minutes_after_submission`: **PASSED**
- `test_03_no_email_sent_immediately`: **PASSED**
- `test_04_email_sent_after_five_minutes`: **PASSED**
- `test_05_correct_candidate_name_inserted`: **PASSED**
- `test_06_correct_job_title_inserted`: **PASSED**
- `test_07_correct_application_id_inserted`: **PASSED**
- `test_08_duplicate_submissions_prevent_duplicate_emails`: **PASSED**
- `test_09_scheduler_survives_application_restart`: **PASSED**
- `test_10_failed_delivery_recorded_and_safely_retried`: **PASSED**
- `test_11_changing_to_under_review_does_not_trigger_email`: **PASSED**
- `test_12_changing_to_shortlisted_does_not_trigger_email`: **PASSED**
- `test_13_changing_to_rejected_does_not_trigger_email`: **PASSED**
- `test_14_only_one_template_entry_displayed`: **PASSED**
- `test_15_no_rejection_email_automation_exists`: **PASSED**
- `test_16_existing_candidate_and_payment_data_unchanged`: **PASSED**

#### Suite 2: Single Acknowledgment Template UI (`test_single_acknowledgment_template.py`) — 9 Tests
- `test_01_exactly_one_active_template_displayed`: **PASSED**
- `test_02_template_content_editable`: **PASSED**
- `test_03_preview_displays_correct_dynamic_values`: **PASSED**
- `test_04_application_submission_schedules_five_minutes_later`: **PASSED**
- `test_05_email_not_sent_before_five_minutes`: **PASSED**
- `test_06_only_one_acknowledgment_email_sent_idempotent`: **PASSED**
- `test_07_other_templates_cannot_trigger_automated_emails`: **PASSED**
- `test_08_existing_applications_and_email_history_intact`: **PASSED**
- `test_09_payment_and_application_flows_unchanged`: **PASSED**

#### Suite 3: Scheduler Worker & Timezone (`test_email_scheduler_worker_and_timezone.py`) — 6 Tests
- `test_01_scheduled_time_and_ist_conversion`: **PASSED**
- `test_02_past_due_application_fetched_and_dispatched`: **PASSED**
- `test_03_recent_application_not_dispatched_prematurely`: **PASSED**
- `test_04_duplicate_dispatch_prevention`: **PASSED**
- `test_05_admin_application_detail_renders_ist_and_utc`: **PASSED**
- `test_06_fork_safe_worker_pid_tracking`: **PASSED**

#### Suite 4: Email Retry Event Keys (`test_email_retry_event_keys.py`) — 7 Tests
- `test_01_retry_acknowledgment_with_application_successful`: **PASSED**
- `test_02_retry_acknowledgment_duplicate_blocked`: **PASSED**
- `test_03_retry_under_review_notification`: **PASSED**
- `test_04_retry_shortlisted_notification`: **PASSED**
- `test_05_retry_rejected_notification`: **PASSED**
- `test_06_invalid_event_key_handled_safely`: **PASSED**
- `test_07_admin_http_endpoint_retry_flow`: **PASSED**

**Overall Result: 38 passed in 37.29s**

---

## 8. Production Safety & Deployment Hold

1. **Database & Data Preservation:**
   - Zero tables were dropped, truncated, or recreated.
   - All historical candidate records, payments, and `EmailLog` entries remain intact.
2. **Startup & Configuration Guards:**
   - `ALLOW_STARTUP_DB_INIT=false` and startup guards in `app.py` remain untouched.
   - No `.env` secrets or API credentials were modified or exposed.
3. **Deployment Hold:**
   - Work is fully tested and contained within the local repository copy.
   - **No deployment, git push, rsync, or production server restart has been performed.**
   - All changes are ready and awaiting explicit authorization.
