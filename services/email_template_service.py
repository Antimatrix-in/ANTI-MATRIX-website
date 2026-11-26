import re
from datetime import datetime, timezone
from sqlalchemy import func, inspect, text
from flask import current_app
from models import db, EmailTemplate, EmailTemplateMapping


# =====================================================================
# DEFAULT STATUS EMAIL TEMPLATE BODIES
# =====================================================================

DEFAULT_UNDER_REVIEW_SUBJECT = "Your Application is Under Review — Anti-Matrix"

DEFAULT_UNDER_REVIEW_BODY = """Dear {{candidate_name}},

Thank you for your interest in Anti-Matrix and for applying for the **{{job_title}}** position.

We wanted to let you know that your application (ID: **{{application_id}}**) is currently **under review** by our recruitment team.

We are carefully evaluating your profile and will get back to you with further updates as soon as possible.

Please keep your **Application ID ({{application_id}})** handy for future reference.

Best Regards,
**Anti-Matrix Recruitment Team**
{{company_email}}
{{website}}"""

DEFAULT_REJECTION_SUBJECT = "Update on Your Application — Anti-Matrix"

DEFAULT_REJECTION_BODY = """Dear {{candidate_name}},

Thank you for your interest in Anti-Matrix and for applying for the **{{job_title}}** position (Application ID: **{{application_id}}**).

After careful consideration, we regret to inform you that we will not be moving forward with your application at this time.

We appreciate the time and effort you invested in your application. We encourage you to continue developing your skills and to look out for future openings at Anti-Matrix that may align with your profile.

We wish you the very best in your career journey.

Best Regards,
**Anti-Matrix Recruitment Team**
{{company_email}}
{{website}}"""


# =====================================================================
# DEFAULT SYSTEM EVENTS & CONFIGURATION
# =====================================================================

SUPPORTED_TEMPLATE_CATEGORIES = [
    'Recruitment',
    'Assessment',
    'Interview',
    'General'
]

SUPPORTED_RECRUITMENT_EVENTS = [
    {
        'key': 'candidate_application_submitted',
        'label': 'Candidate Application Submitted',
        'default_delay': 5,
        'default_template_type': 'application_successful',
        'description': 'Sent automatically 5 minutes after a candidate submits their job application or completes payment.'
    },
    {
        'key': 'candidate_under_review',
        'label': 'Application Under Review',
        'default_delay': 0,
        'default_template_type': 'under_review_notification',
        'description': 'Sent when a candidate application status is updated to Under Review.'
    },
    {
        'key': 'candidate_shortlisted',
        'label': 'Candidate Shortlisted',
        'default_delay': 0,
        'default_template_type': 'offer_letter',
        'description': 'Sent when a candidate application status is updated to Shortlisted.'
    },
    {
        'key': 'candidate_rejected',
        'label': 'Candidate Rejected',
        'default_delay': 0,
        'default_template_type': 'rejection_notification',
        'description': 'Sent when a candidate application status is updated to Rejected.'
    },
    {
        'key': 'assessment_invitation',
        'label': 'Assessment Invitation',
        'default_delay': 0,
        'default_template_type': None,
        'description': 'Reserved for future Assessment Portal integration. Inactive by default.'
    },
    {
        'key': 'interview_invitation',
        'label': 'Interview Invitation',
        'default_delay': 0,
        'default_template_type': None,
        'description': 'Sent when an interview invitation is scheduled for a candidate.'
    }
]


# =====================================================================
# SLUG & NAME VALIDATION
# =====================================================================

def slugify(text):
    """
    Generate clean, alphanumeric slug from text string.
    """
    if not text:
        return f"template_{int(datetime.now(timezone.utc).timestamp())}"
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    slug = text.strip('_')
    return slug or f"template_{int(datetime.now(timezone.utc).timestamp())}"


def generate_unique_slug(base_slug, exclude_id=None):
    """
    Ensures slug uniqueness in the email_templates table.
    """
    candidate = base_slug
    counter = 1
    while True:
        query = EmailTemplate.query.filter_by(template_type=candidate)
        if exclude_id:
            query = query.filter(EmailTemplate.id != exclude_id)
        exists = query.first()
        if not exists:
            return candidate
        counter += 1
        candidate = f"{base_slug}_{counter}"


def validate_template_name(name, current_id=None):
    """
    Validates template name: non-empty, max 150 chars, and unique (case-insensitive).
    Returns (is_valid: bool, error_message: str or None)
    """
    if not name or not name.strip():
        return False, "Template Name is required."
    
    clean_name = name.strip()
    if len(clean_name) > 150:
        return False, "Template Name cannot exceed 150 characters."

    query = EmailTemplate.query.filter(func.lower(EmailTemplate.name) == func.lower(clean_name))
    if current_id:
        query = query.filter(EmailTemplate.id != current_id)
    
    duplicate = query.first()
    if duplicate:
        return False, f"A template with the name '{clean_name}' already exists. Please choose a unique name."

    return True, None


# =====================================================================
# INITIALIZATION & SEEDING
# =====================================================================

