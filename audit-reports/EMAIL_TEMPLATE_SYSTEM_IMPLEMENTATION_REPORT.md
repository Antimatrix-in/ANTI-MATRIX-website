# ANTI-MATRIX — MULTIPLE EMAIL TEMPLATES & EVENT MAPPING SYSTEM IMPLEMENTATION REPORT

**Project:** Anti-Matrix Official Website  
**Production Domain:** https://antimatrix.co.in  
**Environment:** Hostinger VPS (Ubuntu 24.04) / Local Development  
**Architecture:** Flask + SQLAlchemy + Gunicorn + Nginx  
**Status:** Implementation & Verification Complete — Ready for Review (No production deployment executed)

---

## Executive Summary

The `/admin/templates` module of the Anti-Matrix platform has been upgraded from a single-template editor into a **Centralized Email Template Management & Automation Mapping System**.

Administrators can now create an unlimited number of customizable email templates, categorize them (`Recruitment`, `Assessment`, `Interview`, `General`), preview dynamic variables with sample candidate/assessment data, safely duplicate templates, toggle active statuses, and map templates to lifecycle recruitment events with configurable sending delays.

The existing **5-minute delayed Application Acknowledgment automation** continues to operate uninterrupted through this system without code breaks, database resets, or duplicate emails. Future assessment templates can be created and mapped now without premature dispatch or changes to assessment infrastructure.

---

## 1. Architectural Changes & Module Inventory

### 1.1 Database Architecture (`models/document.py` & `models/__init__.py`)

#### `EmailTemplate` Entity (Enhanced)
Extended the existing model while strictly preserving backward compatibility with legacy queries:
- **`id`** (`INTEGER`, Primary Key): Stable database identifier.
- **`template_type`** (`VARCHAR(100)`, Unique, Indexed): Stable identifier/slug (e.g. `application_successful`, `offer_letter`, `assessment_invitation_alpha`). Exposed via property alias `slug`.
- **`name`** (`VARCHAR(150)`, Unique, Indexed): Human-readable name (e.g. `Application Acknowledgment`, `Online Assessment Invitation`).
- **`description`** (`TEXT`, Nullable): Explanatory note for administrators on template usage.
- **`category`** (`VARCHAR(50)`, Default `'Recruitment'`, Indexed): Organization bucket (`Recruitment`, `Assessment`, `Interview`, `General`).
- **`subject`** (`VARCHAR(255)`, Not Null): Email subject supporting dynamic variables.
- **`body`** (`TEXT`, Not Null): Email body supporting Markdown formatting and dynamic variables.
- **`is_active`** (`BOOLEAN`, Default `TRUE`, Indexed): Master switch for template availability.
- **`created_at` / `updated_at`** (`TIMESTAMP`, UTC): Automatic timestamp tracking.
- **Relationships:** Linked to `EmailTemplateMapping` via `mappings` backref.

#### `EmailTemplateMapping` Entity (New)
Normalized event-to-template mapping table:
- **`id`** (`INTEGER`, Primary Key)
- **`event_key`** (`VARCHAR(100)`, Unique, Indexed): Machine event key (e.g. `candidate_application_submitted`, `candidate_shortlisted`, `assessment_invitation`, etc.).
- **`event_label`** (`VARCHAR(150)`, Not Null): Human-readable event description.
- **`description`** (`TEXT`, Nullable): Explanatory text for the admin UI.
- **`email_template_id`** (`INTEGER`, ForeignKey to `email_templates.id`, `ON DELETE RESTRICT`, Indexed): Stable foreign key linking the event to its template.
- **`delay_minutes`** (`INTEGER`, Default `0`, Not Null): Delay between event occurrence and dispatch (e.g. `5` for application acknowledgment).
- **`is_active`** (`BOOLEAN`, Default `TRUE`, Indexed): Automation master switch.
- **`created_at` / `updated_at`** (`TIMESTAMP`, UTC): Audit timestamps.

### 1.2 Non-Destructive Schema Auto-Migration (`app.py`)
In accordance with production safety guards (`ALLOW_STARTUP_DB_INIT=false`, no dropping of tables or data loss), `app.py` dynamically inspects existing tables using SQLAlchemy `inspect(db.engine)`:
1. Detects whether `description`, `category`, and `is_active` columns exist in `email_templates` and applies non-destructive `ALTER TABLE ADD COLUMN` if absent.
2. Checks whether `email_template_mappings` exists; if missing, creates it safely via `EmailTemplateMapping.__table__.create(db.engine, checkfirst=True)`.
3. Calls `ensure_default_templates_and_mappings()` to guarantee default templates and baseline event mappings exist without overwriting administrator modifications.

