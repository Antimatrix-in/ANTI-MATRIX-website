import os
import re
import uuid
import time
import docx
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    abort, current_app, send_from_directory, jsonify, session
)
from flask_login import current_user
from werkzeug.utils import secure_filename
from models import (
    db, JobPosting, JobApplication, Payment, User, Employee,
    DocumentTemplate, EmailTemplate, EmployeeDocument, MoneyTransaction,
    InternshipBenefit, ContactInquiry
)

from services.offer_letter_service import (
    generate_offer_letter_docx, send_offer_letter_email,
    OfferLetterTemplateNotFoundError, OfferLetterTemplateFileMissingError,
    get_active_offer_letter_template, determine_job_category,
    OFFER_LETTER_CATEGORIES, ensure_default_templates_initialized
)
from services.money_service import get_financial_summary
from routes.auth import get_safe_redirect

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def _ensure_admin_schemas_on_request():
    """
    Self-healing runtime schema validation for admin modules.
    Ensures missing tables/columns (partners, email_template_mappings, partner_id)
    are created and initialized automatically without requiring server-level app.py overwrites.
    """
    try:
        from services.email_template_service import ensure_email_template_schema
        ensure_email_template_schema()
    except Exception as e:
        current_app.logger.warning(f"[AdminSchemaCheck] Email template schema healing note: {e}")

    try:
        from services.money_service import ensure_money_management_schema
        ensure_money_management_schema()
    except Exception as e:
        current_app.logger.warning(f"[AdminSchemaCheck] Money management schema healing note: {e}")


@admin_bp.context_processor
def inject_admin_inquiry_counts():
    try:
        unread = ContactInquiry.query.filter_by(is_processed=False).count()
        total = ContactInquiry.query.count()
        return {
            'unread_inquiries_count': unread,
            'total_inquiries_count': total
        }
    except Exception:
        return {
            'unread_inquiries_count': 0,
            'total_inquiries_count': 0
        }


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in with an administrator account to access this area.', 'warning')
            target_path = request.path
            if request.query_string:
                target_path = f"{request.path}?{request.query_string.decode('utf-8', errors='ignore')}"
            return redirect(url_for('auth.login', next=target_path))
        if getattr(current_user, 'role', '') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['GET', 'POST'], strict_slashes=False)
def admin_login():
    """
    Compatibility route for /admin/login and /admin/login/.
    Keeps /login as the canonical login route and redirects safely with next target.
    Directs already-authenticated admins straight to admin.dashboard.
    """
    raw_target = (
        request.args.get('next') or
        request.args.get('redirect') or
        request.form.get('redirect') or
        request.form.get('next')
    )
    safe_target = get_safe_redirect(raw_target, default='/admin/') if raw_target else '/admin/'

    if current_user.is_authenticated and getattr(current_user, 'role', '') == 'admin':
        return redirect(safe_target if raw_target else url_for('admin.dashboard'))

    return redirect(url_for('auth.login', next=safe_target))


@admin_bp.route('', strict_slashes=False)
@admin_bp.route('/', strict_slashes=False)
@admin_bp.route('/dashboard', strict_slashes=False)
@admin_required
def dashboard():
    total_jobs = JobPosting.query.count()
    active_jobs = JobPosting.query.filter_by(is_active=True).count()
    recent_jobs = JobPosting.query.order_by(JobPosting.created_at.desc()).limit(5).all()
    total_applications = JobApplication.query.count()

    try:
        financial_summary = get_financial_summary()
        total_transactions = MoneyTransaction.query.count()
        recent_transactions = MoneyTransaction.query.order_by(
            MoneyTransaction.transaction_date.desc(),
            MoneyTransaction.created_at.desc()
        ).limit(6).all()
    except Exception as f_err:
        current_app.logger.warning(f"Error computing financial summary for dashboard: {f_err}")
        db.session.rollback()
        financial_summary = {
            'production_balance': 0.0,
            'production_income': 0.0,
            'balance': 0.0,
            'total_income': 0.0,
            'total_expense': 0.0,
            'all_time_count': 0
        }
        total_transactions = 0
        recent_transactions = []

    return render_template(
        'admin/dashboard.html',
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        recent_jobs=recent_jobs,
        total_applications=total_applications,
        financial_summary=financial_summary,
        total_transactions=total_transactions,
        recent_transactions=recent_transactions
    )


@admin_bp.route('/jobs', strict_slashes=False)
@admin_required
def jobs():
    status_filter = request.args.get('status', 'all').lower()
    dept_filter = request.args.get('dept', '').strip()
    search_query = request.args.get('q', '').strip()

    query = JobPosting.query

    if status_filter == 'active':
        query = query.filter_by(is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)

    if dept_filter:
        query = query.filter(JobPosting.department.ilike(f'%{dept_filter}%'))

    if search_query:
        query = query.filter(
            (JobPosting.title.ilike(f'%{search_query}%')) |
            (JobPosting.location.ilike(f'%{search_query}%')) |
            (JobPosting.skills.ilike(f'%{search_query}%'))
        )

    all_jobs = query.order_by(JobPosting.created_at.desc()).all()
    total_unfiltered_jobs = JobPosting.query.count()
    departments = db.session.query(JobPosting.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]

    return render_template(
        'admin/jobs.html',
        jobs=all_jobs,
        total_unfiltered_jobs=total_unfiltered_jobs,
        status_filter=status_filter,
        dept_filter=dept_filter,
        search_query=search_query,
        departments=departments
    )


@admin_bp.route('/jobs/delete-all', methods=['POST'])
@admin_required
def delete_all_jobs():
    confirmation = (request.form.get('confirmation') or '').strip()
    if confirmation != 'DELETE':
        flash('Deletion cancelled. You must type DELETE to confirm.', 'danger')
        return redirect(url_for('admin.jobs'))

    total_jobs = JobPosting.query.count()
    if total_jobs == 0:
        flash('There are no job postings to delete.', 'info')
        return redirect(url_for('admin.jobs'))

    try:
        Payment.query.delete()
        JobApplication.query.delete()
        JobPosting.query.delete()
        db.session.commit()
        flash('All job postings have been deleted successfully.', 'success')
    except Exception:
        db.session.rollback()
        flash('Unable to delete job postings. No changes were made.', 'danger')

    return redirect(url_for('admin.jobs'))


