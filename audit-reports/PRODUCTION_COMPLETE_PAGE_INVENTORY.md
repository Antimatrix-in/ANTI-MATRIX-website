# ANTI-MATRIX — PRODUCTION COMPLETE PAGE INVENTORY & ROUTE AUDIT

**Domain:** https://antimatrix.co.in  
**Audit Type:** Production Full-Stack Route & Page Inventory  
**Date:** November 19, 2026  
**Status:** READ-ONLY Complete Audit  
**Total Registered Routes:** 126  
**Total HTML Templates on Disk:** 38  
**Total Routable Unique HTML Pages:** 29  

---

## 1. Executive Summary & Methodology

This report provides an exhaustive, verified catalog of every URL, route handler, view function, and HTML page registered in the Anti-Matrix production Flask application (`/var/www/anti-matrix`).

### Counting Methodology & Distinction
To avoid ambiguity, the audit explicitly distinguishes between:
1. **Registered Flask Route Rules:** A URL pattern registered in `app.url_map`. Multiple route rules may point to the same view function (URL aliases).
2. **Unique HTML Pages:** Standalone user-facing HTML views rendered by a view function that return an HTTP 200 HTML response. Component templates (`base.html`, `navbar.html`, `footer.html`, `icons.html`, `logo.html`) are partials and excluded from page counts.
3. **URL Aliases:** Alternative URL paths mapped to the exact same view function and template (e.g., `/products` and `/product`, `/terms` and `/terms-and-conditions`).
4. **Action / Mutation Endpoints:** POST-only endpoints that process data and issue HTTP 302 redirects without rendering an HTML page (e.g., `/admin/jobs/toggle/<id>`).
5. **API & Webhook Endpoints:** Routes that consume or return raw JSON or handle asynchronous server-to-server callbacks (e.g., `/api/health`, `/payment/cashfree/webhook`).
6. **Redirect-Only Routes:** Endpoints whose sole behavior is to issue an HTTP 301 or 302 redirect to another canonical destination (e.g., `/pricing` -> `/services`, `/admin/applications` -> `/admin/dashboard`).

---

## 2. Exact Page & Route Quantity Breakdown

| Category | Exact Count | Description / Methodology |
| :--- | :---: | :--- |
| **Total Registered Flask Routes** | **126** | Total rules in `app.url_map` across all blueprints. |
| **Total HTML Template Files** | **38** | All `.html` files in `templates/` (including components and errors). |
| **Routable Unique HTML Pages** | **29** | Unique page views backed by distinct Jinja templates. |
| **A. Public HTML Pages** | **10** | Home, About, Services, Products, Careers, Contact, Privacy, Terms, Refund Policy, Brand Film. |
| **B. Authenticated User Pages** | **3** | User Profile, My Applications List, My Application Detail. |
| **C. Admin-Only HTML Pages** | **7** | Dashboard, Jobs List, Create Job, Edit Job, Money Management, Add Txn, Edit Txn. |
| **D. Employee/Internship Pages** | **0** | Fully migrated to Internship Portal (`intern.antimatrix.co.in`). Legacy routes redirect. |
| **E. Authentication Pages** | **2** | Login (`/login`), Signup (`/signup`). |
| **F. Candidate Application Pages** | **4** | Job Apply Form (Manual/Automated), Application Review, Application Success. |
| **G. Payment-Related Pages** | **3** | Cashfree Checkout, Payment Pending, Payment Failed. |
| **H. API Endpoints** | **5** | Health Check (`/api/health`), Contact API (`/api/contact`), Txn Detail API, Checkout JSON. |
| **I. Webhook Endpoints** | **1** | Cashfree Asynchronous Webhook (`/payment/cashfree/webhook`). |
| **J. Redirects & Legacy Aliases** | **83** | 59 retired admin redirects, 7 URL aliases, 1 pricing 301, 6 OAuth flows, 10 action redirects. |
| **K. Error & Utility Endpoints** | **5** | 3 Error templates (403, 404, 500) + 2 static asset routes (`/static/`, `/assets/`). |
| **Duplicate / Conflicting URL Aliases** | **6 Pairs** | `/product` & `/products`, `/privacy` & `/privacy-policy`, `/terms` & `/terms-and-conditions`, `/refund-policy` & `/refunds` & `/cancellation-refund`, `/profile` & `/my-profile`, `/contact` & `/contact/`. |