---

## 2. Business Logic Services

### 2.1 Template & Mapping Service (`services/email_template_service.py`)
- **`SUPPORTED_TEMPLATE_CATEGORIES`**: `['Recruitment', 'Assessment', 'Interview', 'General']`
- **`SUPPORTED_RECRUITMENT_EVENTS`**:
  1. `candidate_application_submitted` (Default: `Application Acknowledgment`, 5m delay, `Active`)
  2. `candidate_shortlisted` (Default: `Offer Letter / Shortlisted`, 0m delay, `Inactive` until configured)
  3. `candidate_rejected` (Default: `None`, 0m delay, `Inactive`)
  4. `assessment_invitation` (Default: `None`, 0m delay, `Inactive` - reserved for future portal)
  5. `interview_invitation` (Default: `None`, 0m delay, `Inactive`)
- **`validate_template_name(name, current_id=None)`**: Case-insensitive uniqueness enforcement, preventing duplicate names across active and inactive templates.
- **`duplicate_template(template_id)`**: Clones a template with unique naming scheme (`Copy of ...` or `Copy (2) of ...`) and unique slug.
- **`can_delete_template(template_id)`**: Blocks deletion if the template is actively mapped to any recruitment event or is the system-protected `application_successful` template.

### 2.2 Dynamic Variable Replacement Engine (`services/email_service.py`)
Enhanced `replace_variables()` to support whitespace inside braces and case insensitivity:
- **Candidate Placeholders:**
  - `{{candidate_name}}`
  - `{{candidate_email}}`
  - `{{application_id}}`
  - `{{job_title}}`
  - `{{company_name}}`
  - `{{application_date}}`
  - `{{company_email}}`
  - `{{website}}`
- **Future Assessment Placeholders (Supported in preview & future portal):**
  - `{{assessment_username}}`
  - `{{assessment_password}}` (Masked as `••••••••` in previews to prevent exposure)
  - `{{assessment_link}}`
  - `{{assessment_expiry}}`
- **Send-time Protection:** At sending time, `strip_unresolved=True` cleans any residual placeholders so candidates never see raw `{{...}}` tokens.

### 2.3 Delayed Email Scheduler (`services/email_scheduler_service.py`)
- Preserves the non-blocking background worker and persistent database tracking (`Pending`, `Processing`, `Sent`, `Failed`).
- The scheduler now inspects `EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').first()`.
- If the mapping is disabled or the mapped template is inactive, automated dispatch is cleanly paused without throwing errors.
- Respects the administrator-configured `delay_minutes` (defaulting to 5 minutes) when computing the cutoff timestamp: `created_at <= now - delay_minutes`.
- Atomic locking via status `Processing` prevents duplicate dispatches across workers or threads.

---

## 3. Administrative Interface (`templates/admin/templates.html`)

### 3.1 Design System & Navigation
- Maintains the official Anti-Matrix branding (dark modern slate, emerald `#10b981` accents, responsive tables, badge statuses).
- Retains strictly the **5 standard navigation tabs**:
  1. `Overview` (`admin.dashboard`)
  2. `Job Postings` (`admin.jobs`)
  3. `Candidate Applications` (`admin.applications`)
  4. `Templates` (`admin.templates` - Active)
  5. `Money Management` (`admin.money_management`)

### 3.2 Two-Section View
1. **Email Templates Tab:**
   - Search bar: Real-time search across template names and email subjects.
   - Filter dropdowns: Category (`Recruitment`, `Assessment`, `Interview`, `General`), Status (`Active`, `Inactive`), Mapping (`Mapped`, `Unmapped`).
   - Responsive data table displaying Name, Subject, Category, Mapped Event, Delay, Status, Last Updated, and Actions.
   - Actions: Edit modal, Live Preview modal, Duplicate button, Status toggle button, and Safe Delete button.
