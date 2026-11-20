# ANTI-MATRIX — WEBSITE CLEANUP & REFINEMENT RECOMMENDATIONS

**Domain:** https://antimatrix.co.in  
**Audit Type:** Pre-SEO Website Optimization & Cleanup Plan  
**Date:** November 19, 2026  
**Status:** **INVESTIGATION & RECOMMENDATIONS ONLY — NO FILES MODIFIED**

---

## 1. Executive Summary

Following the streamlining of the administrative panel into three core modules (Overview, Job Postings, and Money Management), this audit evaluated the entire codebase, templates, routes, and static assets to identify:
1. Obsolete or orphan templates that can be safely archived or removed.
2. Missing media assets that currently return HTTP 404 errors on the live website.
3. Unused large static assets and abandoned third-party vendor libraries.
4. Conflicting duplicate URL aliases that undermine search engine crawl efficiency.
5. Missing critical technical SEO infrastructure (`robots.txt` and `sitemap.xml`).

All proposed actions are classified with risk levels, dependencies checked, and impact assessments. **No changes have been implemented; these recommendations await explicit user approval.**

---

## 2. Priority 1 — Urgent Fixes: Broken Media & Missing SEO Infrastructure

### A. Broken Video Assets on `/brand-film` (Live HTTP 404)
- **Verified Finding:** On the live website at `https://antimatrix.co.in/brand-film`, the HTML `<video>` player attempts to load:
  - `static/videos/anti_matrix_brand_film.mp4` -> **HTTP 404 Not Found**
  - `static/videos/anti_matrix_brand_film.webm` -> **HTTP 404 Not Found**
- **Root Cause:** The video container template (`templates/pages/brand_film.html`) references MP4 and WebM video files, but only raw unreferenced audio files (`anti_matrix_film_audio.wav` and `anti_matrix_film_audio.m4a`) exist in `static/videos/`.
- **Impact:** Visitors and search engines visiting `/brand-film` encounter an unplayable, broken video container with 404 network errors in the browser console.
- **Recommendations:**
  - *Option 1 (Preferred if video is ready):* Upload the finalized, compressed `anti_matrix_brand_film.mp4` and `anti_matrix_brand_film.webm` files into `static/videos/`.
  - *Option 2 (If video is not produced yet):* Replace the broken video player in `templates/pages/brand_film.html` with an elegant "Brand Film Coming Soon" teaser card, or temporarily redirect `/brand-film` (302) to the homepage until the video is rendered.

### B. Missing `robots.txt` & `sitemap.xml` (Live HTTP 404)
- **Verified Finding:**
  - `https://antimatrix.co.in/robots.txt` -> **HTTP 404 Not Found**
  - `https://antimatrix.co.in/sitemap.xml` -> **HTTP 404 Not Found**
- **Impact:** Search engine crawlers (Googlebot, Bingbot) cannot discover canonical site structure, resulting in suboptimal crawl budgets and indexation delays.
- **Recommendation:** Implement dynamic or static `robots.txt` and `sitemap.xml` routes in Flask (or Nginx) during the upcoming SEO implementation phase. Ensure private paths (`/admin/`, `/profile`, `/my-applications/`, `/payment/`) are disallowed from crawling.

---

## 3. Priority 2 — Unused Templates & Orphan Development Files

### A. Orphan Template: `templates/pages/font_test.html`
- **File:** `templates/pages/font_test.html` (154 lines)
- **Purpose:** A development-only HTML document created during brand design to test Google Fonts (Audiowide, Bruno Ace, Chakra Petch, Michroma, Orbitron, Oxanium, Syncopate, Syne) against the Anti-Matrix logo wordmark.
- **Dependencies Checked:**
  - Registered Flask routes: **None**
  - Jinja `include` / `extends` calls: **None**
  - Internal navigation links: **None**
- **Classification:** **Confirmed Unused**
- **Recommendation:** Safely delete `templates/pages/font_test.html`. It has zero runtime dependencies and does not belong in production.

---

## 4. Priority 3 — Unreferenced Large Assets & Abandoned Vendor Libraries

A complete scan of `static/` revealed 25 unreferenced assets, totaling **~10.5 MB** of unnecessary disk storage and git repository weight:

| Asset Path | Size | Reason Unused / Former Purpose | Recommendation |
| :--- | :---: | :--- | :--- |
| `static/videos/anti_matrix_film_audio.wav` | **7.58 MB** | Raw uncompressed WAV master audio. Not referenced in any HTML/CSS/JS file. Served publicly at HTTP 200. | **Archive or Delete**. If needed for video production, store in external cloud backup, not in production webroot. |
| `static/videos/anti_matrix_film_audio.m4a` | **650 KB** | Raw M4A audio. Unreferenced in any HTML/CSS/JS file. | **Archive or Delete**. |
| `static/js/vendor/jszip.js`<br>`static/js/vendor/jszip.min.js` | **483 KB** (combined) | Leftover client-side zip library originally included for the retired in-browser DOCX preview feature. Zero code references. | **Safe to Delete**. |
| `static/js/vendor/docx-preview.js`<br>`static/js/vendor/docx-preview.min.js` | **180 KB** (combined) | Leftover docx-preview client library from retired document templates module. Zero code references. | **Safe to Delete**. |
| `static/default_templates/offer letter (Anti-matrix) with pages removed (1).docx` | **252 KB** | Duplicate of `offer_letter_ai_ml_master.docx` with unstandardized filename (spaces and parentheses). `services/offer_letter_service.py` uses the standard filename. | **Safe to Delete**. |
| `static/images/qmatrix_logo.png`<br>`static/images/qmatrix_mark.png` | **169 KB** (combined) | Q-Matrix corporate branding assets inadvertently saved in the Anti-Matrix website static folder. Anti-Matrix templates use `components/logo.html` and `static/images/logo.png`. | **Move to Q-Matrix repository or Delete**. |
| `static/images/logo_cropped_original.png`<br>`static/images/logo_transparent.png`<br>`static/images/anti_matrix_full_logo_transparent.png`<br>`static/images/anti_matrix_wordmark_transparent.png`<br>`static/images/anti_matrix_tagline_transparent.png` | **320 KB** (combined) | Redundant legacy PNG logo cuts. Active site uses vector `components/logo.html`, `static/favicon.svg`, and `static/images/logo.png`. | **Propose for Archival/Cleanup**. |
| `static/images/home_svc_ai.jpg`<br>`static/images/home_svc_marketing.jpg`<br>`static/images/home_svc_mobile.jpg`<br>`static/images/home_svc_web.jpg` | **2.2 MB** (combined) | High-resolution background service stock images that were superseded by modern CSS gradient cards and SVG icons. | **Investigate**. Confirm design preference before deleting. |

---

## 5. Priority 4 — Duplicate URL Aliases & Canonical Routing Standardization

Currently, several public pages are accessible under multiple URLs serving the exact same template with an HTTP 200 status code. This creates duplicate content risks in search engine indexes:

| Canonical Destination (Keep as Primary) | Redundant URL Alias | Current Behavior | Recommended Canonical Action |
| :--- | :--- | :---: | :--- |
| `https://antimatrix.co.in/products` | `/product` | Serves 200 OK | Implement HTTP 301 Redirect: `/product` -> `/products` |
| `https://antimatrix.co.in/privacy-policy` | `/privacy` | Serves 200 OK | Choose canonical (e.g. `/privacy-policy`) and 301 redirect `/privacy` |
| `https://antimatrix.co.in/terms-and-conditions` | `/terms` | Serves 200 OK | Choose canonical (e.g. `/terms-and-conditions`) and 301 redirect `/terms` |
| `https://antimatrix.co.in/refund-policy` | `/refunds`<br>`/cancellation-refund` | Serves 200 OK | Choose canonical (`/refund-policy`) and 301 redirect legacy variants |
| `https://antimatrix.co.in/profile` | `/my-profile` | Serves 302 -> Login | Standardize internal links to `/profile`; 301 redirect `/my-profile` -> `/profile` |
| `https://antimatrix.co.in/contact` | `/contact/` | Serves 200 OK | Standardize strict slash routing via Nginx / Flask |

---

## 6. Priority 5 — Shared Dependencies to STRICTLY PRESERVE

During any future cleanup, the following components **must NOT be removed**, as they are critical dependencies for public candidate workflows or the separate Internship Portal:

1. **SQLAlchemy Models (`models/`):**
   - `Employee` & `EmployeeOnboardingCredential`: Required by the Internship Portal (`intern.antimatrix.co.in`).
   - `JobApplication` & `Payment`: Required by candidate tracking, public application forms, and Cashfree webhook reconciliation.
   - `MoneyTransaction`: Required by the retained Money Management module.
   - `InternshipBenefit`: Required for dynamically rendering benefits on `/careers`.
   - `ContactInquiry`: Required by the public contact form `/contact` and `/api/contact`.
2. **Backend Service Logic (`services/`):**
   - `services/offer_letter_service.py`: Required by `/my-applications/<id>/document/<doc_type>` when candidates download offer letters.
   - `services/document_preview_service.py`: Required for server-side docx-to-pdf conversion.
   - `services/internship_benefit_service.py`: Required for default benefit seeding and `/careers` rendering.
   - `services/money_service.py`: Core engine for Money Management ledger and Cashfree reconciliation.
3. **Master Document Templates (`static/default_templates/`):**
   - `offer_letter_ai_ml_master.docx`
   - `offer_letter_app_development_master.docx`
   - `offer_letter_data_analytics_master.docx`
   - `offer_letter_web_development_master.docx`
   All four files are required by `services/offer_letter_service.py` to generate candidate offer letters.

---

## 7. Recommended Staged Cleanup Execution Plan

```
Phase 1: Zero-Risk Asset & Template Pruning (Post-Approval)
├── Delete orphan development template: templates/pages/font_test.html
├── Delete unreferenced vendor scripts: static/js/vendor/jszip* and docx-preview* (~663 KB)
├── Delete unstandardized duplicate template: static/default_templates/offer letter (...).docx (252 KB)
└── Remove or archive external branding assets: static/images/qmatrix_* (169 KB)

Phase 2: Media & User Experience Repair
├── Resolve /brand-film video assets (Upload compressed MP4/WebM or replace with teaser)
└── Move unreferenced 7.58 MB WAV file (static/videos/anti_matrix_film_audio.wav) out of production webroot

Phase 3: SEO Canonical Infrastructure (Part of SEO Implementation)
├── Add 301 permanent redirects for duplicate URL aliases (/product, /refunds, /privacy, etc.)
├── Deploy robots.txt with disallow rules for /admin/ and /payment/
└── Deploy dynamic XML sitemap covering canonical public URLs only
```
