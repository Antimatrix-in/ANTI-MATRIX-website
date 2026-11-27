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
    'Recruitment'
]

SUPPORTED_RECRUITMENT_EVENTS = [
    {
        'key': 'candidate_application_submitted',
        'label': 'Candidate Application Submitted',
        'default_delay': 5,
        'default_template_type': 'application_successful',
        'description': 'Single official acknowledgment email sent automatically 5 minutes after a candidate submits their job application or completes payment.',
        'is_active': True
    },
    {
        'key': 'candidate_under_review',
        'label': 'Application Under Review',
        'default_delay': 0,
        'default_template_type': 'under_review_notification',
        'description': 'Reserved for future recruitment phase. Inactive.',
        'is_active': False
    },
    {
        'key': 'candidate_shortlisted',
        'label': 'Candidate Shortlisted',
        'default_delay': 0,
        'default_template_type': 'offer_letter',
        'description': 'Reserved for future recruitment phase. Inactive.',
        'is_active': False
    },
    {
        'key': 'candidate_rejected',
        'label': 'Candidate Rejected',
        'default_delay': 0,
        'default_template_type': 'rejection_notification',
        'description': 'Reserved for future recruitment phase. Inactive.',
        'is_active': False
    },
    {
        'key': 'assessment_invitation',
        'label': 'Assessment Invitation',
        'default_delay': 0,
        'default_template_type': None,
        'description': 'Reserved for future Assessment Portal integration. Inactive.',
        'is_active': False
    },
    {
        'key': 'interview_invitation',
        'label': 'Interview Invitation',
        'default_delay': 0,
        'default_template_type': None,
        'description': 'Reserved for future interview scheduling. Inactive.',
        'is_active': False
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
    Ensures the single active Application Submitted Successfully template
    and automation event mapping exist in the database.
    Safely deactivates and archives all other templates and event mappings so that
    only the single acknowledgment template remains active.
    Preserves all historical email delivery records and audit logs.
    """
    from services.email_service import (
        DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT,
        DEFAULT_APPLICATION_SUCCESSFUL_BODY
    )

    # 1. Ensure the single active Application Submitted Successfully template exists
    app_tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
    if not app_tmpl:
        app_tmpl = EmailTemplate(
            template_type='application_successful',
            name='Application Submitted Successfully',
            description='Single official acknowledgment email sent 5 minutes after job application submission.',
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
        app_tmpl.name = 'Application Submitted Successfully'
        app_tmpl.category = 'Recruitment'
        app_tmpl.is_active = True
        # If subject/body is blank or legacy wording, update to the new single official template
        if not app_tmpl.subject or "Thank You for Showing Interest" in app_tmpl.subject or "Application Successfully Submitted —" in app_tmpl.subject:
            app_tmpl.subject = DEFAULT_APPLICATION_SUCCESSFUL_SUBJECT
        if not app_tmpl.body or "evaluating your credentials" in app_tmpl.body or "Internship Opportunity at Anti Matrix" in app_tmpl.body:
            app_tmpl.body = DEFAULT_APPLICATION_SUCCESSFUL_BODY
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Re-fetch app_tmpl id
    app_tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()

    # 2. Deactivate and archive all other templates safely (Preserve records, do not delete)
    archived_template_defs = [
        {
            'template_type': 'under_review_notification',
            'name': 'Application Under Review',
            'description': 'Candidate notification once review begins. Archived.',
            'category': 'Recruitment',
            'subject': 'Application Under Review – Anti-Matrix | {{application_id}}',
            'body': 'Dear {{candidate_name}},\n\nYour application for {{job_title}} is currently under review.\n\nBest Regards,\nAnti-Matrix Recruitment Team',
        },
        {
            'template_type': 'offer_letter',
            'name': 'Candidate Shortlisted Notification',
            'description': 'Candidate notification when moved to Shortlisted. Archived.',
            'category': 'Recruitment',
            'subject': 'Update on Your Application – Anti-Matrix | {{application_id}}',
            'body': 'Dear {{candidate_name}},\n\nCongratulations! You have been shortlisted for {{job_title}}.\n\nBest Regards,\nAnti-Matrix Recruitment Team',
        },
        {
            'template_type': 'rejection_notification',
            'name': 'Application Status Update',
            'description': 'Candidate notification when not moving forward. Archived.',
            'category': 'Recruitment',
            'subject': 'Update Regarding Your Application – Anti-Matrix | {{application_id}}',
            'body': 'Dear {{candidate_name}},\n\nThank you for applying for {{job_title}}. At this time, we have decided to proceed with other candidates.\n\nBest Regards,\nAnti-Matrix Recruitment Team',
        }
    ]
    for adef in archived_template_defs:
        t = EmailTemplate.query.filter_by(template_type=adef['template_type']).first()
        if not t:
            t = EmailTemplate(
                template_type=adef['template_type'],
                name=adef['name'],
                description=adef['description'],
                category=adef['category'],
                subject=adef['subject'],
                body=adef['body'],
                is_active=False
            )
            db.session.add(t)
        else:
            t.is_active = False

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    # 3. Ensure the single active automation mapping: Candidate Application Submitted
    app_mapping = EmailTemplateMapping.query.filter_by(event_key='candidate_application_submitted').first()
    if not app_mapping:
        app_mapping = EmailTemplateMapping(
            event_key='candidate_application_submitted',
            event_label='Candidate Application Submitted',
            description='Sent automatically 5 minutes after a candidate submits their job application or completes payment.',
            email_template_id=app_tmpl.id if app_tmpl else None,
            delay_minutes=5,
            is_active=True
        )
        db.session.add(app_mapping)
    else:
        if app_tmpl:
            app_mapping.email_template_id = app_tmpl.id
        app_mapping.delay_minutes = 5
        app_mapping.is_active = True

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    # 4. Deactivate and archive all other automation mappings safely
    archived_mapping_defs = [
        ('candidate_under_review', 'Application Under Review', 'under_review_notification'),
        ('candidate_shortlisted', 'Candidate Shortlisted', 'offer_letter'),
        ('candidate_rejected', 'Candidate Rejected', 'rejection_notification'),
    ]
    for ev_key, ev_label, tmpl_type in archived_mapping_defs:
        linked_tmpl = EmailTemplate.query.filter_by(template_type=tmpl_type).first()
        m = EmailTemplateMapping.query.filter_by(event_key=ev_key).first()
        if not m:
            m = EmailTemplateMapping(
                event_key=ev_key,
                event_label=ev_label,
                description=f'{ev_label} notification (Archived/Inactive).',
                email_template_id=linked_tmpl.id if linked_tmpl else None,
                delay_minutes=0,
                is_active=False
            )
            db.session.add(m)
        else:
            m.is_active = False
            if linked_tmpl and not m.email_template_id:
                m.email_template_id = linked_tmpl.id

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