_EMAIL_SCHEMA_INITIALIZED = False

def ensure_email_template_schema():
    """
    Safely inspects and updates the database schema for the email templates module.
    Ensures:
    1. 'email_templates' table has 'description', 'category', 'is_active' columns.
    2. 'email_template_mappings' table exists.
    3. Default recruitment email templates and automation event mappings are initialized.
    Works seamlessly across PostgreSQL and SQLite, preventing 500/404 crashes.
    """
    global _EMAIL_SCHEMA_INITIALIZED
    if _EMAIL_SCHEMA_INITIALIZED:
        return True

    try:
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # 1. Update columns on email_templates if missing
        if 'email_templates' in table_names:
            tmpl_cols = [c['name'] for c in inspector.get_columns('email_templates')]
            with db.engine.begin() as conn:
                dialect_name = db.engine.dialect.name
                if dialect_name == 'postgresql':
                    if 'description' not in tmpl_cols:
                        conn.execute(text("ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS description TEXT"))
                    if 'category' not in tmpl_cols:
                        conn.execute(text("ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'Recruitment'"))
                    if 'is_active' not in tmpl_cols:
                        conn.execute(text("ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                else:
                    if 'description' not in tmpl_cols:
                        conn.execute(text("ALTER TABLE email_templates ADD COLUMN description TEXT"))
                    if 'category' not in tmpl_cols:
                        conn.execute(text("ALTER TABLE email_templates ADD COLUMN category VARCHAR(50) DEFAULT 'Recruitment'"))
                    if 'is_active' not in tmpl_cols:
                        conn.execute(text("ALTER TABLE email_templates ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL"))

        # 2. Create email_template_mappings table if missing
        if 'email_template_mappings' not in table_names:
            try:
                EmailTemplateMapping.__table__.create(db.engine, checkfirst=True)
            except Exception:
                pass

        # 3. Seed default templates and event mappings
        ensure_default_templates_and_mappings()

        _EMAIL_SCHEMA_INITIALIZED = True
        return True
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        if current_app:
            current_app.logger.warning(f"[EmailTemplateService] Schema self-healing note: {e}")
        return False


def ensure_default_templates_and_mappings():
    """
    Ensures default email templates and automation event mappings exist in the database.
    Non-destructive: will never overwrite admin customizations or existing mappings.
    """
    from services.email_service import (
        DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT,
        DEFAULT_APPLICATION_SUCCESSFUL_BODY,
        DEFAULT_OFFER_LETTER_SUBJECT,
        DEFAULT_OFFER_LETTER_BODY
    )

    # 1. Ensure default Application Acknowledgment template exists
    app_tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
    if not app_tmpl:
        app_tmpl = EmailTemplate(
            template_type='application_successful',
            name='Application Acknowledgment',
            description='Default acknowledgment email sent 5 minutes after job application submission.',
            category='Recruitment',
            subject=DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT,
            body=DEFAULT_APPLICATION_SUCCESSFUL_BODY,
            is_active=True
        )
        db.session.add(app_tmpl)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        # Update missing fields if needed without overwriting customized body/subject
        updated = False
        if not app_tmpl.name:
            app_tmpl.name = 'Application Acknowledgment'
            updated = True
        if not getattr(app_tmpl, 'category', None):
            app_tmpl.category = 'Recruitment'
            updated = True
        if getattr(app_tmpl, 'is_active', None) is None:
            app_tmpl.is_active = True
            updated = True
        if updated:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    # 2. Ensure default Offer Letter template exists
    offer_tmpl = EmailTemplate.query.filter_by(template_type='offer_letter').first()
    if not offer_tmpl:
        offer_tmpl = EmailTemplate(
            template_type='offer_letter',
            name='Offer Letter / Shortlisted',
            description='Official congratulatory shortlisted offer letter email template.',
            category='Recruitment',
            subject=DEFAULT_OFFER_LETTER_SUBJECT,
            body=DEFAULT_OFFER_LETTER_BODY,
            is_active=True
        )
        db.session.add(offer_tmpl)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        updated = False
        if not getattr(offer_tmpl, 'category', None):
            offer_tmpl.category = 'Recruitment'
            updated = True
        if getattr(offer_tmpl, 'is_active', None) is None:
            offer_tmpl.is_active = True
            updated = True
        if updated:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    # 3. Ensure default Under Review Notification template exists
    under_review_tmpl = EmailTemplate.query.filter_by(template_type='under_review_notification').first()
    if not under_review_tmpl:
        under_review_tmpl = EmailTemplate(
            template_type='under_review_notification',
            name='Application Under Review Notification',
            description='Notification email sent when a candidate application status changes to Under Review.',
            category='Recruitment',
            subject=DEFAULT_UNDER_REVIEW_SUBJECT,
            body=DEFAULT_UNDER_REVIEW_BODY,
            is_active=True
        )
        db.session.add(under_review_tmpl)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # 4. Ensure default Rejection Notification template exists
    rejection_tmpl = EmailTemplate.query.filter_by(template_type='rejection_notification').first()
    if not rejection_tmpl:
        rejection_tmpl = EmailTemplate(
            template_type='rejection_notification',
            name='Application Rejected Notification',
            description='Notification email sent when a candidate application is rejected.',
            category='Recruitment',
            subject=DEFAULT_REJECTION_SUBJECT,
            body=DEFAULT_REJECTION_BODY,
            is_active=True
        )
        db.session.add(rejection_tmpl)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Re-fetch template references
    app_tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
    offer_tmpl = EmailTemplate.query.filter_by(template_type='offer_letter').first()
    under_review_tmpl = EmailTemplate.query.filter_by(template_type='under_review_notification').first()
    rejection_tmpl = EmailTemplate.query.filter_by(template_type='rejection_notification').first()

    # 5. Ensure supported event mappings exist
    for event_cfg in SUPPORTED_RECRUITMENT_EVENTS:
        key = event_cfg['key']
        mapping = EmailTemplateMapping.query.filter_by(event_key=key).first()

        if not mapping:
            # Determine initial template link
            initial_tmpl_id = None
            initial_active = False

            if key == 'candidate_application_submitted' and app_tmpl:
                initial_tmpl_id = app_tmpl.id
                initial_active = True
            elif key == 'candidate_shortlisted' and offer_tmpl:
                initial_tmpl_id = offer_tmpl.id
                initial_active = True
            elif key == 'candidate_under_review' and under_review_tmpl:
                initial_tmpl_id = under_review_tmpl.id
                initial_active = True
            elif key == 'candidate_rejected' and rejection_tmpl:
                initial_tmpl_id = rejection_tmpl.id
                initial_active = True

            mapping = EmailTemplateMapping(
                event_key=key,
                event_label=event_cfg['label'],
                description=event_cfg['description'],
                email_template_id=initial_tmpl_id,
                delay_minutes=event_cfg['default_delay'],
                is_active=initial_active
            )
            db.session.add(mapping)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        else:
            # Backfill template_id for existing mappings that have none
            updated = False
            if key == 'candidate_application_submitted' and not mapping.email_template_id and app_tmpl:
                mapping.email_template_id = app_tmpl.id
                mapping.delay_minutes = 5
                mapping.is_active = True
                updated = True
            elif key == 'candidate_under_review' and not mapping.email_template_id and under_review_tmpl:
                mapping.email_template_id = under_review_tmpl.id
                mapping.is_active = True
                updated = True
            elif key == 'candidate_shortlisted' and not mapping.email_template_id and offer_tmpl:
                mapping.email_template_id = offer_tmpl.id
                mapping.is_active = True
                updated = True
            elif key == 'candidate_rejected' and not mapping.email_template_id and rejection_tmpl:
                mapping.email_template_id = rejection_tmpl.id
                mapping.is_active = True
                updated = True
            if updated:
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()


# =====================================================================
# TEMPLATE DUPLICATION & SAFETY CHECKS
# =====================================================================

def duplicate_template(template_id):
    """
    Creates a copy of an existing template with a unique name and slug.
    Returns the newly created EmailTemplate instance.
    """
    source = db.session.get(EmailTemplate, template_id)
    if not source:
        return None

    # Generate unique name
    base_name = f"Copy of {source.name}"
    name_candidate = base_name
    counter = 1
    while True:
        exists = EmailTemplate.query.filter(func.lower(EmailTemplate.name) == func.lower(name_candidate)).first()
        if not exists:
            break
        counter += 1
        name_candidate = f"Copy ({counter}) of {source.name}"

    # Generate unique slug
    base_slug = slugify(name_candidate)
    new_slug = generate_unique_slug(base_slug)

    new_tmpl = EmailTemplate(
        template_type=new_slug,
        name=name_candidate,
        description=f"Cloned from '{source.name}'. {source.description or ''}".strip(),
        category=source.category or 'Recruitment',
        subject=source.subject,
        body=source.body,
        is_active=True
    )
    db.session.add(new_tmpl)
    db.session.commit()
    return new_tmpl


def can_delete_template(template_id):
    """
    Verifies if a template can be safely deleted.
    Returns: (can_delete: bool, reason: str or None, active_mappings: list)
    Rules:
    1. Cannot delete templates currently used in active event mappings.
    2. Protect core 'application_successful' default template from deletion.
    """
    tmpl = db.session.get(EmailTemplate, template_id)
    if not tmpl:
        return False, "Template not found.", []

    # Check active mappings
    active_mappings = EmailTemplateMapping.query.filter_by(
        email_template_id=template_id,
        is_active=True
    ).all()

    if active_mappings:
        event_names = ", ".join([m.event_label for m in active_mappings])
        reason = (
            f"Cannot delete template '{tmpl.name}' because it is currently mapped to active automation event(s): "
            f"{event_names}. Please unmap or reassign the automation event before deleting this template."
        )
        return False, reason, active_mappings

    # Check if core acknowledgment template
    if tmpl.template_type == 'application_successful':
        return False, "The default Application Acknowledgment system template cannot be deleted.", []

    return True, None, []