---

## 3. Complete Route Inventory by Classification

### Category A: Public HTML Pages (10 Unique Pages, 17 Route Rules)

| No. | URL Rule | HTTP Methods | Endpoint | Template Rendered | Live Status | Canonical Status |
| :---: | :--- | :---: | :--- | :--- | :---: | :--- |
| 1 | `/` | `GET` | `main.home` | `pages/home.html` | 200 OK | Canonical homepage |
| 2 | `/about` | `GET` | `main.about` | `pages/about.html` | 200 OK | Canonical |
| 3 | `/services` | `GET` | `main.services` | `pages/services.html` | 200 OK | Canonical |
| 4 | `/products` | `GET` | `main.products` | `pages/products.html` | 200 OK | Canonical products page |
| 5 | `/product` | `GET` | `main.products` | `pages/products.html` | 200 OK | **Duplicate Alias** (Should 301 redirect to `/products`) |
| 6 | `/careers` | `GET` | `main.careers` | `pages/careers.html` | 200 OK | Canonical careers page |
| 7 | `/contact` | `GET, POST` | `main.contact` | `pages/contact.html` | 200 OK | Canonical contact form |
| 8 | `/contact/` | `GET, POST` | `main.contact` | `pages/contact.html` | 200 OK | Trailing slash alias |
| 9 | `/privacy` | `GET` | `main.privacy` | `pages/privacy.html` | 200 OK | Short alias |
| 10 | `/privacy-policy` | `GET` | `main.privacy` | `pages/privacy.html` | 200 OK | **Duplicate Alias** (Needs explicit canonical) |
| 11 | `/terms` | `GET` | `main.terms` | `pages/terms.html` | 200 OK | Short alias |
| 12 | `/terms-and-conditions` | `GET` | `main.terms` | `pages/terms.html` | 200 OK | **Duplicate Alias** (Needs explicit canonical) |
| 13 | `/refund-policy` | `GET` | `main.refund_policy` | `pages/refund_policy.html` | 200 OK | Canonical refund page |
| 14 | `/refunds` | `GET` | `main.refund_policy` | `pages/refund_policy.html` | 200 OK | Short alias |
| 15 | `/cancellation-refund` | `GET` | `main.refund_policy` | `pages/refund_policy.html` | 200 OK | Legacy alias |
| 16 | `/brand-film` | `GET` | `main.brand_film` | `pages/brand_film.html` | 200 OK | Brand film page (**Media 404 issue: MP4/WebM missing**) |
| 17 | `/pricing` | `GET` | `main.pricing` | *(None - 301 Redirect)* | 301 -> `/services` | Permanent redirect |

---

### Category B: Authenticated User Pages (3 Unique Pages, 4 Route Rules)

| No. | URL Rule | HTTP Methods | Endpoint | Auth Required | Template Rendered | Live Status (Guest) |
| :---: | :--- | :---: | :--- | :---: | :--- | :---: |
| 1 | `/profile` | `GET, POST` | `main.profile` | `@login_required` | `pages/profile.html` | 302 -> `/login?next=/profile` |
| 2 | `/my-profile` | `GET, POST` | `main.profile` | `@login_required` | `pages/profile.html` | 302 -> `/login?next=/my-profile` |
| 3 | `/my-applications` | `GET` | `main.my_applications` | `@login_required` | `pages/my_applications.html` | 302 -> `/login?next=/my-applications` |
| 4 | `/my-applications/<int:app_id>` | `GET` | `main.my_application_detail` | `@login_required` | `pages/my_application_detail.html` | 302 -> `/login?next=...` |

---

### Category C: Admin-Only HTML Pages (7 Unique Pages, 10 Route Rules)

