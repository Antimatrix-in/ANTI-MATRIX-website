# Anti-Matrix Website — Unwanted and Duplicate Pages Report

**Audit Date:** November 18, 2026  
**Auditor:** Senior Technical SEO Auditor & Full-Stack Reviewer  
**Target:** https://antimatrix.co.in  

---

## 1. Classification Methodology

In accordance with strict production safety rules, no files or routes are automatically removed. Every page and route is classified into one of the following strategic actions:

- **KEEP**: Core, functional, high-value page requiring no architectural routing changes.
- **IMPROVE**: High-value page that needs metadata, canonical tags, asset fixes, or content polish.
- **MERGE**: Content overlap exists between two or more pages; content should be consolidated.
- **REDIRECT**: Duplicate URL variant or deprecated endpoint that must return a permanent HTTP 301 redirect to the canonical URL.
- **NOINDEX**: Functional internal, administrative, or authentication page that must be excluded from search engine indexation via `<meta name="robots" content="noindex, nofollow">` and `robots.txt`.
- **REVIEW FOR REMOVAL**: Unreferenced, orphaned, development, or backup file that serves no production purpose and should be reviewed for safe removal.

---

## 2. Page Inventory and Action Register

| Page / Route / File | Current Status | Content / Purpose | Recommended Action | Justification |
| :--- | :--- | :--- | :--- | :--- |
| **`/`** | HTTP 200 | Homepage & primary brand landing | **IMPROVE** | Core page; needs page-specific meta description, canonical tag, and WebP image optimization. |
| **`/about`** | HTTP 200 | Corporate story, mission, and leadership | **IMPROVE** | Core page; needs unique meta description and canonical tag. |
| **`/services`** | HTTP 200 | Engineering services catalog | **IMPROVE** | Core page; needs structured data (Service schema) and unique meta description. |
| **`/products`** | HTTP 200 | Software products (QMatrix, POS, ERP, Biometrics) | **IMPROVE** | Canonical product showcase; needs clean outbound links (remove UTM ChatGPT tag). |
| **`/product`** | HTTP 200 | Exact duplicate route for products | **REDIRECT** | 301 redirect to `/products` to eliminate duplicate content indexation. |
| **`/pricing`** | HTTP 301 | Deprecated pricing route (redirects to `/services`) | **KEEP** | Clean 301 redirect preserved for legacy bookmarks. |
| **`/careers`** | HTTP 200 | Job postings and internship listings | **IMPROVE** | Core page; needs JobPosting schema markup and canonical tag. |
| **`/brand-film`** | HTTP 200 | Brand film landing page | **REVIEW FOR REMOVAL** / **IMPROVE** | Orphan page not linked in navigation; media files (`.mp4`, `.webm`) return 404. Upload video assets or 301 redirect to `/about`. |
| **`/contact`** | HTTP 200 | Contact inquiry form | **IMPROVE** | Core page; needs canonical tag. Unify trailing slash behavior with `/contact/`. |
| **`/login`** | HTTP 200 | User and administrative login | **NOINDEX** | Authentication portal. Must not be indexed by Google; add `noindex, nofollow`. |
| **`/signup`** | HTTP 200 | Candidate account registration | **NOINDEX** | User onboarding page. Add `noindex, nofollow` to prevent thin content indexing. |
| **`/profile`** | HTTP 302 | User profile dashboard (requires auth) | **NOINDEX** | Internal user portal. Disallow in `robots.txt` and ensure `noindex`. |
| **`/my-profile`** | HTTP 302 | Alias for `/profile` | **REDIRECT** | 301 redirect to `/profile` to avoid route fragmentation. |
| **`/my-applications`**| HTTP 302 | Candidate application tracker (requires auth) | **NOINDEX** | Internal user portal. Disallow in `robots.txt`. |
| **`/privacy-policy`**| HTTP 200 | Official legal privacy policy | **IMPROVE** | Canonical legal page; add canonical tag. |
| **`/privacy`** | HTTP 200 | Duplicate privacy policy route | **REDIRECT** | 301 redirect to `/privacy-policy`. |
| **`/terms-and-conditions`** | HTTP 200 | Official terms of service | **IMPROVE** | Canonical legal page; add canonical tag. |
| **`/terms`** | HTTP 200 | Duplicate terms route | **REDIRECT** | 301 redirect to `/terms-and-conditions`. |
| **`/refunds`** | HTTP 200 | Cancellation and refund policy | **IMPROVE** | Canonical legal page; add canonical tag. |
| **`/refund-policy`**| HTTP 200 | Duplicate refund policy route | **REDIRECT** | 301 redirect to `/refunds`. |
| **`/cancellation-refund`** | HTTP 200 | Duplicate refund policy route | **REDIRECT** | 301 redirect to `/refunds`. |
| **`/careers/apply/<id>`** | HTTP 200 | Job application form | **NOINDEX** | User input workflow. Add `noindex` so Google does not index transient form pages. |
| **`templates/pages/font_test.html`** | Unrouted | Font comparison test template | **REVIEW FOR REMOVAL** | Development scratch template. Not routed or referenced anywhere in production. |
| **`templates/admin/employee_create.html`** | Unrouted | Legacy employee creation form | **REVIEW FOR REMOVAL** | Superseded by `templates/admin/create_employee.html`. Never rendered by Flask. |
| **`templates/admin/employee_credentials.html`** | Unrouted | Legacy employee credentials template | **REVIEW FOR REMOVAL** | Superseded by modal rendering in `application_detail.html`. |
| **`routes/auth.py.bak`** | File | Backup file left in routes directory | **REVIEW FOR REMOVAL** | 18.6KB backup file. Development artifact that should be removed from repository. |
| **`tests/test_admin_login_routing.py.bak`** | File | Backup test file | **REVIEW FOR REMOVAL** | Backup file; should be archived or removed. |
| **`routes/contact.py`** | Active Blueprint | `/api/contact` endpoint | **MERGE** | Redundant; `POST /contact` in `routes/main.py` handles all frontend form submissions. |

