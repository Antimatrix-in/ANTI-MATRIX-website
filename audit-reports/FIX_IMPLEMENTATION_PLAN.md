# Anti-Matrix Website — Revised Fix Implementation Plan & SEO Remediation Roadmap

**Project:** Anti-Matrix Official Web Platform (`https://antimatrix.co.in`)  
**Document Version:** 2.0.0 (Production-Verified & Pre-Implementation Revised)  
**Status:** READY FOR STAKEHOLDER REVIEW — PENDING EXPLICIT APPROVAL  
**Safety Mandate:** ANALYZE & PLAN ONLY — Zero Code Modifications Until Explicit Approval  

---

## 1. Operational Safety Rules & Constraints

Every action in this implementation plan strictly adheres to the following production safety rules:

1. **Zero Database Modifications:**
   - Never run migrations, table drops, schema alterations, truncation, or destructive SQL.
   - All Supabase PostgreSQL data (`aws-0-ap-south-1.pooler.supabase.com:5432/postgres`) must remain 100% untouched.
2. **Preserve Production Startup Guards:**
   - Preserve `ALLOW_STARTUP_DB_INIT=false` on the Hostinger VPS.
   - Never overwrite the VPS `/var/www/anti-matrix/app.py` with an unguarded version.
3. **No Unsafe Deployment Commands:**
   - Never execute `git reset --hard` or `rsync --delete` on the production server.
   - Deployment must use `/usr/local/bin/anti-matrix-deploy`.
4. **Isolate Multi-Site VPS Infrastructure:**
   - The Hostinger Ubuntu 24.04 VPS hosts multiple web properties: `antimatrix.co.in`, `intern.antimatrix.co.in`, Q Matrix (`qmatrix.co.in`), EMS, and Teamwork Manpower.
   - Never use wildcard Nginx rules (e.g. `*.antimatrix.co.in`) or modify other site configurations.
5. **Zero Credential Exposure:**
   - Never commit, display, or transmit `.env` keys, Supabase credentials, Cashfree payment secrets, or SSH keys.
6. **Preserve Application & Auth Workflows:**
   - Candidate job application flow, Cashfree payment processing, user authentication, and admin dashboards must remain fully functional.

---

## 2. Architecture Overview & Track Separation

To ensure system stability, all tasks are divided into three distinct tracks:

```
+---------------------------------------------------------------------------------------------------+
|                                  IMPLEMENTATION TRACKS                                            |
+---------------------------------------------------------------------------------------------------+
|  TRACK 1: Core Technical SEO Infrastructure (Immediate Foundation)                                 |
|  - Step 1.1: robots.txt crawling protocol (clean crawling directives, zero security confusion)    |
|  - Step 1.2: Dynamic sitemap.xml (verified canonical URLs, single /careers entry, NO #fragments)  |
|  - Step 1.3: Explicit, safe canonical URL strategy (immutable domain constant, context processor)  |
|  - Step 1.4: Search engine indexation controls (noindex, nofollow on auth and application forms)  |
|  - Step 1.5: Hostinger VPS Nginx inspection, DNS/SSL check & safe www-to-apex 301 redirection     |
+---------------------------------------------------------------------------------------------------+
|  TRACK 2: Route Hygiene & Canonical Redirections (Routing Alignment)                              |
|  - Step 2.1: Align Flask route aliases preserving all url_for() and form dependencies             |
|  - Step 2.2: Enforce trailing slash consistency                                                   |
+---------------------------------------------------------------------------------------------------+
|  TRACK 3: Content, Schema & Asset Optimization (Subsequent Enhancements)                          |
|  - Step 3.1: Organization & WebSite JSON-LD structured data using verified company details        |
|  - Step 3.2: Dynamic per-template Title and Meta Description architecture                         |
|  - Step 3.3: External link hygiene (clean ChatGPT UTM parameter from products.html)               |
|  - Step 3.4: Brand Film media handling (embed streaming player or upload master file)             |
|  - Step 3.5: Non-destructive asset archiving protocol (protect JSZip and DOCX dependencies)       |
|  - Step 3.6: Dedicated Job Detail Architecture (prerequisite for valid Google JobPosting schema)  |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Track 1 — Core Technical SEO Infrastructure

### Step 1.1: Deploy `robots.txt` Crawling Protocol
- **Target Files:** `static/robots.txt`, `routes/main.py`
- **Dependencies:** None
- **Risk Level:** Low
- **Architectural Clarification:**
  - `robots.txt` is an indexing/crawling instruction for cooperative search spiders. It is **NOT an access control mechanism**.
  - Internal and authentication routes must be secured by backend middleware (`@login_required`, session authentication, CSRF tokens), not `robots.txt`.
  - Sensitive transactional forms (`/login`, `/signup`, `/careers/apply/*`) must be crawlable so spiders can read their `<meta name="robots" content="noindex, nofollow">` directives. Disallowing them in `robots.txt` would prevent Googlebot from seeing `noindex`, causing URLs to appear as indexed without snippets.
- **Specification:**
  1. Create `static/robots.txt`:
     ```txt
     User-agent: *
     Allow: /
     Disallow: /api/
     Disallow: /static/private/

     Sitemap: https://antimatrix.co.in/sitemap.xml
     ```
  2. In `routes/main.py`, register the route:
     ```python
     @main_bp.route('/robots.txt')
     def robots_txt():
         return send_from_directory(current_app.static_folder, 'robots.txt', mimetype='text/plain')
     ```
- **Testing & Verification Procedures:**
  ```bash
  # Local Test:
  curl -I http://127.0.0.1:8017/robots.txt
  # Verify status HTTP 200, Content-Type: text/plain

  # Production Test:
  curl -I https://antimatrix.co.in/robots.txt
  ```
- **Rollback Procedure:** Remove the route in `routes/main.py` and delete `static/robots.txt`.
- **Acceptance Criteria:** `curl https://antimatrix.co.in/robots.txt` returns `HTTP 200 OK`, `text/plain`, contains `Sitemap: https://antimatrix.co.in/sitemap.xml`, and does not block auth/form pages.

---

### Step 1.2: Dynamic `sitemap.xml` Generation
- **Target Files:** `routes/main.py`, `templates/seo/sitemap.xml`
- **Dependencies:** `models.JobPosting` (read-only query)
- **Risk Level:** Low
- **Architectural Requirements:**
  1. **Strict Exclusion of URL Fragments:** Sitemaps protocol (sitemaps.org) explicitly forbids URI fragments (`#...`). Fragments are client-side anchors stripped by search engines. Never output `/careers#job-123`.
  2. **Single Careers Hub Entry:** Because Anti-Matrix currently displays active jobs as cards on `/careers` rather than dedicated individual public pages, the sitemap must include `https://antimatrix.co.in/careers` **once**.
  3. **Verified Canonical Legal URLs:** Include only the verified primary legal endpoints (`/privacy`, `/terms`, `/refund-policy`). Never include duplicate aliases.
- **Specification:**
  1. In `templates/seo/sitemap.xml`:
     ```xml
     <?xml version="1.0" encoding="UTF-8"?>
     <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
       {% for page in static_pages %}
       <url>
         <loc>{{ page.loc }}</loc>
         <changefreq>{{ page.changefreq }}</changefreq>
         <priority>{{ page.priority }}</priority>
         {% if page.lastmod %}<lastmod>{{ page.lastmod }}</lastmod>{% endif %}
       </url>
       {% endfor %}
     </urlset>
     ```
  2. In `routes/main.py`:
     ```python
     from datetime import datetime
     from flask import Response, render_template

     @main_bp.route('/sitemap.xml')
     def sitemap_xml():
         base_url = "https://antimatrix.co.in"
         static_pages = [
             {'loc': f"{base_url}/", 'changefreq': 'weekly', 'priority': '1.0'},
             {'loc': f"{base_url}/about", 'changefreq': 'monthly', 'priority': '0.8'},
             {'loc': f"{base_url}/services", 'changefreq': 'weekly', 'priority': '0.9'},
             {'loc': f"{base_url}/products", 'changefreq': 'weekly', 'priority': '0.9'},
             {'loc': f"{base_url}/careers", 'changefreq': 'daily', 'priority': '0.8'},
             {'loc': f"{base_url}/contact", 'changefreq': 'monthly', 'priority': '0.7'},
             {'loc': f"{base_url}/privacy", 'changefreq': 'yearly', 'priority': '0.3'},
             {'loc': f"{base_url}/terms", 'changefreq': 'yearly', 'priority': '0.3'},
             {'loc': f"{base_url}/refund-policy", 'changefreq': 'yearly', 'priority': '0.3'},
         ]
         xml = render_template('seo/sitemap.xml', static_pages=static_pages)
         return Response(xml, mimetype='application/xml')
     ```
- **Testing & Verification Procedures:**
  ```bash
  curl -s https://antimatrix.co.in/sitemap.xml | grep "<loc>"
  # Verify valid XML syntax, zero "#" fragments, zero private/auth URLs, and single /careers entry.
  ```
- **Rollback Procedure:** Remove the route and template.
- **Acceptance Criteria:** `curl https://antimatrix.co.in/sitemap.xml` returns `HTTP 200 OK`, `application/xml`, passes XML validation, contains zero URL fragments, and lists all 9 canonical pages.

---

### Step 1.3: Explicit, Safe Canonical URL Strategy
- **Target Files:** `app.py` (or `routes/main.py`), `templates/base.html`
- **Dependencies:** Flask request context
- **Risk Level:** Medium
- **Vulnerability of Generic `request.base_url`:**
  - `request.base_url` reflects whatever Host header, protocol (`http` vs `https`), or trailing slash the client sent.
  - If a user accesses `http://www.antimatrix.co.in/about/`, a generic `request.base_url` outputs `http://www.antimatrix.co.in/about/`, defeating the purpose of the canonical tag and encouraging search engine confusion.
- **Safe Explicit Strategy:**
  1. Define global constant:
     ```python
     CANONICAL_DOMAIN = 'https://antimatrix.co.in'
     ```
  2. Implement an explicit context processor in `app.py` / `routes/main.py`:
     ```python
     @app.context_processor
     def inject_canonical_url():
         # Normalize path: strip trailing slash except for root '/'
         path = request.path.rstrip('/') if request.path != '/' else '/'
         
         # Map secondary aliases to explicit canonical paths
         alias_map = {
             '/product': '/products',
             '/privacy-policy': '/privacy',
             '/terms-and-conditions': '/terms',
             '/refunds': '/refund-policy',
             '/cancellation-refund': '/refund-policy',
             '/my-profile': '/profile',
         }
         canonical_path = alias_map.get(path, path)
         canonical_url = f"{CANONICAL_DOMAIN}{canonical_path}"
         return dict(canonical_url=canonical_url)
     ```
  3. In `templates/base.html`:
     ```html
     {% block canonical %}
       <link rel="canonical" href="{{ canonical_url }}">
     {% endblock %}
     ```
- **Testing & Verification Procedures:**
  ```bash
  # Test with www and trailing slash:
  curl -s -H "Host: www.antimatrix.co.in" http://127.0.0.1:8017/about/ | grep "rel=\"canonical\""
  # Expected: <link rel="canonical" href="https://antimatrix.co.in/about">
  ```
- **Rollback Procedure:** Revert `templates/base.html` and remove the context processor.
- **Acceptance Criteria:** Every page renders `<link rel="canonical" href="https://antimatrix.co.in/...">` with guaranteed HTTPS, apex domain, normalized slashes, and zero query parameters.

---

### Step 1.4: Search Engine Indexation Controls (`noindex, nofollow`)
- **Target Files:**
  - `templates/auth/login.html`
  - `templates/auth/signup.html`
  - `templates/pages/job_apply.html`
  - `templates/pages/job_apply_review.html`
  - `templates/pages/profile.html`
- **Dependencies:** `templates/base.html` (block `meta_robots`)
- **Risk Level:** Low
- **Specification:**
  1. In `templates/base.html` `<head>`:
     ```html
     {% block meta_robots %}
       <meta name="robots" content="index, follow">
     {% endblock %}
     ```
  2. In auth, transactional, and candidate application templates:
     ```html
     {% block meta_robots %}
       <meta name="robots" content="noindex, nofollow">
     ```
     ```html
     {% endblock %}
     ```
- **Testing & Verification Procedures:**
  ```bash
  curl -s https://antimatrix.co.in/login | grep "robots"
  # Expected: <meta name="robots" content="noindex, nofollow">

  curl -s https://antimatrix.co.in/about | grep "robots"
  # Expected: <meta name="robots" content="index, follow">
  ```
- **Rollback Procedure:** Remove block overrides in child templates.
- **Acceptance Criteria:** Core public pages output `index, follow`; login, signup, profile, and application forms output `noindex, nofollow`.

---

### Step 1.5: Hostinger VPS Nginx Inspection & Domain Redirection
- **Target Server:** Hostinger Ubuntu 24.04 VPS
- **Target File:** `/etc/nginx/sites-available/anti-matrix`
- **Prerequisites & Isolation Rules:**
  - Must NOT touch `intern.antimatrix.co.in`, `qmatrix.co.in`, `ems`, or `teamworkmanpower`.
  - Must inspect active Nginx configurations first.
  - Must verify DNS for `www.antimatrix.co.in`:
    ```bash
    dig +short A www.antimatrix.co.in
    ```
  - Must verify SSL certificate coverage:
    ```bash
    sudo certbot certificates
    ```
    *Note: If the existing certificate does not include `www.antimatrix.co.in` in its SAN list, an HTTPS server block for `www` will trigger a browser SSL certificate mismatch warning. If `www` is missing from the cert, run `sudo certbot --expand -d antimatrix.co.in -d www.antimatrix.co.in` before enabling the HTTPS redirect.*
- **Specification (Only after SSL coverage is confirmed):**
  1. Back up active configuration:
     ```bash
     sudo cp /etc/nginx/sites-available/anti-matrix /etc/nginx/sites-available/anti-matrix.bak-$(date +%F)
     ```
  2. Add dedicated server blocks for `www` and HTTP port 80:
     ```nginx
     # Redirect HTTP to HTTPS Apex
     server {
         listen 80;
         server_name antimatrix.co.in www.antimatrix.co.in;
         return 301 https://antimatrix.co.in$request_uri;
     }

     # Redirect HTTPS WWW to HTTPS Apex
     server {
         listen 443 ssl http2;
         server_name www.antimatrix.co.in;

         ssl_certificate /etc/letsencrypt/live/antimatrix.co.in/fullchain.pem;
         ssl_certificate_key /etc/letsencrypt/live/antimatrix.co.in/privkey.pem;

         return 301 https://antimatrix.co.in$request_uri;
     }
     ```
  3. Validate syntax before reload:
     ```bash
     sudo nginx -t
     ```
  4. Reload Nginx:
     ```bash
     sudo systemctl reload nginx
     ```
- **Testing & Verification Procedures:**
  ```bash
  curl -I https://www.antimatrix.co.in/
  # Expected: HTTP/2 301 Moved Permanently -> Location: https://antimatrix.co.in/

  curl -I http://antimatrix.co.in/
  # Expected: HTTP/1.1 301 Moved Permanently -> Location: https://antimatrix.co.in/

  # Verify other domains are unaffected:
  curl -I https://intern.antimatrix.co.in/
  # Must return expected status for internship portal without redirection to apex!
  ```
- **Rollback Procedure:**
  ```bash
  sudo cp /etc/nginx/sites-available/anti-matrix.bak-$(date +%F) /etc/nginx/sites-available/anti-matrix
  sudo nginx -t && sudo systemctl reload nginx
  ```
- **Acceptance Criteria:** `www` requests 301-redirect cleanly to apex domain; other virtual hosts (`intern.*`, etc.) continue operating normally.

---

## 4. Track 2 — Route Hygiene & Canonical Redirections

### Step 2.1: Align Flask Route Aliases Preserving Functional Dependencies
- **Target File:** `routes/main.py`
- **Dependencies:** Templates, Footer, Signup, Candidate declaration forms
- **Risk Level:** Medium
- **Codebase Dependency Verification:**
  - In `routes/main.py`:
    - `def products()` is decorated with `@main_bp.route('/product')` then `@main_bp.route('/products')`. Because `/product` was first, `url_for('main.products')` generates `/product`.
    - `def privacy()` is decorated with `@main_bp.route('/privacy')` then `@main_bp.route('/privacy-policy')`. `url_for('main.privacy')` generates `/privacy`.
    - `def terms()` is decorated with `@main_bp.route('/terms')` then `@main_bp.route('/terms-and-conditions')`. `url_for('main.terms')` generates `/terms`.
    - `def refund_policy()` is decorated with `@main_bp.route('/refund-policy')`, `@main_bp.route('/cancellation-refund')`, `@main_bp.route('/refunds')`. `url_for('main.refund_policy')` generates `/refund-policy`.
  - In templates (`templates/components/footer.html`, `templates/auth/signup.html`, `templates/pages/job_apply.html`):
    - All existing links call `url_for('main.terms')`, `url_for('main.privacy')`, and `url_for('main.refund_policy')`!
- **Safe Route Realignment Specification:**
  To prevent breaking any internal links, form submissions, or causing redirect loops:
  1. **Products:** Make `/products` the canonical route. Update `routes/main.py` so `/products` is primary on `def products()`, and `/product` issues a 301 redirect:
     ```python
     @main_bp.route('/products')
     def products():
         return render_template('pages/products.html')

     @main_bp.route('/product')
     def product_alias_redirect():
         return redirect(url_for('main.products'), code=301)
     ```
  2. **Legal Pages:** Preserve `/privacy`, `/terms`, and `/refund-policy` as primary canonical endpoints matching `url_for` callers. Secondary aliases 301-redirect to them:
     ```python
     # Privacy
     @main_bp.route('/privacy')
     def privacy():
         return render_template('pages/privacy.html')

     @main_bp.route('/privacy-policy')
     def privacy_alias_redirect():
         return redirect(url_for('main.privacy'), code=301)

     # Terms
     @main_bp.route('/terms')
     def terms():
         return render_template('pages/terms.html')

     @main_bp.route('/terms-and-conditions')
     def terms_alias_redirect():
         return redirect(url_for('main.terms'), code=301)

     # Refunds
     @main_bp.route('/refund-policy')
     def refund_policy():
         return render_template('pages/refund_policy.html')

     @main_bp.route('/cancellation-refund')
     @main_bp.route('/refunds')
     def refund_alias_redirect():
         return redirect(url_for('main.refund_policy'), code=301)
     ```
  3. **Profile Route:**
     ```python
     @main_bp.route('/my-profile')
     @login_required
     def my_profile_alias_redirect():
         return redirect(url_for('main.profile'), code=301)
     ```
- **Testing & Verification Procedures:**
  ```bash
  curl -I http://127.0.0.1:8017/product
  # Expected: HTTP 301 -> /products

  curl -I http://127.0.0.1:8017/privacy-policy
  # Expected: HTTP 301 -> /privacy

  curl -I http://127.0.0.1:8017/terms-and-conditions
  # Expected: HTTP 301 -> /terms

  curl -I http://127.0.0.1:8017/refunds
  # Expected: HTTP 301 -> /refund-policy
  ```
- **Rollback Procedure:** Revert `routes/main.py` to previous git commit.
- **Acceptance Criteria:** Secondary aliases return 301 redirects; primary endpoints return 200 OK; zero broken template links or infinite loops.

---

### Step 2.2: Enforce Trailing Slash Consistency
- **Target File:** `routes/main.py`
- **Dependencies:** Flask url matching
- **Risk Level:** Low
- **Specification:**
  Ensure routes specify `strict_slashes=False` or standard redirect behavior so URLs like `/careers/` redirect or match `/careers` without duplicating content.
- **Testing & Verification Procedures:**
  ```bash
  curl -I https://antimatrix.co.in/careers/
  # Verify status 308 or 301 to /careers or canonical tag points to /careers
  ```
- **Acceptance Criteria:** Canonical tag points to non-trailing slash URL across all pages.

---

## 5. Track 3 — Content, Schema & Asset Optimization

### Step 3.1: Organization & WebSite JSON-LD Structured Data
- **Target File:** `templates/base.html`
- **Dependencies:** Verified corporate details
- **Risk Level:** Low
- **Verified Company Details (from Codebase Inspection):**
  - **Legal / Brand Name:** Anti-Matrix
  - **Canonical URL:** `https://antimatrix.co.in`
  - **Logo:** `https://antimatrix.co.in/static/images/anti_matrix_logo.png`
  - **Verified Email:** `info@antimatrix.com` (from `templates/pages/contact.html` & `footer.html`)
  - **Verified Phone:** `+91 91595 14326` (telecom link: `tel:+919159514326`)
  - **Verified Social Profiles:**
    - LinkedIn: `https://www.linkedin.com/in/anti-matrix/`
    - Instagram: `https://www.instagram.com/antimatrix_in/`
  *(Note: No Twitter/X or placeholder phone numbers will be included).*
- **Specification:**
  In `templates/base.html` `<head>`:
  ```html
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": "https://antimatrix.co.in/#organization",
        "name": "Anti-Matrix",
        "url": "https://antimatrix.co.in",
        "logo": {
          "@type": "ImageObject",
          "url": "https://antimatrix.co.in/static/images/anti_matrix_logo.png"
        },
        "sameAs": [
          "https://www.linkedin.com/in/anti-matrix/",
          "https://www.instagram.com/antimatrix_in/"
        ],
        "contactPoint": {
          "@type": "ContactPoint",
          "telephone": "+919159514326",
          "contactType": "Customer Support",
          "email": "info@antimatrix.com",
          "areaServed": "IN"
        }
      },
      {
        "@type": "WebSite",
        "@id": "https://antimatrix.co.in/#website",
        "url": "https://antimatrix.co.in",
        "name": "Anti-Matrix",
        "publisher": {
          "@id": "https://antimatrix.co.in/#organization"
        }
      }
    ]
  }
  </script>
  ```
- **Testing & Verification Procedures:** Test output against Google Rich Results Test.
- **Acceptance Criteria:** Valid JSON-LD with zero syntax errors, verified contact info only, and zero placeholder values.

---

### Step 3.2: Dynamic Title & Meta Description Architecture
- **Target Files:** `templates/base.html`, child page templates
- **Dependencies:** Jinja2 blocks
- **Risk Level:** Low
- **Specification:**
  1. In `templates/base.html`:
     ```html
     <meta name="description" content="{% block meta_description %}Anti-Matrix delivers enterprise AI automation, full-stack software development, and transformative digital intelligence systems.{% endblock %}">
     ```
  2. In child templates (`about.html`, `services.html`, `products.html`, `careers.html`, `contact.html`), define tailored, unique meta descriptions.
- **Testing & Verification Procedures:**
  ```bash
  curl -s https://antimatrix.co.in/about | grep "description"
  curl -s https://antimatrix.co.in/services | grep "description"
  ```
- **Acceptance Criteria:** Each page serves a distinct, keyword-relevant meta description under 160 characters.

---

### Step 3.3: External Link Hygiene (Remove ChatGPT UTM Parameter)
- **Target File:** `templates/pages/products.html` (Line 339)
- **Dependencies:** None
- **Risk Level:** Low
- **Specification:**
  Change:
  ```html
  <a href="https://www.qmatrix.co.in/?utm_source=chatgpt.com" target="_blank" rel="noopener noreferrer" class="btn-card">
  ```
  To:
  ```html
  <a href="https://www.qmatrix.co.in/" target="_blank" rel="noopener noreferrer" class="btn-card">
  ```
- **Testing & Verification Procedures:** Grep codebase for `utm_source=chatgpt.com`.
- **Acceptance Criteria:** Zero occurrences of hardcoded ChatGPT tracking strings in production links.

---

### Step 3.4: Brand Film Media Handling
- **Target File:** `templates/pages/brand_film.html`
- **Dependencies:** Media assets
- **Risk Level:** Low
- **Specification:**
  - Verify if video file (`anti_matrix_brand_film.mp4`) is available for upload.
  - If video is hosted externally (e.g. YouTube/Vimeo), replace the broken `<video>` player and broken download button with a responsive embedded player.
  - If unreleased, remove the broken download button and show a "Coming Soon" state with poster image `static/images/anti_matrix_brand_film_poster.jpg` (which is verified to exist on disk).
- **Acceptance Criteria:** Zero HTTP 404 console errors when accessing `https://antimatrix.co.in/brand-film`.

---

### Step 3.5: Non-Destructive Asset Archiving Protocol
- **Target Directory:** `static/`
- **Dependencies:** Admin DOCX document preview workflows
- **Risk Level:** Medium
- **Asset Verification Findings:**
  1. `static/js/vendor/jszip.js` and `jszip.min.js`:
     - **MANDATORY PRESERVATION:** In `templates/admin/application_detail.html` and `document_preview.html`, DOCX preview is handled. `JSZip` is a required peer dependency of `docx-preview.js`. **Do NOT delete or remove JSZip.**
  2. `static/videos/anti_matrix_film_audio.wav` (7.58 MB):
     - Master uncompressed audio stem for brand film. Do NOT delete destructively. If repository size optimization is requested, back up to cold offline storage outside git tracking.
  3. `static/images/home_svc_*.jpg`:
     - Superseded by `service_*.jpg` in `templates/pages/home.html`. Do NOT delete without verifying legacy CSS caches.
- **Acceptance Criteria:** No vendor libraries or document preview dependencies are removed.

---

### Step 3.6: Dedicated Job Detail Architecture (Future JobPosting Schema Prerequisite)
- **Target Scope:** Future Feature Roadmap
- **Dependencies:** Backend route and template architecture
- **Risk Level:** Informational
- **Google JobPosting Schema Requirements Analysis:**
  - Google Search Central strictly requires that `JobPosting` structured data describe a **single job posting** on a **dedicated, publicly accessible job-detail URL** where a candidate can view full requirements and directly apply.
  - Google explicitly advises against injecting multiple `JobPosting` schemas on general listing pages without individual job URLs.
  - Because Anti-Matrix currently lists jobs as cards on `/careers` and routes applications directly to `/careers/apply/<job_id>` (which is noindexed), injecting `JobPosting` schema currently would trigger Google Search Console structured data validation errors.
- **Recommended Future Implementation:**
  1. Create a dedicated public route: `/careers/<job_slug>` (or `/careers/job/<job_id>`).
  2. Implement dedicated job detail template rendering single job requirements, responsibilities, and apply button.
  3. Embed fully compliant `JobPosting` JSON-LD schema on each individual job detail page.
  4. Only after this dedicated architecture is deployed, include the individual job detail URLs in `sitemap.xml`.
- **Current Action:** Defer `JobPosting` schema until dedicated job pages are built, preventing invalid schema penalties.

---

## 6. Comprehensive Testing & Verification Plan

```
+---------------------------------------------------------------------------------------------------+
|                                 VERIFICATION MATRIX & CHECKLIST                                   |
+---------------------------------------------------------------------------------------------------+
|  Check Item                     Target URL / File           Expected Result                       |
+---------------------------------+---------------------------+-------------------------------------+
|  Robots.txt HTTP 200            | /robots.txt               | 200 OK, text/plain, sitemap pointer |
|  Robots.txt No Auth Disallows   | /robots.txt               | Does NOT block /login or /signup    |
|  Sitemap.xml HTTP 200           | /sitemap.xml              | 200 OK, application/xml             |
|  Sitemap XML Fragment Free      | /sitemap.xml              | Zero '#job-' or '#' strings in XML  |
|  Sitemap Single Careers Entry   | /sitemap.xml              | Exactly one /careers URL listed     |
|  Canonical Tag Presence         | All pages                 | <link rel="canonical" href="...">   |
|  Canonical Tag Format           | All pages                 | https://antimatrix.co.in/...        |
|  Noindex on Auth                | /login, /signup           | <meta name="robots" content="noindex|
|  Noindex on Job Application     | /careers/apply/<id>       | <meta name="robots" content="noindex|
|  Nginx WWW Redirect             | https://www.antimatrix... | 301 -> https://antimatrix.co.in/    |
|  Nginx Port 80 Redirect         | http://antimatrix.co.in   | 301 -> https://antimatrix.co.in/    |
|  Isolated VHosts Intact         | https://intern.antimat... | Unaffected (no redirect to apex)    |
|  Product Route 301              | /product                  | 301 -> /products                    |
|  Privacy Route 301              | /privacy-policy           | 301 -> /privacy                     |
|  Terms Route 301                | /terms-and-conditions     | 301 -> /terms                       |
|  Refund Route 301               | /cancellation-refund      | 301 -> /refund-policy               |
|  JSON-LD Schema Validity        | Homepage                  | Google Rich Results Test Passes     |
|  JSON-LD Verified Contact       | Homepage                  | info@antimatrix.com, +919159514326  |
|  Docx Preview Dependency        | Admin Application Detail  | JSZip preserved; preview functions  |
+---------------------------------------------------------------------------------------------------+
```

---

## 7. Rollback Strategies

For every track and step executed:
1. **Application Code Rollback:**
   - Git commits are structured atomically per track.
   - To roll back application changes:
     ```bash
     git revert <commit-hash> --no-edit
     /usr/local/bin/anti-matrix-deploy
     ```
   - Zero database changes were made, ensuring 100% rollback fidelity.
2. **Nginx Configuration Rollback:**
   - To roll back Nginx changes on Hostinger VPS:
     ```bash
     sudo cp /etc/nginx/sites-available/anti-matrix.bak-* /etc/nginx/sites-available/anti-matrix
     sudo nginx -t && sudo systemctl reload nginx
     ```
3. **Emergency Verification:**
   - Test `curl -I http://127.0.0.1:8017/` to ensure Gunicorn service is healthy.

---

## 8. Summary & Next Actions

> [!IMPORTANT]
> **No changes have been executed.**  
> This revised implementation plan addresses all 10 strategic and safety issues, preserves multi-site VPS configurations, protects backend dependencies, avoids invalid schemas and URI fragments, and establishes an explicit, safe technical foundation.
> 
> **Awaiting explicit stakeholder approval before proceeding to implementation.**