| No. | URL Rule | HTTP Methods | Endpoint | Auth Required | Template Rendered | Module |
| :---: | :--- | :---: | :--- | :---: | :--- | :--- |
| 1 | `/admin` | `GET` | `admin.dashboard` | `@admin_required` | `admin/dashboard.html` | Overview |
| 2 | `/admin/` | `GET` | `admin.dashboard` | `@admin_required` | `admin/dashboard.html` | Overview |
| 3 | `/admin/dashboard` | `GET` | `admin.dashboard` | `@admin_required` | `admin/dashboard.html` | Overview |
| 4 | `/admin/jobs` | `GET` | `admin.jobs` | `@admin_required` | `admin/jobs.html` | Job Postings |
| 5 | `/admin/jobs/create` | `GET, POST` | `admin.create_job` | `@admin_required` | `admin/create_job.html` | Job Postings |
| 6 | `/admin/jobs/edit/<int:job_id>` | `GET, POST` | `admin.edit_job` | `@admin_required` | `admin/edit_job.html` | Job Postings |
| 7 | `/admin/money-management` | `GET` | `admin.money_management` | `@admin_required` | `admin/money_management.html` | Money Management |
| 8 | `/admin/money-management/add` | `GET, POST` | `admin.add_money_transaction` | `@admin_required` | `admin/money_management_add.html` | Money Management |
| 9 | `/admin/money-management/transactions/<int:txn_id>/edit` | `GET, POST` | `admin.edit_money_transaction` | `@admin_required` | `admin/money_management_edit.html` | Money Management |
| 10 | `/admin/login` | `GET, POST` | `admin.admin_login` | Public | *(Redirects to `/login?next=/admin/`)* | Auth Compatibility |

---

### Category D: Employee & Internship Management Pages (0 on Main Site)

All active employee management, credential creation, and onboarding operations have been moved to the dedicated **Internship Portal** at `https://intern.antimatrix.co.in`. The Anti-Matrix main website retains no active employee management views. Legacy routes redirect cleanly to `/admin/dashboard`.

---

### Category E: Authentication & Registration Pages (2 Unique Pages, 9 Route Rules)

| No. | URL Rule | HTTP Methods | Endpoint | Template / Action | Live Status |
| :---: | :--- | :---: | :--- | :--- | :---: |
| 1 | `/login` | `GET, POST` | `auth.login` | `auth/login.html` | 200 OK |
| 2 | `/signup` | `GET, POST` | `auth.signup` | `auth/signup.html` | 200 OK |
| 3 | `/logout` | `GET, POST` | `auth.logout` | Redirect to `/` | 302 -> `/` |
| 4 | `/login/google` | `GET` | `auth.google_login` | Google OAuth redirect | 302 -> Google |
| 5 | `/auth/google` | `GET` | `auth.google_login` | Alias for Google OAuth | 302 -> Google |
| 6 | `/auth/google/callback` | `GET` | `auth.google_callback` | OAuth callback & session init | 302 |
| 7 | `/login/github` | `GET` | `auth.github_login` | GitHub OAuth redirect | 302 -> GitHub |
| 8 | `/auth/github` | `GET` | `auth.github_login` | Alias for GitHub OAuth | 302 -> GitHub |
| 9 | `/auth/github/callback` | `GET` | `auth.github_callback` | OAuth callback & session init | 302 |

---

### Category F: Job Application & Candidate Pages (4 Unique Pages, 7 Route Rules)

| No. | URL Rule | HTTP Methods | Endpoint | Template Rendered | Description |
| :---: | :--- | :---: | :--- | :--- | :--- |
| 1 | `/careers/apply/<int:job_id>` | `GET, POST` | `main.apply_job` | `pages/job_apply_manual.html` (or `job_apply.html`) | Candidate Application Form |
| 2 | `/careers/apply/review/<int:app_id>` | `GET` | `main.job_apply_review` | `pages/job_apply_review.html` | Review submission before payment |
| 3 | `/careers/apply/success/<int:app_id>` | `GET` | `main.job_apply_success` | `pages/job_apply_success.html` | Application Confirmation & Next Steps |
| 4 | `/careers/apply/retry-payment/<int:app_id>` | `GET` | `main.retry_payment` | Redirects to checkout / success | Payment retry action |
| 5 | `/careers/apply/checkout/<int:app_id>` | `POST` | `main.job_apply_checkout` | *(JSON / Redirect to Cashfree checkout)* | Order generation action |
| 6 | `/application/test-payment/<int:app_id>` | `POST` | `main.job_apply_test_payment` | Action (Test mode payment simulation) | Developer test endpoint |
| 7 | `/careers/apply/test-payment/<int:app_id>` | `POST` | `main.job_apply_test_payment` | Alias for test payment | Developer test endpoint |

