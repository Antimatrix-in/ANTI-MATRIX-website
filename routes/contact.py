from flask import Blueprint, request, jsonify, redirect, url_for
from models import db, ContactInquiry
import re

contact_bp = Blueprint('contact', __name__)
EMAIL_REGEX = re.compile(r'^\S+@\S+\.\S+$')


@contact_bp.route('/api/contact', methods=['POST'], strict_slashes=False)
@contact_bp.route('/api/contact/', methods=['POST'], strict_slashes=False)
def api_contact():
    data = (request.get_json(silent=True) if request.is_json else None) or request.form or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    phone = (data.get('phone') or '').strip()
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()

    errors = {}
    if not name:
        errors['name'] = 'Name is required'
    if not email:
        errors['email'] = 'Email is required'
    elif not EMAIL_REGEX.match(email):
        errors['email'] = 'Enter a valid email address'
    if not subject:
        errors['subject'] = 'Please select a subject'
    if not message:
        errors['message'] = 'Message is required'
    elif len(message) < 20:
        errors['message'] = 'Message must be at least 20 characters'

    if errors:
        return jsonify({'status': 'error', 'errors': errors}), 400

    saved_successfully = False
    try:
        inquiry = ContactInquiry(
            name=name,
            email=email,
            phone=phone if phone else None,
            subject=subject,
            message=message,
            is_processed=False
        )
        db.session.add(inquiry)
        db.session.commit()
        saved_successfully = True
    except Exception as primary_err:
        db.session.rollback()

        # Tier 2: Auto-heal missing table/columns or out-of-sync PostgreSQL sequence
        try:
            from sqlalchemy import inspect as sa_inspect, text as sa_text
            inspector = sa_inspect(db.engine)
            table_names = inspector.get_table_names()
            
            if 'contact_inquiries' not in table_names:
                db.create_all()
            else:
                existing_cols = [c['name'] for c in inspector.get_columns('contact_inquiries')]
                with db.engine.connect() as conn:
                    if 'phone' not in existing_cols:
                        try:
                            conn.execute(sa_text("ALTER TABLE contact_inquiries ADD COLUMN phone VARCHAR(40)"))
                            conn.commit()
                        except Exception:
                            conn.rollback()
                    if 'is_processed' not in existing_cols:
                        try:
                            conn.execute(sa_text("ALTER TABLE contact_inquiries ADD COLUMN is_processed BOOLEAN DEFAULT FALSE"))
                            conn.commit()
                        except Exception:
                            conn.rollback()
                    if db.engine.dialect.name != 'sqlite':
                        try:
                            conn.execute(sa_text("""
                                DO $$
                                DECLARE
                                    seq_name text;
                                    max_id bigint;
                                BEGIN
                                    seq_name := pg_get_serial_sequence('contact_inquiries', 'id');
                                    IF seq_name IS NOT NULL THEN
                                        SELECT COALESCE(MAX(id), 0) + 1 INTO max_id FROM contact_inquiries;
                                        PERFORM setval(seq_name, max_id, false);
                                    END IF;
                                END $$;
                            """))
                            conn.commit()
                        except Exception:
                            conn.rollback()

            inquiry = ContactInquiry(
                name=name,
                email=email,
                phone=phone if phone else None,
                subject=subject,
                message=message,
                is_processed=False
            )
            db.session.add(inquiry)
            db.session.commit()
            saved_successfully = True
        except Exception:
            db.session.rollback()

        # Tier 3: Explicit ID insert
        if not saved_successfully:
            try:
                max_id = db.session.query(db.func.max(ContactInquiry.id)).scalar() or 0
                inquiry = ContactInquiry(
                    id=max_id + 1,
                    name=name,
                    email=email,
                    phone=phone if phone else None,
                    subject=subject,
                    message=message,
                    is_processed=False
                )
                db.session.add(inquiry)
                db.session.commit()
                saved_successfully = True
            except Exception:
                db.session.rollback()

        # Tier 4: Dynamic parameterized raw SQL fallback
        if not saved_successfully:
            try:
                from sqlalchemy import inspect as sa_inspect, text as sa_text
                from datetime import datetime, timezone
                inspector = sa_inspect(db.engine)
                existing_cols = set(c['name'] for c in inspector.get_columns('contact_inquiries')) if 'contact_inquiries' in inspector.get_table_names() else set()
                
                insert_fields = {
                    'name': name[:120],
                    'email': email[:120],
                    'subject': subject[:120],
                    'message': message
                }
                if 'phone' in existing_cols and phone:
                    insert_fields['phone'] = phone[:40]
                if 'is_processed' in existing_cols:
                    insert_fields['is_processed'] = False
                if 'created_at' in existing_cols:
                    insert_fields['created_at'] = datetime.now(timezone.utc)

                cols_str = ', '.join(insert_fields.keys())
                vals_str = ', '.join([f":{k}" for k in insert_fields.keys()])
                with db.engine.connect() as conn:
                    conn.execute(sa_text(f"INSERT INTO contact_inquiries ({cols_str}) VALUES ({vals_str})"), insert_fields)
                    conn.commit()
                saved_successfully = True
            except Exception:
                pass

    if not saved_successfully:
        return jsonify({
            'status': 'error',
            'message': 'Failed to save your inquiry due to a temporary database error. Please try again.'
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'Message sent! Thank you for reaching out.'
    })