@admin_bp.route('/jobs/create', methods=['GET', 'POST'])
@admin_required
def create_job():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        department = (request.form.get('department') or '').strip()
        location = (request.form.get('location') or '').strip()
        employment_type = (request.form.get('employment_type') or 'Full-time').strip()
        duration = (request.form.get('duration') or '').strip() or None
        short_description = (request.form.get('short_description') or '').strip()
        description = (request.form.get('description') or '').strip()
        requirements = (request.form.get('requirements') or '').strip()
        qualifications = (request.form.get('qualifications') or '').strip()
        experience = (request.form.get('experience') or '').strip()
        responsibilities = (request.form.get('responsibilities') or '').strip()
        skills = (request.form.get('skills') or '').strip()
        salary = (request.form.get('salary') or '').strip()
        application_deadline = (request.form.get('application_deadline') or '').strip()
        is_active = True if request.form.get('is_active') in ['true', '1', 'on'] else False

        errors = []
        if not title:
            errors.append('Job title is required.')
        if not department:
            errors.append('Department is required.')
        if not location:
            errors.append('Location is required.')
        if not short_description:
            errors.append('Short description is required.')
        if not description:
            errors.append('Full job description is required.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/create_job.html', form_data=request.form)

        # Auto-generate unique Job Code JB#### with concurrency retry or use manual if provided
        from sqlalchemy.exc import IntegrityError
        import re

        manual_code = (request.form.get('job_code') or request.form.get('job_id') or '').strip().upper()
        if manual_code:
            if not re.match(r'^JB\d{4}$', manual_code):
                flash('Job Code must follow the format JB#### (e.g. JB1001, JB1234).', 'danger')
                return render_template('admin/create_job.html', form_data=request.form)
            existing = JobPosting.query.filter((JobPosting.job_code == manual_code) | (JobPosting.job_id == manual_code)).first()
            if existing:
                flash(f'Job Code {manual_code} is already in use by "{existing.title}".', 'danger')
                return render_template('admin/create_job.html', form_data=request.form)

        saved = False
        final_job_code = None
        for attempt in range(5):
            final_job_code = manual_code if manual_code else JobPosting.generate_unique_job_code()
            job = JobPosting(
                job_id=final_job_code,
                job_code=final_job_code,
                title=title,
                department=department,
                location=location,
                employment_type=employment_type,
                duration=duration,
                short_description=short_description,
                description=description,
                requirements=requirements,
                qualifications=qualifications,
                experience=experience,
                responsibilities=responsibilities,
                skills=skills,
                salary=salary,
                application_deadline=application_deadline,
                is_active=is_active
            )
            try:
                db.session.add(job)
                db.session.commit()
                saved = True
                break
            except IntegrityError:
                db.session.rollback()
                if manual_code:
                    flash(f'Job Code {manual_code} already exists in the database.', 'danger')
                    return render_template('admin/create_job.html', form_data=request.form)
                if attempt == 4:
                    flash('Could not generate a unique Job Code due to concurrency conflict. Please try again.', 'danger')
                    return render_template('admin/create_job.html', form_data=request.form)

        flash(f"Job posting '{job.title}' ({final_job_code}) created successfully.", 'success')
        return redirect(url_for('admin.jobs'))

    return render_template('admin/create_job.html', form_data={})


@admin_bp.route('/jobs/edit/<int:job_id>', methods=['GET', 'POST'])
@admin_required
def edit_job(job_id):
    job = db.session.get(JobPosting, job_id) or abort(404)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        department = (request.form.get('department') or '').strip()
        location = (request.form.get('location') or '').strip()
        employment_type = (request.form.get('employment_type') or 'Full-time').strip()
        duration = (request.form.get('duration') or '').strip() or None
        short_description = (request.form.get('short_description') or '').strip()
        description = (request.form.get('description') or '').strip()
        requirements = (request.form.get('requirements') or '').strip()
        qualifications = (request.form.get('qualifications') or '').strip()
        experience = (request.form.get('experience') or '').strip()
        responsibilities = (request.form.get('responsibilities') or '').strip()
        skills = (request.form.get('skills') or '').strip()
        salary = (request.form.get('salary') or '').strip()
        application_deadline = (request.form.get('application_deadline') or '').strip()
        is_active = True if request.form.get('is_active') in ['true', '1', 'on'] else False

        errors = []
        if not title:
            errors.append('Job title is required.')
        if not department:
            errors.append('Department is required.')
        if not location:
            errors.append('Location is required.')
        if not short_description:
            errors.append('Short description is required.')
        if not description:
            errors.append('Full job description is required.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/edit_job.html', job=job)

        job_code_val = (request.form.get('job_code') or request.form.get('job_id') or '').strip().upper()
        if not job.job_code and not job.job_id:
            generated = JobPosting.generate_unique_job_code()
            job.job_code = generated
            job.job_id = generated
        elif job_code_val and job_code_val != (job.job_code or job.job_id or '').upper():
            import re
            if re.match(r'^JB\d{4}$', job_code_val):
                conflict = JobPosting.query.filter(
                    ((JobPosting.job_code == job_code_val) | (JobPosting.job_id == job_code_val)),
                    JobPosting.id != job.id
                ).first()
                if not conflict:
                    job.job_code = job_code_val
                    job.job_id = job_code_val
        elif not job.job_code and job.job_id:
            job.job_code = job.job_id

        job.title = title
        job.department = department
        job.location = location
        job.employment_type = employment_type
        job.duration = duration
        job.short_description = short_description
        job.description = description
        job.requirements = requirements
        job.qualifications = qualifications
        job.experience = experience
        job.responsibilities = responsibilities
        job.skills = skills
        job.salary = salary
        job.application_deadline = application_deadline
        job.is_active = is_active

        # Mark as Updated state handling
        mark_updated = True if request.form.get('is_updated') in ['true', '1', 'on'] else False
        if mark_updated:
            now = datetime.now(timezone.utc)
            cr = job.created_at
            if cr and cr.tzinfo is None:
                cr = cr.replace(tzinfo=timezone.utc)
            if cr and (now - cr).total_seconds() < 60:
                job.updated_at = job.created_at + timedelta(minutes=5)
            else:
                job.updated_at = now
        else:
            job.updated_at = job.created_at

        db.session.commit()
        flash(f"Job posting '{job.title}' updated successfully.", 'success')
        return redirect(url_for('admin.jobs'))

    return render_template('admin/edit_job.html', job=job)


@admin_bp.route('/jobs/toggle/<int:job_id>', methods=['POST'])
@admin_required
def toggle_job(job_id):
    job = db.session.get(JobPosting, job_id) or abort(404)
    job.is_active = not job.is_active
    db.session.commit()
    status_str = 'Active' if job.is_active else 'Inactive'
    flash(f"Job '{job.title}' is now {status_str}.", 'success')
    return redirect(request.referrer or url_for('admin.jobs'))


@admin_bp.route('/jobs/toggle-updated/<int:job_id>', methods=['POST'])
@admin_required
def toggle_job_updated(job_id):
    job = db.session.get(JobPosting, job_id) or abort(404)
    if job.is_updated:
        job.updated_at = job.created_at
        status_str = 'unmarked as Updated'
    else:
        now = datetime.now(timezone.utc)
        cr = job.created_at
        if cr and cr.tzinfo is None:
            cr = cr.replace(tzinfo=timezone.utc)
        if cr and (now - cr).total_seconds() < 60:
            job.updated_at = job.created_at + timedelta(minutes=5)
        else:
            job.updated_at = now
        status_str = 'marked as Updated'
    db.session.commit()
    flash(f"Job '{job.title}' {status_str}.", 'success')
    return redirect(request.referrer or url_for('admin.jobs'))


@admin_bp.route('/jobs/delete/<int:job_id>', methods=['POST'])
@admin_required
def delete_job(job_id):
    job = db.session.get(JobPosting, job_id) or abort(404)
    title = job.title
    db.session.delete(job)
    db.session.commit()
    flash(f"Job posting '{title}' and its applications have been safely removed.", 'info')
    return redirect(url_for('admin.jobs'))


# ==============================================================================
# MONEY MANAGEMENT & REVENUE DASHBOARD
# ==============================================================================