---

### Category G: Payment & Transaction Pages (3 Unique Pages, 5 Route Rules)

| No. | URL Rule | HTTP Methods | Endpoint | Template Rendered | Live Status |
| :---: | :--- | :---: | :--- | :--- | :---: |
| 1 | `/payment/cashfree/checkout/<int:payment_id>` | `GET` | `main.cashfree_checkout_page` | `pages/payment_cashfree_checkout.html` | 200 (Active Session) |
| 2 | `/payment/pending/<int:payment_id>` | `GET` | `main.payment_pending_page` | `pages/payment_pending.html` | 200 |
| 3 | `/payment/failed/<int:payment_id>` | `GET` | `main.payment_failed_page` | `pages/payment_failed.html` | 200 |
| 4 | `/payment/cashfree/return` | `GET, POST` | `main.cashfree_return` | *(Verifies status & redirects)* | 302 |
| 5 | `/payment/cashfree/webhook` | `POST` | `main.cashfree_webhook` | *(Asynchronous webhook handler)* | JSON Response |

---

### Category H: API Endpoints (5 Routes)

| No. | URL Rule | HTTP Methods | Endpoint | Blueprint | Description |
| :---: | :--- | :---: | :--- | :--- | :--- |
| 1 | `/api/health` | `GET` | `health_check` | `app` | Health check (`{"status": "OK", "timestamp": "..."}`) |
| 2 | `/api/contact` | `POST` | `contact.api_contact` | `contact` | Asynchronous Contact Form Submission API |
| 3 | `/api/contact/` | `POST` | `contact.api_contact` | `contact` | Trailing slash alias for contact API |
| 4 | `/admin/money-management/transactions/<int:txn_id>` | `GET` | `admin.get_money_transaction_detail` | `admin` | Admin transaction inspection JSON API |
| 5 | `/my-applications/<int:app_id>/document/<string:doc_type>` | `GET` | `main.my_application_document` | `main` | Candidate document/offer letter download endpoint |

---

### Category I: Webhooks & Callbacks (1 Route)

| No. | URL Rule | HTTP Methods | Endpoint | CSRF Status | Security Verification |
| :---: | :--- | :---: | :--- | :---: | :--- |
| 1 | `/payment/cashfree/webhook` | `POST` | `main.cashfree_webhook` | **Exempt** | Verified via Cashfree cryptographic signature (`x-webhook-signature`). |

---

### Category J: Admin Action Endpoints & Retired Module Redirects (68 Routes)

#### 1. Active Admin Action Endpoints (9 Routes)
- `/admin/jobs/delete-all` [POST] -> `admin.delete_all_jobs`
- `/admin/jobs/toggle/<int:job_id>` [POST] -> `admin.toggle_job`
- `/admin/jobs/toggle-updated/<int:job_id>` [POST] -> `admin.toggle_job_updated`
- `/admin/jobs/delete/<int:job_id>` [POST] -> `admin.delete_job`
- `/admin/money-management/transactions/create` [POST] -> `admin.create_money_transaction`
- `/admin/money-management/transactions/<int:txn_id>/delete` [POST] -> `admin.delete_money_transaction`
- `/admin/money-management/reconcile` [POST] -> `admin.reconcile_payments`
- `/admin/money-management/transactions/clear-all` [POST] -> `admin.clear_all_money_transactions`
- `/admin/login` [GET, POST] -> `admin.admin_login`

