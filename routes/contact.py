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
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': 'Failed to save your inquiry. Please try again.'
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'Message sent! Thank you for reaching out.'
    })