2. **Email Automation Mapping Tab:**
   - Cards for each system event with status indicator (`Active`, `Template Inactive`, `Paused`).
   - Form allowing admins to select any existing template from a dropdown, configure sending delay in minutes, toggle active status, and save the mapping.
   - Summarizes currently configured delay and destination template.

### 3.3 Interactive Modals
- **Add Template Modal:** Full creation form with dynamic placeholder reference pills (click-to-copy).
- **Edit Template Modal:** Pre-filled edit form with placeholder pills.
- **Preview Modal:** Live rendered HTML email and plain text views populated with sample data, with built-in test email transmission form.
- **Delete Confirmation Modal:** Displays explicit warnings and disables deletion if the template is actively mapped to an automation event.

---

## 4. Verification and Automated Test Results

The new automated test suite in `tests/test_email_template_system.py` comprehensively verifies all 15 operational requirements:

| # | Test Case | Target Requirement | Status |
|---|---|---|---|
| 1 | `test_01_admin_dashboard_renders_with_five_navigation_tabs` | Page load, layout, strictly 5 admin navigation tabs | **PASSED** |
| 2 | `test_02_unauthorized_users_cannot_manage_templates` | Anonymous & non-admin authorization guards | **PASSED** |
| 3 | `test_03_create_multiple_templates_across_categories` | Template creation across Recruitment, Assessment, Interview | **PASSED** |
| 4 | `test_04_prevent_duplicate_template_names` | Case-insensitive duplicate name prevention | **PASSED** |
| 5 | `test_05_edit_and_rename_template` | Template editing and updating | **PASSED** |
| 6 | `test_06_preview_dynamic_placeholders_with_sample_data` | Dynamic variable replacement & password masking | **PASSED** |
| 7 | `test_07_duplicate_template_functionality` | Template cloning with unique slug/name | **PASSED** |
| 8 | `test_08_map_template_to_event` | Mapping event to template with 5m delay | **PASSED** |
| 9 | `test_09_rename_mapped_template_preserves_mapping` | Renaming template preserves foreign-key mapping | **PASSED** |
| 10 | `test_10_prevent_duplicate_active_mappings` | Unique event key constraint enforcement | **PASSED** |
| 11 | `test_11_deactivate_mapped_template_safety` | Safety warning on deactivation & dispatch pause | **PASSED** |
| 12 | `test_12_prevent_deletion_of_actively_mapped_template` | Prevention of deleting actively mapped templates | **PASSED** |
| 13 | `test_13_application_acknowledgment_uses_mapped_template_and_five_minute_delay` | 5-minute delayed cutoff and mapped template rendering | **PASSED** |
| 14 | `test_14_scheduled_emails_survive_restarts_and_prevent_duplicate_sends` | Database persistence & duplicate prevention | **PASSED** |
| 15 | `test_15_future_assessment_templates_saved_without_triggering_emails` | Assessment template saved without triggering emails | **PASSED** |

### Existing Test Suite Regression Checks
- `tests/test_candidate_recruitment_workflow.py`: **7/7 PASSED**
- `tests/test_admin_five_modules_navigation.py`: **6/6 PASSED**
- **Total Combined Tests Passing:** **28 / 28 Tests PASSED (100% Success)**

---

## 5. Production VPS Safety Compliance

All work strictly abides by the mandatory production safety guidelines:
1. **Preserved App Architecture:** `app.py` startup guards and `ALLOW_STARTUP_DB_INIT=false` remain untouched.
2. **Zero Database Destructive Actions:** No `DROP TABLE`, `TRUNCATE`, or destructive migrations. Only additive columns and new table creation if absent.
3. **Preserved Data:** Candidate applications, job postings, financial records, and existing email templates were fully preserved.
4. **Isolated Host:** No Nginx configurations, virtual hosts, or other hosted domains on the VPS were modified.
5. **Security:** No `.env` secrets or credentials exposed.

---

## 6. Recommendations & Next Steps

1. **Review and Verification:** Review the changes locally and run the test suite if desired (`python -m pytest tests/test_email_template_system.py -v`).
2. **Production Deployment Approval:** Once approved, commit and push to Git repository. Production VPS deployment will follow the standard zero-downtime deployment procedure.
3. **Future Assessment Portal Integration:** When the assessment portal backend is implemented, its dispatch trigger will simply query `EmailTemplateMapping.query.filter_by(event_key='assessment_invitation', is_active=True).first()` to send invitations through this same infrastructure.