@admin_bp.route('/money-management', methods=['GET'], strict_slashes=False)
@admin_bp.route('/money_management', methods=['GET'], strict_slashes=False)
@admin_bp.route('/money', methods=['GET'], strict_slashes=False)
@admin_required
def money_management():
    """
    Main Admin Money Management & Revenue Dashboard.
    Displays Google Pay-style chronological transactions, summaries, and filters.
    """
    from services.money_service import (
        ensure_money_management_schema,
        get_financial_summary, filter_transactions, get_partner_earnings_summary,
        STANDARD_INCOME_CATEGORIES, STANDARD_EXPENSE_CATEGORIES, PAYMENT_METHODS,
        format_inr
    )

    try:
        ensure_money_management_schema()
    except Exception as e:
        current_app.logger.warning(f"Note on money schema initialization: {e}")

    type_filter = (request.args.get('type') or 'all').strip().lower()
    env_filter = (request.args.get('env') or 'all').strip().lower()
    date_filter = (request.args.get('date') or 'all').strip().lower()
    start_date = (request.args.get('start_date') or '').strip() or None
    end_date = (request.args.get('end_date') or '').strip() or None
    category_filter = (request.args.get('category') or 'all').strip()
    search_query = (request.args.get('q') or '').strip()
    sort_by = (request.args.get('sort') or 'newest').strip().lower()

    # Dynamic partner earnings summary for descending bar chart
    try:
        partner_summary = get_partner_earnings_summary(
            date_filter=date_filter,
            start_date=start_date,
            end_date=end_date
        )
    except Exception as e:
        current_app.logger.error(f"[MoneyManagement] Partner summary error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        partner_summary = {'partners': [], 'total_partner_earnings': 0, 'total_partner_count': 0, 'max_earnings': 0, 'date_filter_label': 'All Time'}

    # Dynamic backend summary calculations (database-driven)
    try:
        summary = get_financial_summary(
            env_filter=env_filter,
            date_filter=date_filter,
            start_date=start_date,
            end_date=end_date,
            category_filter=category_filter,
            search_query=search_query
        )
    except Exception as e:
        current_app.logger.error(f"[MoneyManagement] Financial summary error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        summary = {
            'total_income': 0, 'total_expense': 0, 'net_balance': 0, 'total_tax': 0,
            'cashfree_income': 0, 'manual_income': 0, 'transaction_count': 0,
            'income_count': 0, 'expense_count': 0
        }

    # Filtered transaction list
    try:
        transactions = filter_transactions(
            type_filter=type_filter,
            env_filter=env_filter,
            date_filter=date_filter,
            start_date=start_date,
            end_date=end_date,
            category_filter=category_filter,
            search_query=search_query,
            sort_by=sort_by
        ).all()
    except Exception as e:
        current_app.logger.error(f"[MoneyManagement] Filter transactions error: {e}", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        transactions = []

    # Aggregate distinct categories for filter dropdown
    try:
        db_categories = db.session.query(MoneyTransaction.category).distinct().all()
        all_categories = sorted(list(set(
            STANDARD_INCOME_CATEGORIES + 
            STANDARD_EXPENSE_CATEGORIES + 
            [c[0] for c in db_categories if c[0]]
        )))
    except Exception as e:
        current_app.logger.warning(f"[MoneyManagement] Categories query note: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        all_categories = sorted(list(set(STANDARD_INCOME_CATEGORIES + STANDARD_EXPENSE_CATEGORIES)))

    # Partner Earnings Records Table queries
    partner_id_filter = request.args.get('partner_filter', '').strip() or None
    q_partner = request.args.get('q_partner', '').strip() or None
    sort_partner = request.args.get('sort_partner', 'newest').strip() or 'newest'

    try:
        from services.money_service import filter_partner_earnings_records, get_active_partners
        partner_records = filter_partner_earnings_records(
            partner_id=partner_id_filter,
            date_filter=date_filter,
            start_date=start_date,
            end_date=end_date,
            search_query=q_partner,
            sort_by=sort_partner
        ).all()
        active_partners = get_active_partners()
    except Exception as e:
        current_app.logger.warning(f"[MoneyManagement] Partner records query note: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        partner_records = []
        active_partners = []

    # Base counts for admin navigation badges
    try:
        total_jobs = JobPosting.query.count()
        total_applications = JobApplication.query.count()
        new_applications = JobApplication.query.filter_by(status='New').count()
    except Exception as count_err:
        current_app.logger.warning(f"[MoneyManagement] Base counts note: {count_err}")
        try:
            db.session.rollback()
        except Exception:
            pass
        total_jobs = 0
        total_applications = 0
        new_applications = 0

    try:
        total_employees = Employee.query.count()
    except Exception as emp_err:
        try:
            db.session.rollback()
        except Exception:
            pass
        total_employees = 0

    today_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    return render_template(
        'admin/money_management.html',
        partner_summary=partner_summary,
        format_inr=format_inr,
        summary=summary,
        transactions=transactions,
        type_filter=type_filter,
        env_filter=env_filter,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
        category_filter=category_filter,
        search_query=search_query,
        sort_by=sort_by,
        categories=all_categories,
        income_categories=STANDARD_INCOME_CATEGORIES,
        expense_categories=STANDARD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        today_date_str=today_date_str,
        total_jobs=total_jobs,
        total_applications=total_applications,
        new_applications=new_applications,
        total_employees=total_employees,
        partner_records=partner_records,
        active_partners=active_partners,
        partner_id_filter=partner_id_filter,
        q_partner=q_partner,
        sort_partner=sort_partner
    )


@admin_bp.route('/money-management/add', methods=['GET', 'POST'], strict_slashes=False)
@admin_bp.route('/money_management/add', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def add_money_transaction():
    """
    Dedicated Add Transaction page for recording manual Income and Expense entries.
    GET: Displays the standalone executive Add Transaction form.
    POST: Processes and stores the manual transaction with audit logging.
    """
    from services.money_service import (
        STANDARD_INCOME_CATEGORIES, STANDARD_EXPENSE_CATEGORIES, PAYMENT_METHODS,
        get_active_partners
    )

    if request.method == 'POST':
        txn_type = (request.form.get('transaction_type') or '').strip().upper()
        amount_str = (request.form.get('amount') or '').strip()
        txn_date_str = (request.form.get('transaction_date') or '').strip()
        txn_time = (request.form.get('transaction_time') or '').strip()
        category = (request.form.get('category') or '').strip()
        custom_category = (request.form.get('custom_category') or '').strip()
        purpose = (request.form.get('purpose') or '').strip()
        description = (request.form.get('description') or '').strip()
        payment_method = (request.form.get('payment_method') or 'Bank Transfer').strip()
        reference = (request.form.get('reference') or '').strip()
        partner_id_raw = (request.form.get('partner_id') or '').strip()
        partner_id = int(partner_id_raw) if partner_id_raw.isdigit() else None

        # Handle custom category
        if category.lower() in ['other', 'custom', 'other income', 'other expense'] and custom_category:
            category = custom_category
        elif not category and custom_category:
            category = custom_category

        # Validate Transaction Type
        if txn_type not in ['INCOME', 'EXPENSE']:
            flash('Invalid transaction type. Must be Income or Expense.', 'danger')
            return redirect(url_for('admin.add_money_transaction'))

        # Validate Amount (must be positive numeric > 0)
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")
        except (ValueError, TypeError):
            flash('Please enter a valid numeric amount greater than zero.', 'danger')
            return redirect(url_for('admin.add_money_transaction'))

        # Validate Transaction Date (supports historical dates)
        if not txn_date_str:
            txn_date = datetime.now(timezone.utc).date()
        else:
            try:
                txn_date = datetime.strptime(txn_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format. Please select a valid date (YYYY-MM-DD).', 'danger')
                return redirect(url_for('admin.add_money_transaction'))

        # Default time if not entered
        if not txn_time:
            txn_time = datetime.now(timezone.utc).strftime('%I:%M %p')

        # Category is required
        if not category:
            category = "Other Income" if txn_type == 'INCOME' else "Other Expense"

        if not purpose:
            purpose = category

        now_utc = datetime.now(timezone.utc)

        try:
            new_txn = MoneyTransaction(
                transaction_type=txn_type,
                amount=amount,
                transaction_date=txn_date,
                transaction_time=txn_time,
                category=category,
                purpose=purpose,
                description=description,
                payment_method=payment_method,
                reference=reference,
                partner_id=partner_id,
                source='MANUAL',
                provider='MANUAL',
                environment='MANUAL',
                created_by_admin_id=current_user.id,
                created_at=now_utc,
                updated_at=now_utc
            )
            db.session.add(new_txn)
            db.session.commit()
            flash(f"Manual {txn_type.capitalize()} of ₹{amount:,.2f} recorded successfully!", 'success')
            return redirect(url_for('admin.money_management'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving transaction: {str(e)}", 'danger')
            return redirect(url_for('admin.add_money_transaction'))

    # GET Request: Prepare form context
    partners = get_active_partners()
    total_jobs = JobPosting.query.count()
    total_applications = JobApplication.query.count()
    new_applications = JobApplication.query.filter_by(status='New').count()
    try:
        total_employees = Employee.query.count()
    except Exception as emp_err:
        current_app.logger.warning(f"Note on total_employees count: {emp_err}")
        db.session.rollback()
        total_employees = 0
    today_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    return render_template(
        'admin/money_management_add.html',
        partners=partners,
        income_categories=STANDARD_INCOME_CATEGORIES,
        expense_categories=STANDARD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        today_date_str=today_date_str,
        total_jobs=total_jobs,
        total_applications=total_applications,
        new_applications=new_applications,
        total_employees=total_employees
    )


@admin_bp.route('/money-management/transactions/create', methods=['POST'], strict_slashes=False)
@admin_bp.route('/money_management/transactions/create', methods=['POST'], strict_slashes=False)
@admin_required
def create_money_transaction():
    """
    Legacy / Direct endpoint for manually creating an Income or Expense transaction.
    Maintains full backward compatibility.
    """
    return add_money_transaction()


@admin_bp.route('/money-management/transactions/<int:txn_id>/edit', methods=['GET', 'POST'], strict_slashes=False)
@admin_bp.route('/money_management/transactions/<int:txn_id>/edit', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def edit_money_transaction(txn_id):
    """
    Edit an existing manual transaction.
    GET: Renders dedicated Edit Transaction page with pre-populated values.
    POST: Validates and updates the existing record in place, recalculating all metrics.
    Automatic Cashfree transactions are strictly locked and cannot be edited.
    """
    from services.money_service import (
        STANDARD_INCOME_CATEGORIES, STANDARD_EXPENSE_CATEGORIES, PAYMENT_METHODS,
        validate_manual_admin_mutation, get_active_partners
    )

    txn = db.session.get(MoneyTransaction, txn_id)
    if not txn:
        flash('Transaction not found.', 'danger')
        return redirect(url_for('admin.money_management'))

    allowed, err_msg = validate_manual_admin_mutation(current_user, txn=txn, action='edit')
    if not allowed:
        flash(err_msg or 'You are not authorized to edit this transaction.', 'danger')
        return redirect(url_for('admin.money_management'))

    if request.method == 'POST':
        txn_type = (request.form.get('transaction_type') or '').strip().upper()
        amount_str = (request.form.get('amount') or '').strip()
        txn_date_str = (request.form.get('transaction_date') or '').strip()
        txn_time = (request.form.get('transaction_time') or '').strip()
        category = (request.form.get('category') or '').strip()
        custom_category = (request.form.get('custom_category') or '').strip()
        purpose = (request.form.get('purpose') or '').strip()
        description = (request.form.get('description') or '').strip()
        payment_method = (request.form.get('payment_method') or txn.payment_method or 'Manual').strip()
        reference = (request.form.get('reference') or '').strip()
        partner_id_raw = (request.form.get('partner_id') or '').strip()
        partner_id = int(partner_id_raw) if partner_id_raw.isdigit() else None

        if category.lower() in ['other', 'custom', 'other income', 'other expense'] and custom_category:
            category = custom_category
        elif not category and custom_category:
            category = custom_category

        # Validate Transaction Type
        if txn_type in ['INCOME', 'EXPENSE']:
            txn.transaction_type = txn_type

        # Validate Amount (must be positive numeric > 0)
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")
            txn.amount = amount
        except (ValueError, TypeError):
            flash('Please enter a valid numeric amount greater than zero.', 'danger')
            return redirect(url_for('admin.edit_money_transaction', txn_id=txn_id))

        # Validate Date
        if txn_date_str:
            try:
                txn.transaction_date = datetime.strptime(txn_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format. Please select a valid date (YYYY-MM-DD).', 'danger')
                return redirect(url_for('admin.edit_money_transaction', txn_id=txn_id))

        if txn_time:
            txn.transaction_time = txn_time

        if category:
            txn.category = category
        if purpose:
            txn.purpose = purpose
        txn.description = description
        txn.payment_method = payment_method
        txn.reference = reference
        txn.partner_id = partner_id
        txn.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
            flash('Transaction updated successfully.', 'success')
            return redirect(url_for('admin.money_management'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating transaction: {str(e)}", 'danger')
            return redirect(url_for('admin.edit_money_transaction', txn_id=txn_id))

    # GET Request: Prepare pre-populated form context
    partners = get_active_partners()
    total_jobs = JobPosting.query.count()
    total_applications = JobApplication.query.count()
    new_applications = JobApplication.query.filter_by(status='New').count()
    try:
        total_employees = Employee.query.count()
    except Exception as emp_err:
        current_app.logger.warning(f"Note on total_employees count: {emp_err}")
        db.session.rollback()
        total_employees = 0

    is_custom_category = (
        txn.category not in STANDARD_INCOME_CATEGORIES and 
        txn.category not in STANDARD_EXPENSE_CATEGORIES
    )

    return render_template(
        'admin/money_management_edit.html',
        txn=txn,
        partners=partners,
        is_custom_category=is_custom_category,
        income_categories=STANDARD_INCOME_CATEGORIES,
        expense_categories=STANDARD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        total_jobs=total_jobs,
        total_applications=total_applications,
        new_applications=new_applications,
        total_employees=total_employees
    )


@admin_bp.route('/money-management/transactions/<int:txn_id>/delete', methods=['POST'], strict_slashes=False)
@admin_bp.route('/money_management/transactions/<int:txn_id>/delete', methods=['POST'], strict_slashes=False)
@admin_required
def delete_money_transaction(txn_id):
    """
    Delete a manually created transaction.
    Cashfree automatic transactions CANNOT be deleted.
    """
    txn = db.session.get(MoneyTransaction, txn_id)
    if not txn:
        flash('Transaction not found.', 'danger')
        return redirect(url_for('admin.money_management'))

    from services.money_service import validate_manual_admin_mutation
    allowed, err_msg = validate_manual_admin_mutation(current_user, txn=txn, action='delete')
    if not allowed:
        flash(err_msg or 'Cashfree automatic transactions cannot be deleted. They remain permanently linked to payment records.', 'danger')
        return redirect(url_for('admin.money_management'))

    try:
        amount = txn.amount
        txn_type = txn.transaction_type
        db.session.delete(txn)
        db.session.commit()
        flash(f"Manual {txn_type.capitalize()} of ₹{amount:,.2f} deleted successfully.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting transaction: {str(e)}", 'danger')

    return redirect(url_for('admin.money_management'))


@admin_bp.route('/money-management/transactions/<int:txn_id>', methods=['GET'], strict_slashes=False)
@admin_bp.route('/money_management/transactions/<int:txn_id>', methods=['GET'], strict_slashes=False)
@admin_required
def get_money_transaction_detail(txn_id):
    """Return full transaction details as JSON for the audit details modal."""
    txn = db.session.get(MoneyTransaction, txn_id)
    if not txn:
        return jsonify({'error': 'Transaction not found'}), 404
    return jsonify(txn.to_dict())


@admin_bp.route('/money-management/reconcile', methods=['POST'], strict_slashes=False)
@admin_bp.route('/money_management/reconcile', methods=['POST'], strict_slashes=False)
@admin_required
def reconcile_payments():
    """Admin tool to scan for any verified payments that might be missing from Money Management."""
    from services.money_service import reconcile_cashfree_payments
    try:
        count_added, total_checked = reconcile_cashfree_payments()
        if count_added > 0:
            flash(f"Reconciliation complete: {count_added} missing Cashfree payment(s) successfully recorded.", 'success')
        else:
            flash(f"Reconciliation complete: All {total_checked} paid transactions are fully up to date!", 'info')
    except Exception as e:
        flash(f"Reconciliation error: {str(e)}", 'danger')

    return redirect(url_for('admin.money_management'))


@admin_bp.route('/money-management/transactions/clear-all', methods=['POST'], strict_slashes=False)
@admin_bp.route('/money_management/transactions/clear-all', methods=['POST'], strict_slashes=False)
@admin_required
def clear_all_money_transactions():
    """
    Destructive Admin-Only action to clear all MoneyManagement ledger transactions.
    Requires explicit confirmation code ('CLEAR').
    Preserves all Payment, Application, Employee, and User records.
    """
    from services.money_service import clear_all_transactions

    confirmation = (request.form.get('confirmation') or '').strip()

    if confirmation.upper() != 'CLEAR':
        flash("Confirmation failed. You must type 'CLEAR' exactly to clear all transactions.", 'danger')
        return redirect(url_for('admin.money_management'))

    success, count, err = clear_all_transactions(admin_user=current_user)
    if success:
        flash("All transactions cleared successfully.", 'success')
    else:
        flash(f"Error clearing transactions: {err}", 'danger')

    return redirect(url_for('admin.money_management'))


# ==============================================================================
# PARTNER EARNINGS RECORD ENDPOINTS
# ==============================================================================

@admin_bp.route('/partner-earnings/create', methods=['POST'], endpoint='create_partner_earnings_record', strict_slashes=False)
@admin_bp.route('/partner_earnings/create', methods=['POST'], endpoint='create_partner_earnings_record_alias', strict_slashes=False)
@admin_required
def create_partner_earnings_record_route():
    """
    Creates and records a verified partner earnings contribution.
    """
    from services.money_service import create_partner_earnings_record

    partner_id = request.form.get('partner_id')
    amount = request.form.get('amount')
    earnings_date = request.form.get('earnings_date')
    description = request.form.get('description')
    reference = request.form.get('reference')
    notes = request.form.get('notes')
    date_filter = request.form.get('date_filter', 'all')

    success, record, err = create_partner_earnings_record(
        partner_id=partner_id,
        amount=amount,
        earnings_date=earnings_date,
        description=description,
        reference=reference,
        notes=notes,
        created_by=getattr(current_user, 'id', None)
    )

    if success:
        flash(f"Earnings record of ₹{record.amount:,.2f} recorded successfully for {record.partner.name}.", 'success')
    else:
        flash(err or "Failed to record partner earnings.", 'danger')

    return redirect(url_for('admin.money_management', date=date_filter))


@admin_bp.route('/partner-earnings/<int:record_id>/edit', methods=['POST'], endpoint='edit_partner_earnings_record', strict_slashes=False)
@admin_bp.route('/partner_earnings/<int:record_id>/edit', methods=['POST'], endpoint='edit_partner_earnings_record_alias', strict_slashes=False)
@admin_required
def edit_partner_earnings_record_route(record_id):
    """
    Updates an existing partner earnings contribution entry.
    """
    from services.money_service import update_partner_earnings_record

    partner_id = request.form.get('partner_id')
    amount = request.form.get('amount')
    earnings_date = request.form.get('earnings_date')
    description = request.form.get('description')
    reference = request.form.get('reference')
    notes = request.form.get('notes')
    date_filter = request.form.get('date_filter', 'all')

    success, record, err = update_partner_earnings_record(
        record_id=record_id,
        partner_id=partner_id,
        amount=amount,
        earnings_date=earnings_date,
        description=description,
        reference=reference,
        notes=notes
    )

    if success:
        flash(f"Partner earnings record updated successfully for {record.partner.name}.", 'success')
    else:
        flash(err or "Failed to update partner earnings record.", 'danger')

    return redirect(url_for('admin.money_management', date=date_filter))


@admin_bp.route('/partner-earnings/<int:record_id>/delete', methods=['POST'], endpoint='delete_partner_earnings_record', strict_slashes=False)
@admin_bp.route('/partner_earnings/<int:record_id>/delete', methods=['POST'], endpoint='delete_partner_earnings_record_alias', strict_slashes=False)
@admin_required
def delete_partner_earnings_record_route(record_id):
    """
    Permanently deletes a partner earnings contribution entry.
    """
    from services.money_service import delete_partner_earnings_record

    date_filter = request.form.get('date_filter', 'all')
    success, err = delete_partner_earnings_record(record_id)

    if success:
        flash("Partner earnings record deleted successfully.", 'success')
    else:
        flash(err or "Failed to delete partner earnings record.", 'danger')

    return redirect(url_for('admin.money_management', date=date_filter))


@admin_bp.route('/partner-earnings/<int:record_id>', methods=['GET'], endpoint='get_partner_earnings_record', strict_slashes=False)
@admin_bp.route('/partner_earnings/<int:record_id>', methods=['GET'], endpoint='get_partner_earnings_record_alias', strict_slashes=False)
@admin_required
def get_partner_earnings_record_detail(record_id):
    """
    Returns JSON details of a single partner earnings record for modal editing.
    """
    from models import PartnerEarningsRecord
    record = db.session.get(PartnerEarningsRecord, record_id)
    if not record:
        return jsonify({'error': 'Earnings record not found'}), 404
    return jsonify(record.to_dict())




# ==============================================================================
# RETIRED ADMINISTRATIVE MODULES
# ==============================================================================
# The following modules have been retired from the Anti-Matrix admin dashboard:
# - Candidate Applications (Candidate applications and records remain in database)
# - Employees (Employee records remain in database; active operations moved to Internship Portal)
# - Document & Email Templates
# - Internship Benefits
# - Contact Inquiries
#
# Any direct access or legacy bookmark automatically redirects to the Admin Dashboard
# with an informative notification. All endpoint names are preserved as compatibility
# aliases to prevent routing BuildErrors.
# ==============================================================================

# ==============================================================================
# CANDIDATE APPLICATIONS MODULE
# ==============================================================================

@admin_bp.route('/applications', strict_slashes=False)
@admin_required
def applications():
    """
    Candidate Applications Management Hub.
    Lists candidate applications with search, multi-criteria filtering,
    and stage tracking (Applied, Under Review, Shortlisted, Rejected).
    """
    job_id_filter = request.args.get('job_id', type=int)
    duration_filter = request.args.get('duration', '').strip()
    status_filter = request.args.get('status', 'all').strip()
    payment_filter = request.args.get('payment_status', 'all').strip()
    search_query = request.args.get('q', '').strip()

    query = JobApplication.query.join(JobPosting)

    if job_id_filter:
        query = query.filter(JobApplication.job_id == job_id_filter)

    if duration_filter and duration_filter.lower() != 'all':
        query = query.filter(JobApplication.duration == duration_filter)

    if status_filter and status_filter.lower() != 'all':
        status_map = {
            'applied': ['Applied', 'APPLIED', 'New'],
            'under_review': ['Under Review', 'UNDER_REVIEW', 'Reviewed'],
            'under review': ['Under Review', 'UNDER_REVIEW', 'Reviewed'],
            'shortlisted': ['Shortlisted', 'SHORTLISTED'],
            'rejected': ['Rejected', 'REJECTED', 'Not Selected']
        }
        allowed_statuses = status_map.get(status_filter.lower(), [status_filter])
        query = query.filter(JobApplication.status.in_(allowed_statuses))

    if payment_filter and payment_filter.lower() != 'all':
        if payment_filter.lower() == 'paid':
            query = query.filter(JobApplication.payment_status.in_(['paid', 'PAID', 'exempt']))
        elif payment_filter.lower() == 'pending':
            query = query.filter(JobApplication.payment_status.in_(['pending', 'PENDING']))
        elif payment_filter.lower() == 'failed':
            query = query.filter(JobApplication.payment_status.in_(['failed', 'FAILED']))
        else:
            query = query.filter(JobApplication.payment_status.ilike(payment_filter))

    if search_query:
        query = query.filter(
            (JobApplication.full_name.ilike(f'%{search_query}%')) |
            (JobApplication.email.ilike(f'%{search_query}%')) |
            (JobApplication.phone.ilike(f'%{search_query}%')) |
            (JobApplication.college.ilike(f'%{search_query}%')) |
            (JobApplication.skills.ilike(f'%{search_query}%')) |
            (JobApplication.application_code.ilike(f'%{search_query}%')) |
            (JobPosting.title.ilike(f'%{search_query}%')) |
            (JobPosting.job_code.ilike(f'%{search_query}%')) |
            (JobPosting.job_id.ilike(f'%{search_query}%')) |
            (JobPosting.department.ilike(f'%{search_query}%'))
        )

    all_applications = query.order_by(JobApplication.created_at.desc()).all()
    all_jobs = JobPosting.query.order_by(JobPosting.title.asc()).all()
    total_unfiltered_applications = JobApplication.query.count()

    return render_template(
        'admin/applications.html',
        applications=all_applications,
        all_jobs=all_jobs,
        total_unfiltered_applications=total_unfiltered_applications,
        selected_job_id=job_id_filter,
        selected_duration=duration_filter,
        selected_status=status_filter,
        selected_payment_status=payment_filter,
        search_query=search_query
    )


@admin_bp.route('/applications/<int:app_id>', strict_slashes=False)
@admin_required
def application_detail(app_id):
    """
    Detailed candidate application view with Application ID, contact information,
    academic credentials, recruitment stage manager, and acknowledgment email tracking.
    """
    application = db.session.get(JobApplication, app_id) or abort(404)
    job = application.job

    return render_template(
        'admin/application_detail.html',
        app=application,
        job=job
    )


@admin_bp.route('/applications/<int:app_id>/stage', methods=['POST'])
@admin_bp.route('/applications/<int:app_id>/status', methods=['POST'])
@admin_required
def update_application_stage(app_id):
    """
    Update candidate's recruitment stage between:
    - Applied
    - Under Review
    - Shortlisted
    - Rejected
    """
    application = db.session.get(JobApplication, app_id) or abort(404)
    raw_stage = (request.form.get('stage') or request.form.get('status') or '').strip()

    stage_map = {
        'applied': 'Applied',
        'new': 'Applied',
        'under review': 'Under Review',
        'under_review': 'Under Review',
        'reviewed': 'Under Review',
        'shortlisted': 'Shortlisted',
        'rejected': 'Rejected',
        'not selected': 'Rejected'
    }
    normalized = stage_map.get(raw_stage.lower())

    if not normalized:
        flash(f"Invalid recruitment stage: {raw_stage}", "danger")
        return redirect(request.referrer or url_for('admin.applications'))

    application.status = normalized
    application.application_status = normalized
    db.session.commit()
    flash(f"Application stage for candidate {application.full_name} updated to '{normalized}'.", "success")
    return redirect(request.referrer or url_for('admin.application_detail', app_id=application.id))


@admin_bp.route('/applications/<int:app_id>/send-acknowledgment', methods=['POST'])
@admin_bp.route('/applications/<int:app_id>/send-application-email', methods=['POST'])
@admin_required
def send_application_success_email_action(app_id):
    """
    Manual administrator trigger to send or resend the official acknowledgment email.
    """
    application = db.session.get(JobApplication, app_id) or abort(404)

    try:
        from services.email_service import send_application_successful_email
        success, msg = send_application_successful_email(application)
        if success:
            flash(f"Acknowledgment email sent successfully to {application.email}.", "success")
        else:
            flash(f"Failed to send email: {msg}", "danger")
    except Exception as e:
        current_app.logger.error(f"Error sending acknowledgment email for app {app_id}: {e}")
        flash(f"Unable to dispatch email: {e}", "danger")

    return redirect(request.referrer or url_for('admin.application_detail', app_id=application.id))


@admin_bp.route('/applications/clear-all', methods=['POST'])
@admin_bp.route('/applications/delete-all', methods=['POST'])
@admin_required
def clear_all_applications():
    """
    Clear all candidate applications upon typing DELETE.
    Safely preserves job postings, templates, and financial records.
    """
    confirmation = (request.form.get('confirmation') or '').strip()
    if confirmation != 'DELETE':
        flash('Deletion cancelled. You must type DELETE to confirm.', 'danger')
        return redirect(url_for('admin.applications'))

    total_apps = JobApplication.query.count()
    if total_apps == 0:
        flash('There are no candidate applications to delete.', 'info')
        return redirect(url_for('admin.applications'))

    try:
        apps = JobApplication.query.all()
        for app in apps:
            for path_attr in ['resume_path', 'aadhaar_path', 'pan_path', 'college_id_path']:
                fpath = getattr(app, path_attr, None)
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

        MoneyTransaction.query.filter(MoneyTransaction.application_id.isnot(None)).update({'application_id': None})
        Payment.query.delete()
        JobApplication.query.delete()
        db.session.commit()
        flash('All candidate applications and associated files have been cleared successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing applications: {e}")
        flash('Unable to clear candidate applications. No changes were made.', 'danger')

    return redirect(url_for('admin.applications'))


@admin_bp.route('/applications/<int:app_id>/document/<string:doc_type>')
@admin_required
def download_document(app_id, doc_type):
    """Secure, authenticated document download route."""
    application = db.session.get(JobApplication, app_id) or abort(404)
    as_attachment = request.args.get('download', '0') == '1'

    if doc_type == 'resume':
        folder = current_app.config.get('UPLOAD_FOLDER_RESUMES', os.path.join(current_app.root_path, 'uploads', 'resumes'))
        filename = application.resume_filename
        if application.resume_path and os.path.exists(application.resume_path):
            folder = os.path.dirname(application.resume_path)
            filename = os.path.basename(application.resume_path)
    elif doc_type == 'aadhaar':
        folder = current_app.config.get('UPLOAD_FOLDER_DOCUMENTS', os.path.join(current_app.root_path, 'uploads', 'documents'))
        filename = application.aadhaar_filename
    elif doc_type == 'pan':
        folder = current_app.config.get('UPLOAD_FOLDER_DOCUMENTS', os.path.join(current_app.root_path, 'uploads', 'documents'))
        filename = application.pan_filename
    elif doc_type == 'college_id':
        folder = current_app.config.get('UPLOAD_FOLDER_DOCUMENTS', os.path.join(current_app.root_path, 'uploads', 'documents'))
        filename = application.college_id_filename
    else:
        abort(404)

    if not filename:
        flash(f"No {doc_type} file found for candidate {application.full_name}.", 'warning')
        return redirect(url_for('admin.application_detail', app_id=application.id))

    return send_from_directory(folder, os.path.basename(filename), as_attachment=as_attachment)


@admin_bp.route('/applications/<int:app_id>/resume')
@admin_required
def download_resume(app_id):
    return download_document(app_id, 'resume')


# ==============================================================================
# TEMPLATES MANAGEMENT MODULE
# ==============================================================================

@admin_bp.route('/templates', methods=['GET'], strict_slashes=False)
@admin_bp.route('/template', methods=['GET'], strict_slashes=False)
@admin_bp.route('/templates/', methods=['GET'], strict_slashes=False)
@admin_required
def templates():
    """
    Centralized Email Template Management & Automation Mapping Hub.
    Allows viewing, creating, editing, duplicating, previewing, and mapping email templates.
    """
    from models import EmailTemplateMapping
    from services.email_template_service import (
        SUPPORTED_TEMPLATE_CATEGORIES,
        ensure_email_template_schema,
        ensure_default_templates_and_mappings
    )

    # Ensure schema and default templates exist
    try:
        ensure_email_template_schema()
    except Exception as e:
        current_app.logger.warning(f"Note on template schema initialization: {e}")

    try:
        email_templates = EmailTemplate.query.order_by(EmailTemplate.category, EmailTemplate.name).all()
    except Exception as e:
        current_app.logger.warning(f"Error querying templates with category ordering: {e}")
        try:
            db.session.rollback()
            email_templates = EmailTemplate.query.all()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            email_templates = []

    try:
        mappings = EmailTemplateMapping.query.order_by(EmailTemplateMapping.id).all()
    except Exception as e:
        current_app.logger.warning(f"Error querying template mappings: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        mappings = []
    
    # Backward compatibility helper for single template reference
    app_success_email = next((t for t in email_templates if t.template_type == 'application_successful'), None)

    active_tab = request.args.get('tab', 'templates')

    return render_template(
        'admin/templates.html',
        templates=email_templates,
        mappings=mappings,
        categories=SUPPORTED_TEMPLATE_CATEGORIES,
        active_tab=active_tab,
        app_success_email=app_success_email
    )


@admin_bp.route('/templates/create', methods=['POST'], endpoint='create_email_template', strict_slashes=False)
@admin_required
def create_email_template():
    """
    Create a new email template with uniqueness validation.
    """
    from services.email_template_service import (
        validate_template_name,
        slugify,
        generate_unique_slug
    )

    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    category = (request.form.get('category') or 'Recruitment').strip()
    subject = (request.form.get('subject') or '').strip()
    body = (request.form.get('body') or '').strip()
    is_active = request.form.get('is_active') in ['true', 'on', '1', True]

    is_valid, err_msg = validate_template_name(name)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(url_for('admin.templates'))

    if not subject:
        flash('Email Subject is required.', 'danger')
        return redirect(url_for('admin.templates'))

    if not body:
        flash('Email Body is required.', 'danger')
        return redirect(url_for('admin.templates'))

    slug = generate_unique_slug(slugify(name))

    new_tmpl = EmailTemplate(
        template_type=slug,
        name=name,
        description=description,
        category=category,
        subject=subject,
        body=body,
        is_active=is_active
    )
    db.session.add(new_tmpl)
    db.session.commit()

    flash(f"Email template '{name}' created successfully.", 'success')
    return redirect(url_for('admin.templates'))


@admin_bp.route('/templates/<int:template_id>/edit', methods=['POST'], strict_slashes=False)
@admin_required
def edit_template(template_id):
    """
    Edit an existing email template. Renaming safely preserves foreign key event mappings.
    """
    from models import EmailTemplateMapping
    from services.email_template_service import validate_template_name

    tmpl = db.session.get(EmailTemplate, template_id)
    if not tmpl:
        flash('Template not found.', 'danger')
        return redirect(url_for('admin.templates'))

    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    category = (request.form.get('category') or tmpl.category or 'Recruitment').strip()
    subject = (request.form.get('subject') or '').strip()
    body = (request.form.get('body') or '').strip()
    is_active = request.form.get('is_active') in ['true', 'on', '1', True]

    is_valid, err_msg = validate_template_name(name, current_id=tmpl.id)
    if not is_valid:
        flash(err_msg, 'danger')
        return redirect(url_for('admin.templates'))

    if not subject or not body:
        flash('Subject and Body are required for email templates.', 'danger')
        return redirect(url_for('admin.templates'))

    # Check if deactivating a template that is mapped to an active event
    warning_notice = None
    if tmpl.is_active and not is_active:
        active_mappings = EmailTemplateMapping.query.filter_by(
            email_template_id=tmpl.id,
            is_active=True
        ).all()
        if active_mappings:
            event_names = ", ".join([m.event_label for m in active_mappings])
            warning_notice = (
                f"Template '{name}' was deactivated. Warning: This template is mapped to active event(s): "
                f"{event_names}. Automated emails for these events are paused until an active template is assigned."
            )

    tmpl.name = name
    tmpl.description = description
    tmpl.category = category
    tmpl.subject = subject
    tmpl.body = body
    tmpl.is_active = is_active

    db.session.commit()

    if warning_notice:
        flash(warning_notice, 'warning')
    else:
        flash(f"Template '{name}' updated successfully.", 'success')

    return redirect(url_for('admin.templates'))


@admin_bp.route('/templates/<int:template_id>/duplicate', methods=['POST'], strict_slashes=False)
@admin_required
def duplicate_template_route(template_id):
    """
    Duplicate an existing email template with a unique name and slug.
    """
    from services.email_template_service import duplicate_template

    cloned = duplicate_template(template_id)
    if cloned:
        flash(f"Template duplicated successfully as '{cloned.name}'.", 'success')
    else:
        flash("Could not duplicate template: source template not found.", 'danger')

    return redirect(url_for('admin.templates'))


@admin_bp.route('/templates/<int:template_id>/toggle-status', methods=['POST'], strict_slashes=False)
@admin_required
def toggle_template_status(template_id):
    """
    Toggle active/inactive status of an email template.
    """
    from models import EmailTemplateMapping

    tmpl = db.session.get(EmailTemplate, template_id)
    if not tmpl:
        flash('Template not found.', 'danger')
        return redirect(url_for('admin.templates'))

    tmpl.is_active = not tmpl.is_active
    db.session.commit()

    if not tmpl.is_active:
        active_mappings = EmailTemplateMapping.query.filter_by(
            email_template_id=tmpl.id,
            is_active=True
        ).all()
        if active_mappings:
            event_names = ", ".join([m.event_label for m in active_mappings])
            flash(
                f"Template '{tmpl.name}' is now Inactive. Warning: This template is mapped to active event(s): "
                f"{event_names}. Automated emails for these events will be paused until an active template is assigned.",
                'warning'
            )
            return redirect(url_for('admin.templates'))

    new_status = 'Active' if tmpl.is_active else 'Inactive'
    flash(f"Template '{tmpl.name}' status set to {new_status}.", 'success')
    return redirect(url_for('admin.templates'))


@admin_bp.route('/templates/<int:template_id>/delete', methods=['POST'], strict_slashes=False)
@admin_required
def delete_template(template_id):
    """
    Safely delete an email template.
    Prevents deletion if the template is currently mapped to an active event automation.
    """
    from models import EmailTemplateMapping
    from services.email_template_service import can_delete_template

    can_delete, reason, active_mappings = can_delete_template(template_id)
    if not can_delete:
        flash(reason, 'danger')
        return redirect(url_for('admin.templates'))

    tmpl = db.session.get(EmailTemplate, template_id)
    tmpl_name = tmpl.name

    # Disassociate any inactive mappings referencing this template
    inactive_mappings = EmailTemplateMapping.query.filter_by(email_template_id=template_id).all()
    for m in inactive_mappings:
        m.email_template_id = None

    db.session.delete(tmpl)
    db.session.commit()

    flash(f"Template '{tmpl_name}' deleted successfully.", 'success')
    return redirect(url_for('admin.templates'))


@admin_bp.route('/templates/<int:template_id>/preview', methods=['GET'], strict_slashes=False)
@admin_required
def preview_template_by_id(template_id):
    """
    Preview rendered HTML email with sample preview values by template ID.
    """
    from services.email_service import render_sample_email_preview
    preview_data = render_sample_email_preview(template_id)
    return jsonify(preview_data)


@admin_bp.route('/templates/mappings/update', methods=['POST'], strict_slashes=False)
@admin_required
def update_event_mapping():
    """
    Update or save an email automation event mapping.
    Ensures safe foreign key mapping, delay configuration, and validation.
    """
    from models import EmailTemplateMapping

    event_key = (request.form.get('event_key') or '').strip()
    template_id_raw = (request.form.get('email_template_id') or '').strip()
    delay_minutes_raw = (request.form.get('delay_minutes') or '0').strip()
    is_active = request.form.get('is_active') in ['true', 'on', '1', True]

    if not event_key:
        flash('Event key is required.', 'danger')
        return redirect(url_for('admin.templates', tab='mappings'))

    mapping = EmailTemplateMapping.query.filter_by(event_key=event_key).first()
    if not mapping:
        flash('Invalid event mapping.', 'danger')
        return redirect(url_for('admin.templates', tab='mappings'))

    # Parse template ID
    template_id = None
    if template_id_raw and template_id_raw.isdigit():
        template_id = int(template_id_raw)

    # Parse delay minutes
    delay_minutes = 0
    if delay_minutes_raw.isdigit():
        delay_minutes = max(0, int(delay_minutes_raw))

    # Validation: if mapping is set to active, require a valid, active template
    if is_active:
        if not template_id:
            flash(f"Cannot enable automation for '{mapping.event_label}': Please select a template.", 'danger')
            return redirect(url_for('admin.templates', tab='mappings'))

        selected_tmpl = db.session.get(EmailTemplate, template_id)
        if not selected_tmpl:
            flash(f"Selected template does not exist.", 'danger')
            return redirect(url_for('admin.templates', tab='mappings'))

        if not selected_tmpl.is_active:
            flash(
                f"Cannot activate automation for '{mapping.event_label}': The selected template '{selected_tmpl.name}' is inactive. "
                f"Please activate the template first or choose an active template.",
                'danger'
            )
            return redirect(url_for('admin.templates', tab='mappings'))

    mapping.email_template_id = template_id
    mapping.delay_minutes = delay_minutes
    mapping.is_active = is_active
    db.session.commit()

    flash(f"Automation mapping for '{mapping.event_label}' updated successfully.", 'success')
    return redirect(url_for('admin.templates', tab='mappings'))


# --- Backward Compatibility Endpoints ---

@admin_bp.route('/templates/email/<string:template_type>', methods=['POST'], strict_slashes=False)
@admin_required
def update_email_template(template_type):
    """
    Update subject and body for an email template by slug (backward compatibility).
    """
    valid_types = ['application_successful', 'application_acknowledgment']
    if template_type not in valid_types:
        flash('Invalid email template type.', 'danger')
        return redirect(url_for('admin.templates'))

    subject = (request.form.get('subject') or '').strip()
    body = (request.form.get('body') or '').strip()

    if not subject or not body:
        flash('Subject and Body are required for email templates.', 'danger')
        return redirect(url_for('admin.templates'))

    email_tmpl = EmailTemplate.query.filter_by(template_type='application_successful').first()
    if not email_tmpl:
        email_tmpl = EmailTemplate(
            template_type='application_successful',
            name='Application Acknowledgment',
            subject=subject,
            body=body
        )
        db.session.add(email_tmpl)
    else:
        email_tmpl.subject = subject
        email_tmpl.body = body

    db.session.commit()
    flash("Application Acknowledgment email template updated successfully.", 'success')
    return redirect(url_for('admin.templates'))


@admin_bp.route('/templates/email/<string:template_type>/preview', methods=['GET'], strict_slashes=False)
@admin_required
def preview_email_template(template_type):
    """
    Preview rendered HTML email with sample candidate data by slug (backward compatibility).
    """
    from services.email_service import render_sample_email_preview
    actual_type = 'application_successful' if template_type in ['application_successful', 'application_acknowledgment'] else template_type
    preview_data = render_sample_email_preview(actual_type)
    return jsonify(preview_data)


@admin_bp.route('/templates/email/<string:template_type>/test', methods=['POST'], strict_slashes=False)
@admin_required
def send_test_email_route(template_type):
    """
    Send sample test acknowledgment email to admin-specified address.
    """
    recipient_email = (request.form.get('test_recipient') or '').strip()
    if not recipient_email:
        flash('Please specify a recipient email address for testing.', 'danger')
        return redirect(url_for('admin.templates'))

    from services.email_service import send_test_email
    actual_type = 'application_successful' if template_type in ['application_successful', 'application_acknowledgment'] else template_type
    success, msg = send_test_email(actual_type, recipient_email)
    if success:
        flash(f"Test email sent to {recipient_email}: {msg}", 'success')
    else:
        flash(f"Failed to send test email: {msg}", 'danger')

    return redirect(url_for('admin.templates'))


# ==============================================================================
# RETIRED MODULES COMPATIBILITY STUBS
# ==============================================================================

def _retired_module_redirect():
    flash("This administrative module has been retired.", "info")
    return redirect(url_for('admin.dashboard'))


# --- Employees (Retired) ---
@admin_bp.route('/employees', methods=['GET', 'POST'], strict_slashes=False)
@admin_bp.route('/employees/<path:subpath>', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def employees(subpath=None, *args, **kwargs):
    return _retired_module_redirect()


@admin_bp.route('/employees/create', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def create_employee(*args, **kwargs):
    return _retired_module_redirect()


@admin_bp.route('/employees/<string:employee_id>', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def view_employee(employee_id=None, *args, **kwargs):
    return _retired_module_redirect()


# --- Internship Benefits (Retired) ---
@admin_bp.route('/internship-benefits', methods=['GET', 'POST'], strict_slashes=False)
@admin_bp.route('/internship-benefits/<path:subpath>', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def internship_benefits(subpath=None, *args, **kwargs):
    return _retired_module_redirect()


# --- Contact Inquiries (Retired) ---
@admin_bp.route('/inquiries', methods=['GET', 'POST'], strict_slashes=False)
@admin_bp.route('/inquiries/<path:subpath>', methods=['GET', 'POST'], strict_slashes=False)
@admin_required
def inquiries(subpath=None, *args, **kwargs):
    return _retired_module_redirect()


# Compatibility aliases for legacy endpoint resolution:
_RETIRED_ENDPOINTS = [
    'mark_application_under_review', 'mark_application_shortlisted',
    'mark_application_offer_complete', 'mark_application_hired',
    'send_joining_email_action', 'retry_shortlist_offer_email',
    'download_application_offer_letter', 'preview_application_offer_letter_file',
    'preview_application_offer_letter_pdf', 'preview_application_offer_letter',
    'preview_document_file_by_id', 'preview_document_pdf_by_id',
    'preview_document_by_id', 'update_application_payment_status',
    'admin_reset_employee_password', 'upload_document_template',
    'assign_job_to_template', 'activate_document_template',
    'deactivate_document_template', 'delete_document_template',
    'download_document_template_by_id', 'preview_document_template_info',
    'download_document_template', 'generate_offer_letter', 'preview_offer_letter',
    'verify_offer_letter', 'send_offer_letter', 'add_internship_benefit',
    'edit_internship_benefit', 'delete_internship_benefit',
    'reset_default_internship_benefits', 'get_inquiry_detail',
    'toggle_inquiry_status', 'delete_inquiry', 'mark_all_inquiries_read',
    'delete_all_inquiries'
]

def _retired_stub(*args, **kwargs):
    return _retired_module_redirect()

for _ep in _RETIRED_ENDPOINTS:
    admin_bp.add_url_rule(f'/_retired/{_ep}', endpoint=_ep, view_func=_retired_stub, methods=['GET', 'POST'])