#### 2. Retired Module Path-Based Redirects (14 Routes)
All redirect to `/admin/dashboard` with flash message:
- `/admin/applications` & `/admin/applications/<path:subpath>` & `/admin/applications/<int:app_id>` (3 routes)
- `/admin/employees` & `/admin/employees/<path:subpath>` & `/admin/employees/create` & `/admin/employees/<string:employee_id>` (4 routes)
- `/admin/templates` & `/admin/templates/<path:subpath>` & `/admin/documents/<path:subpath>` (3 routes)
- `/admin/internship-benefits` & `/admin/internship-benefits/<path:subpath>` (2 routes)
- `/admin/inquiries` & `/admin/inquiries/<path:subpath>` (2 routes)

#### 3. Retired Module Compatibility Endpoint Aliases (45 Routes)
All map to `_retired_stub` and redirect to `/admin/dashboard`:
- `/admin/_retired/clear_all_applications`
- `/admin/_retired/mark_application_under_review`
- `/admin/_retired/send_application_success_email_action`
- `/admin/_retired/mark_application_shortlisted`
- `/admin/_retired/mark_application_offer_complete`
- `/admin/_retired/mark_application_hired`
- `/admin/_retired/send_joining_email_action`
- `/admin/_retired/retry_shortlist_offer_email`
- `/admin/_retired/download_application_offer_letter`
- `/admin/_retired/preview_application_offer_letter_file`
- `/admin/_retired/preview_application_offer_letter_pdf`
- `/admin/_retired/preview_application_offer_letter`
- `/admin/_retired/preview_document_file_by_id`
- `/admin/_retired/preview_document_pdf_by_id`
- `/admin/_retired/preview_document_by_id`
- `/admin/_retired/update_application_status`
- `/admin/_retired/download_document`
- `/admin/_retired/download_resume`
- `/admin/_retired/update_application_payment_status`
- `/admin/_retired/admin_reset_employee_password`
- `/admin/_retired/update_email_template`
- `/admin/_retired/preview_email_template`
- `/admin/_retired/send_test_email_route`
- `/admin/_retired/upload_document_template`
- `/admin/_retired/create_template`
- `/admin/_retired/assign_job_to_template`
- `/admin/_retired/activate_document_template`
- `/admin/_retired/deactivate_document_template`
- `/admin/_retired/delete_document_template`
- `/admin/_retired/download_document_template_by_id`
- `/admin/_retired/preview_document_template_info`
- `/admin/_retired/download_document_template`
- `/admin/_retired/generate_offer_letter`
- `/admin/_retired/preview_offer_letter`
- `/admin/_retired/verify_offer_letter`
- `/admin/_retired/send_offer_letter`
- `/admin/_retired/add_internship_benefit`
- `/admin/_retired/edit_internship_benefit`
- `/admin/_retired/delete_internship_benefit`
- `/admin/_retired/reset_default_internship_benefits`
- `/admin/_retired/get_inquiry_detail`
- `/admin/_retired/toggle_inquiry_status`
- `/admin/_retired/delete_inquiry`
- `/admin/_retired/mark_all_inquiries_read`
- `/admin/_retired/delete_all_inquiries`

---

### Category K: Error & Utility Endpoints (5 Routes)

| No. | Route / Handler | Template / Behavior | HTTP Status |
| :---: | :--- | :--- | :---: |
| 1 | `errorhandler(403)` | `errors/403.html` | 403 Forbidden |
| 2 | `errorhandler(404)` | `errors/404.html` | 404 Not Found |
| 3 | `errorhandler(500)` | `errors/500.html` (or JSON if AJAX) | 500 Internal Server Error |
| 4 | `/static/<path:filename>` | Serves files from `static/` | 200 / 304 |
| 5 | `/assets/<path:filename>` | Fallback asset handler with logo redirect | 200 / 404 |

---

## 4. Complete Template File Mapping & Audit