---

## 3. Detailed Analysis of Problematic Categories

### 3.1 Duplicate Legal & Content Routes
The application registers multiple identical endpoints for legal and product pages:
- **Product:** `/product` and `/products` both return HTTP 200 with identical HTML.
- **Privacy:** `/privacy` and `/privacy-policy` both return HTTP 200 with identical HTML.
- **Terms:** `/terms` and `/terms-and-conditions` both return HTTP 200 with identical HTML.
- **Refunds:** `/refund-policy`, `/cancellation-refund`, and `/refunds` all return HTTP 200 with identical HTML.

**Impact:** Search engines treat each duplicate URL as a separate page with 100% identical content, diluting keyword relevance and risking duplicate content penalties.

**Solution:** Standardize on canonical paths (`/products`, `/privacy-policy`, `/terms-and-conditions`, `/refunds`) and issue permanent HTTP 301 redirects for all aliases.

---

### 3.2 Orphaned Brand Film Page (`/brand-film`)
- **Discovery:** The route is registered in `routes/main.py` (`@main_bp.route('/brand-film')`).
- **Internal Links:** 0 links point to `/brand-film` across the entire website.
- **Assets:** The template references `videos/anti_matrix_brand_film.mp4` and `videos/anti_matrix_brand_film.webm`. Both files do not exist on the server, returning HTTP 404.
- **Recommendation:** If the brand film is not ready, either disable the route or 301 redirect it to `/about`. If ready, upload optimized MP4/WebM video files to `static/videos/` and link the page from the footer.

---

### 3.3 Development & Backup Files Left in Repository
- `routes/auth.py.bak` (18.6 KB) — Static backup file inside the application routes directory.
- `tests/test_admin_login_routing.py.bak` — Backup file in the test suite directory.
- `templates/pages/font_test.html` (6.1 KB) — Unrouted scratch file testing Google Fonts against the logo.
- `templates/admin/employee_create.html` (9.9 KB) — Unreferenced legacy template.
- `templates/admin/employee_credentials.html` (12.1 KB) — Unreferenced legacy template.

**Recommendation:** Move all `.bak` and scratch files to an external archive or delete them during the cleanup phase. None of these files are required for website functionality.
