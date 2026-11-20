# ANTI-MATRIX — ADMIN DASHBOARD COMPLETE PAGE INVENTORY & AUDIT

**Domain:** https://antimatrix.co.in/admin  
**Audit Scope:** Administrative Panel Architecture, Views, Forms, Actions, and Legacy Endpoints  
**Date:** November 19, 2026  
**Status:** **3 RETAINED CORE MODULES VERIFIED**  
**Total Admin Route Rules in Flask:** 78  
**Active Admin HTML Templates on Disk:** 7  
**Active Admin Unique HTML Pages:** 7  
**Retired Admin Templates on Disk:** 0 (15 Retired Templates Safely Decommissioned)  
**Broken Links / Missing Template References:** **0 (Zero)**

---

## 1. Admin Dashboard Architecture Overview

The Anti-Matrix administrative panel has been simplified to retain **strictly three functional modules**:

```
Admin Dashboard Architecture
├── 1. Overview (/admin/dashboard)
│   ├── Dynamic Financial & Job Statistics (5 Cards)
│   ├── Recent Job Postings Widget (Unlinked Apps Badges)
│   └── Recent Financial Transactions Widget (Ledger Preview)
│
├── 2. Job Postings (/admin/jobs)
│   ├── Postings List & Search/Filter Interface
│   ├── Create Job Posting View (/admin/jobs/create)
│   ├── Edit Job Posting View (/admin/jobs/edit/<id>)
│   └── Safe Action Endpoints (Toggle, Delete, Delete-All)
│
└── 3. Money Management (/admin/money-management)
    ├── Chronological Financial Ledger & Filters
    ├── Add Manual Transaction View (/admin/money-management/add)
    ├── Edit Manual Transaction View (/admin/money-management/transactions/<id>/edit)
    ├── Cashfree Reconciliation Action (/admin/money-management/reconcile)
    └── Clear All Safeguard Action (/admin/money-management/transactions/clear-all)
```

---

## 2. Complete Inventory of Active Admin Pages & Supporting Views

| No. | Admin Page / Module | URL Path | HTTP Methods | Template | Current Status | Purpose / Description | Recommendation |
| :---: | :--- | :--- | :---: | :--- | :---: | :--- | :---: |
| **1** | **Dashboard / Overview** | `/admin`<br>`/admin/`<br>`/admin/dashboard` | `GET` | `admin/dashboard.html` | **Active** | Core executive overview: 5 real-time metrics (Total Jobs, Active Openings, Net Balance, Total Income, Total Transactions) and dual widgets. | **KEEP** (Module 1) |
| **2** | **Job Postings List** | `/admin/jobs` | `GET` | `admin/jobs.html` | **Active** | Primary job management view: filter by status, department, search keywords; manage active/draft states. | **KEEP** (Module 2) |
| **3** | **Create Job Posting** | `/admin/jobs/create` | `GET, POST` | `admin/create_job.html` | **Active** | Secondary supporting view: form to create and publish a new job opening or internship role with live card preview drawer. | **KEEP** (Module 2 Supporting) |
| **4** | **Edit Job Posting** | `/admin/jobs/edit/<int:job_id>` | `GET, POST` | `admin/edit_job.html` | **Active** | Secondary supporting view: form to modify existing job specifications, department, duration, stipend, and status. | **KEEP** (Module 2 Supporting) |
| **5** | **Money Management Ledger** | `/admin/money-management` | `GET` | `admin/money_management.html` | **Active** | Primary financial management view: chronological income/expense ledger, Cashfree vs manual filters, date range filters. | **KEEP** (Module 3) |
| **6** | **Add Transaction** | `/admin/money-management/add` | `GET, POST` | `admin/money_management_add.html` | **Active** | Secondary supporting view: form to manually record income or expense into the financial ledger. | **KEEP** (Module 3 Supporting) |
| **7** | **Edit Transaction** | `/admin/money-management/transactions/<int:txn_id>/edit` | `GET, POST` | `admin/money_management_edit.html` | **Active** | Secondary supporting view: form to edit existing manual transactions (tamper-protected: Cashfree records cannot be edited). | **KEEP** (Module 3 Supporting) |

---

## 3. Active Admin Action & API Endpoints (Non-HTML)

These endpoints execute administrative logic and issue HTTP 302 redirects or return JSON. They do not render independent HTML templates:

| No. | Endpoint Name | URL Path | Methods | Output Type | Security & Guardrails |
| :---: | :--- | :--- | :---: | :---: | :--- |
| 1 | `admin.admin_login` | `/admin/login` | `GET, POST` | 302 Redirect | Safe compatibility redirect to canonical `/login?next=/admin/`. |
| 2 | `admin.toggle_job` | `/admin/jobs/toggle/<int:job_id>` | `POST` | 302 Redirect | Toggles job active/inactive state; redirects to `admin.jobs`. CSRF protected. |
| 3 | `admin.toggle_job_updated` | `/admin/jobs/toggle-updated/<int:job_id>` | `POST` | 302 Redirect | Alternative toggle endpoint; redirects to `admin.jobs`. CSRF protected. |
| 4 | `admin.delete_job` | `/admin/jobs/delete/<int:job_id>` | `POST` | 302 Redirect | Safely deletes a single job posting; redirects to `admin.jobs`. CSRF protected. |
| 5 | `admin.delete_all_jobs` | `/admin/jobs/delete-all` | `POST` | 302 Redirect | Bulk deletion guard requiring explicit `DELETE` confirmation code. |
| 6 | `admin.create_money_transaction` | `/admin/money-management/transactions/create` | `POST` | 302 Redirect | Form submission target for manual transaction creation. |
| 7 | `admin.delete_money_transaction` | `/admin/money-management/transactions/<int:txn_id>/delete` | `POST` | 302 Redirect | Deletes manual transaction (Cashfree automatic records strictly locked). |
| 8 | `admin.get_money_transaction_detail` | `/admin/money-management/transactions/<int:txn_id>` | `GET` | **JSON** | Administrative inspection API returning transaction details in JSON format. |
| 9 | `admin.reconcile_payments` | `/admin/money-management/reconcile` | `POST` | 302 Redirect | Triggers idempotent reconciliation between Cashfree payments and ledger. |
| 10 | `admin.clear_all_money_transactions` | `/admin/money-management/transactions/clear-all` | `POST` | 302 Redirect | Destructive ledger reset requiring exact `CLEAR` confirmation code. |

---

## 4. Retired Admin Modules & Decommissioned Pages

The following five modules have been completely retired from the Anti-Matrix admin interface. Their templates have been removed from disk, and their routes redirect cleanly to `/admin/dashboard`:

### Summary of Retired Modules:

| Retired Module | Former Purpose | Former Templates (Decommissioned) | Current Routing Behavior | Data Safety in Database |
| :--- | :--- | :--- | :--- | :--- |
| **Candidate Applications** | Managing job applicant resumes, statuses, shortlisting, and hiring. | `applications.html`<br>`application_detail.html` | `/admin/applications*`<br>Redirects to `/admin/dashboard` | **100% Preserved** in `job_applications` table. Public application intake and candidate portal remain active. |
| **Employee Management** | Managing employee profiles, credentials, onboarding, and departments. | `employees.html`<br>`employee_detail.html`<br>`create_employee.html`<br>`employee_create.html`<br>`employee_credentials.html` | `/admin/employees*`<br>Redirects to `/admin/dashboard` | **100% Preserved** in `employees` table. Active employee operations moved to Internship Portal (`intern.antimatrix.co.in`). |
| **Document & Email Templates** | Managing docx master templates, email templates, offer letters. | `templates.html`<br>`offer_letter_generate.html`<br>`offer_letter_verify.html`<br>`document_preview.html`<br>`preview_error.html` | `/admin/templates*`<br>`/admin/documents*`<br>Redirects to `/admin/dashboard` | **100% Preserved** in `document_templates` table. Automated letter generation logic preserved in services. |
| **Contact Inquiries** | Viewing and marking contact form messages from `/contact`. | `inquiries.html` | `/admin/inquiries*`<br>Redirects to `/admin/dashboard` | **100% Preserved** in `contact_inquiries` table. Public contact form continues saving inquiries. |
| **Internship Benefits** | Editing 1-month and 3-month stipend, certificate, and perk copy. | `internship_benefits.html`<br>`internship_benefit_form.html` | `/admin/internship-benefits*`<br>Redirects to `/admin/dashboard` | **100% Preserved** in `internship_benefits` table. Configured benefits continue rendering on public `/careers`. |

---

## 5. Quantitative Admin Summary

| Metric | Count | Details |
| :--- | :---: | :--- |
| **Total Registered Admin Route Rules** | **78** | All rules under `/admin*` prefix. |
| **Active Admin Route Rules** | **19** | 3 Dashboard rules, 7 Job Postings rules, 8 Money Management rules, 1 Login rule. |
| **Retired Admin Route Rules** | **59** | 14 path-based redirect rules + 45 legacy endpoint alias redirect rules. |
| **Active Admin HTML Templates** | **7** | `dashboard.html`, `jobs.html`, `create_job.html`, `edit_job.html`, `money_management.html`, `money_management_add.html`, `money_management_edit.html`. |
| **Retired Admin HTML Templates** | **0** | All 15 retired templates removed from disk. |
| **Unused Admin Templates** | **0** | Every template on disk is actively rendered by a primary route. |
| **Broken `url_for()` References** | **0** | Verified: all 70 template link references resolve cleanly to active endpoints. |
| **Pages with Broken Dependencies** | **0** | All models, queries, and services compile and execute without errors. |

---

## 6. Verification Findings & Operational Stability

1. **Clean 3-Tab Navigation Bar:** The `<div class="admin-nav-tabs">` element is identically structured across all 7 retained templates, displaying strictly:
   - `Overview` (`admin.dashboard`)
   - `Job Postings` (`admin.jobs`)
   - `Money Management` (`admin.money_management`)
2. **Desktop & Mobile Navbar Isolation:** The site-wide navigation dropdown and mobile navigation drawer display strictly the 3 active admin links.
3. **Graceful Legacy Redirects:** Any attempt by an administrator or cached browser bookmark to open `/admin/applications`, `/admin/employees`, `/admin/inquiries`, etc., triggers an HTTP 302 redirect to `/admin/dashboard` accompanied by a user-friendly notice: *"This administrative module has been retired."*
4. **Data Integrity:** No database columns or records were modified or deleted during the admin streamlining.