| Template Path | Associated Routes | Purpose | Retention Recommendation |
| :--- | :--- | :--- | :--- |
| `base.html` | Master Jinja layout | Core master template | **Keep** (Core) |
| `components/navbar.html` | Included in `base.html` | Main navigation & mobile drawer | **Keep** (Core) |
| `components/footer.html` | Included in `base.html` | Site footer & links | **Keep** (Core) |
| `components/icons.html` | Imported in templates | Lucide SVG icon macros | **Keep** (Core) |
| `components/logo.html` | Included in navbar/footer | SVG brand logo | **Keep** (Core) |
| `pages/home.html` | `/` | Homepage | **Keep** (Public) |
| `pages/about.html` | `/about` | About company | **Keep** (Public) |
| `pages/services.html` | `/services`, `/pricing` (redirect) | Services list & pricing | **Keep** (Public) |
| `pages/products.html` | `/products`, `/product` | Products showcase | **Keep** (Public) |
| `pages/careers.html` | `/careers` | Job postings & benefits | **Keep** (Public) |
| `pages/contact.html` | `/contact`, `/contact/` | Contact inquiry form | **Keep** (Public) |
| `pages/privacy.html` | `/privacy`, `/privacy-policy` | Privacy policy legal | **Keep** (Public) |
| `pages/terms.html` | `/terms`, `/terms-and-conditions`| Terms of service | **Keep** (Public) |
| `pages/refund_policy.html` | `/refund-policy`, `/refunds`, `/cancellation-refund` | Refund policy legal | **Keep** (Public) |
| `pages/brand_film.html` | `/brand-film` | Corporate brand film | **Investigate** (Fix missing MP4 or retire) |
| `pages/font_test.html` | **None (Orphan)** | Development font tester | **Delete** (Unused debug template) |
| `pages/profile.html` | `/profile`, `/my-profile` | User dashboard & settings | **Keep** (Authenticated) |
| `pages/my_applications.html` | `/my-applications` | Candidate application history | **Keep** (Authenticated) |
| `pages/my_application_detail.html` | `/my-applications/<id>` | Candidate application detail | **Keep** (Authenticated) |
| `pages/job_apply_manual.html` | `/careers/apply/<job_id>` | Manual candidate application | **Keep** (Candidate workflow) |
| `pages/job_apply.html` | `/careers/apply/<job_id>` | Automated candidate application | **Keep** (Candidate fallback) |
| `pages/job_apply_review.html` | `/careers/apply/review/<id>` | Application review screen | **Keep** (Candidate workflow) |
| `pages/job_apply_success.html` | `/careers/apply/success/<id>`| Application success screen | **Keep** (Candidate workflow) |
| `pages/payment_cashfree_checkout.html` | `/payment/cashfree/checkout/<id>` | Cashfree hosted checkout | **Keep** (Payment) |
| `pages/payment_pending.html` | `/payment/pending/<id>` | Payment pending status screen | **Keep** (Payment) |
| `pages/payment_failed.html` | `/payment/failed/<id>` | Payment failure retry screen | **Keep** (Payment) |
| `auth/login.html` | `/login` | User login screen | **Keep** (Authentication) |
| `auth/signup.html` | `/signup` | User signup screen | **Keep** (Authentication) |
| `admin/dashboard.html` | `/admin`, `/admin/`, `/admin/dashboard` | Admin Overview dashboard | **Keep** (Admin Module 1) |
| `admin/jobs.html` | `/admin/jobs` | Job postings table & filters | **Keep** (Admin Module 2) |
| `admin/create_job.html` | `/admin/jobs/create` | New job posting form | **Keep** (Admin Module 2) |
| `admin/edit_job.html` | `/admin/jobs/edit/<id>` | Edit job posting form | **Keep** (Admin Module 2) |
| `admin/money_management.html` | `/admin/money-management` | Financial ledger & filters | **Keep** (Admin Module 3) |
| `admin/money_management_add.html` | `/admin/money-management/add` | Manual transaction form | **Keep** (Admin Module 3) |
| `admin/money_management_edit.html`| `/admin/money-management/transactions/<id>/edit` | Edit manual transaction | **Keep** (Admin Module 3) |
| `errors/403.html` | Error 403 | Forbidden page | **Keep** (Error) |
| `errors/404.html` | Error 404 | Page not found | **Keep** (Error) |
| `errors/500.html` | Error 500 | Server error | **Keep** (Error) |
