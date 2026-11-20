import re
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Employee, JobApplication, EmailVerificationOTP
from services.email_service import send_signup_otp_email
from services.oauth_service import (
    oauth,
    is_google_configured,
    is_github_configured,
    get_google_redirect_uri,
    get_github_redirect_uri,
    find_or_create_oauth_user,
    sync_users_sequence
)

auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r'^\S+@\S+\.\S+$')


def get_safe_redirect(target_url, default='/'):
    """
    Validate redirect URL to prevent Open Redirect vulnerabilities.
    Only allows internal, relative application paths.
    """
    if not default:
        default = '/'
    if not target_url or not isinstance(target_url, str):
        return default
    target_url = target_url.strip()
    if not target_url.startswith('/') or target_url.startswith('//') or '\\' in target_url:
        return default
    try:
        parsed = urlparse(target_url)
        if parsed.netloc or parsed.scheme:
            return default
        return target_url
    except Exception:
        return default


_AUTH_SCHEMA_INITIALIZED = False


def ensure_auth_otp_schema():
    """
    Safely inspects and self-heals database schema for authentication & OTP verification.
    Ensures:
    1. 'email_verification_otps' table exists.
    2. 'email_verified' column exists on 'users' table.
    Works seamlessly across PostgreSQL and SQLite, preventing 500 crashes on production VPS.
    """
    global _AUTH_SCHEMA_INITIALIZED
    if _AUTH_SCHEMA_INITIALIZED:
        return True

    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # 1. Ensure email_verification_otps table exists
        if 'email_verification_otps' not in table_names:
            try:
                EmailVerificationOTP.__table__.create(db.engine, checkfirst=True)
                if current_app:
                    current_app.logger.info("[AuthService] 'email_verification_otps' table created successfully.")
            except Exception as e:
                if current_app:
                    current_app.logger.warning(f"[AuthService] Table creation note for email_verification_otps: {e}")

        # 2. Ensure email_verified column exists on users table
        if 'users' in table_names:
            u_cols = [c['name'] for c in inspector.get_columns('users')]
            if 'email_verified' not in u_cols:
                with db.engine.begin() as conn:
                    dialect_name = db.engine.dialect.name
                    if dialect_name == 'postgresql':
                        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE"))
                    else:
                        conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
                if current_app:
                    current_app.logger.info("[AuthService] Added email_verified column to users table.")

        _AUTH_SCHEMA_INITIALIZED = True
        return True
    except Exception as e:
        if current_app:
            current_app.logger.warning(f"[AuthService] Schema initialization note: {e}")
        return False


@auth_bp.before_request
def auto_heal_auth_schema():
    ensure_auth_otp_schema()


@auth_bp.after_request
def add_auth_cache_control(response):
    """
    Ensure browser and intermediate caches do not store auth responses or forms.
    Prevents persistent 404/form state caching in browsers.
    """
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@auth_bp.route('/login', methods=['GET', 'POST'], strict_slashes=False)
def login():
    raw_target = (
        request.args.get('next') or
        request.args.get('redirect') or
        request.form.get('redirect') or
        request.form.get('next')
    )
    redirect_target = get_safe_redirect(raw_target)
    
    if current_user.is_authenticated:
        if getattr(current_user, 'role', '') == 'admin' and (not raw_target or redirect_target == '/'):
            return redirect(url_for('admin.dashboard'))
        return redirect(redirect_target)

    # Contextual guidance for job application redirect
    if request.method == 'GET' and raw_target and '/careers/apply' in raw_target:
        flashes = session.get('_flashes', [])
        has_msg = any('continue your job application' in str(f[1]) for f in flashes)
        if not has_msg:
            flash('Please log in or create an account to continue your job application.', 'info')

    if request.method == 'POST':
        is_json = request.is_json
        data = request.get_json() if is_json else request.form

        identifier = (data.get('email') or data.get('identifier') or '').strip()
        password = data.get('password') or ''
        remember = bool(data.get('remember', False))
        if isinstance(data.get('remember'), str):
            remember = data.get('remember') in ('true', '1', 'on', 'yes')

        # Check for redirect inside POST payload
        post_target = data.get('redirect') or data.get('next') or raw_target
        redirect_target = get_safe_redirect(post_target)

        errors = {}
        if not identifier:
            errors['email'] = 'Email or Employee ID is required'

        if not password:
            errors['password'] = 'Password is required'
        elif len(password) < 6:
            errors['password'] = 'Password must be at least 6 characters'

        if errors:
            if is_json:
                return jsonify({'status': 'error', 'errors': errors}), 400
            for field, err in errors.items():
                flash(err, 'error')
            return render_template('auth/login.html', errors=errors, email=identifier, redirect_target=redirect_target), 400

        authenticated_user = None

        is_email = bool(EMAIL_REGEX.match(identifier))
        is_emp_id = bool(re.match(r'^AM[A-Za-z0-9]+$', identifier, re.IGNORECASE))

        if is_email:
            # 1. Primary Authentication: Look up registered User by email
            try:
                user = User.query.filter(User.email.ilike(identifier)).first()
                if user and user.check_password(password):
                    authenticated_user = user
            except Exception as u_err:
                current_app.logger.error(f"Error querying User by email: {u_err}")
                db.session.rollback()

            # 2. Fallback Authentication: Candidate with Employee / Application record
            if not authenticated_user:
                try:
                    emp_by_email = Employee.query.join(JobApplication).filter(JobApplication.email.ilike(identifier)).first()
                    if emp_by_email:
                        is_valid = emp_by_email.check_password(password) or (
                            hasattr(emp_by_email, 'onboarding_credential') and
                            emp_by_email.onboarding_credential is not None and
                            emp_by_email.onboarding_credential.verify_password(password)
                        )
                        if is_valid:
                            cand_name = getattr(emp_by_email, 'candidate_name', None) or identifier.split('@')[0].capitalize()
                            cand_email = identifier.lower().strip()
                            try:
                                u = User.query.filter(User.email.ilike(cand_email)).first()
                                if not u:
                                    u = User(
                                        name=cand_name,
                                        email=cand_email,
                                        role='member'
                                    )
                                    u.set_password(password)
                                    db.session.add(u)
                                    db.session.commit()
                                elif getattr(u, 'role', '') != 'admin':
                                    u.set_password(password)
                                    db.session.commit()
                                authenticated_user = u
                            except Exception as sync_err:
                                current_app.logger.warning(f"Note on syncing user for employee: {sync_err}")
                                db.session.rollback()
                except Exception as emp_err:
                    current_app.logger.warning(f"Employee candidate lookup fallback skipped: {emp_err}")
                    db.session.rollback()

        elif is_emp_id:
            # Look up candidate by unique Employee ID (e.g. AM4827)
            try:
                emp_match = Employee.query.filter(Employee.employee_id.ilike(identifier)).first()
                if emp_match:
                    is_valid = emp_match.check_password(password) or (
                        hasattr(emp_match, 'onboarding_credential') and
                        emp_match.onboarding_credential is not None and
                        emp_match.onboarding_credential.verify_password(password)
                    )
                    if is_valid:
                        cand_email = (getattr(emp_match, 'candidate_email', None) or '').lower().strip()
                        cand_name = getattr(emp_match, 'candidate_name', None) or f"Employee {emp_match.employee_id}"
                        try:
                            u = User.query.filter(User.email.ilike(cand_email)).first() if cand_email else None
                            if not u and cand_email:
                                u = User(
                                    name=cand_name,
                                    email=cand_email,
                                    role='member'
                                )
                                u.set_password(password)
                                db.session.add(u)
                                db.session.commit()
                            elif u and getattr(u, 'role', '') != 'admin':
                                u.set_password(password)
                                db.session.commit()
                            authenticated_user = u
                        except Exception as sync_err:
                            current_app.logger.warning(f"Note on syncing user for employee ID: {sync_err}")
                            db.session.rollback()
            except Exception as emp_id_err:
                current_app.logger.warning(f"Employee ID lookup failed: {emp_id_err}")
                db.session.rollback()

        else:
            errors['email'] = 'Enter a valid email address or Employee ID (e.g. AM4827)'
            if is_json:
                return jsonify({'status': 'error', 'errors': errors}), 400
            flash('Enter a valid email address or Employee ID (e.g. AM4827)', 'error')
            return render_template('auth/login.html', errors=errors, email=identifier, redirect_target=redirect_target), 400

        if not authenticated_user:
            errors['password'] = 'Invalid email or password'
            if is_json:
                return jsonify({'status': 'error', 'errors': errors}), 401
            flash('Invalid email or password', 'error')
            return render_template('auth/login.html', errors=errors, email=identifier, redirect_target=redirect_target), 401

        login_user(authenticated_user, remember=remember)

        # Update last_login timestamp safely
        try:
            if hasattr(authenticated_user, 'last_login'):
                from datetime import datetime, timezone
                authenticated_user.last_login = datetime.now(timezone.utc)
                db.session.commit()
        except Exception:
            db.session.rollback()

        # Direct admin users to Admin Dashboard if no specific internal redirect was requested
        final_redirect = redirect_target
        if getattr(authenticated_user, 'role', '') == 'admin' and (not raw_target or redirect_target == '/'):
            final_redirect = url_for('admin.dashboard')

        if is_json:
            user_data = {}
            try:
                user_data = authenticated_user.to_dict()
            except Exception:
                user_data = {
                    'id': getattr(authenticated_user, 'id', None),
                    'name': getattr(authenticated_user, 'name', ''),
                    'email': getattr(authenticated_user, 'email', ''),
                    'role': getattr(authenticated_user, 'role', 'member')
                }
            return jsonify({
                'status': 'success',
                'message': 'Welcome back!',
                'redirect': final_redirect,
                'user': user_data
            })

        return redirect(final_redirect)

    return render_template('auth/login.html', redirect_target=redirect_target, errors={})


@auth_bp.route('/auth/send-otp', methods=['POST'], strict_slashes=False)
@auth_bp.route('/signup/send-otp', methods=['POST'], strict_slashes=False)
def send_otp():
    """
    Step 1: Validate applicant details, generate a cryptographically secure 6-digit OTP,
    store its secure hash, enforce rate limits and cooldown, and email the verification code.
    """
    is_json = request.is_json
    data = request.get_json() if is_json else request.form

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()

    errors = {}
    if not name:
        errors['name'] = 'Full name is required'

    if not email:
        errors['email'] = 'Email is required'
    elif not EMAIL_REGEX.match(email):
        errors['email'] = 'Enter a valid email address'

    if errors:
        return jsonify({
            'status': 'error',
            'errors': errors,
            'message': next(iter(errors.values()))
        }), 400

    # Check whether the email is already registered
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            'status': 'error',
            'already_registered': True,
            'message': 'An account with this email already exists. Please log in.',
            'errors': {'email': 'An account with this email already exists. Please log in.'}
        }), 400

    # Rate limiting: Cooldown check (60 seconds)
    latest_otp = EmailVerificationOTP.query.filter_by(
        email=email,
        is_used=False
    ).order_by(EmailVerificationOTP.created_at.desc()).first()

    if latest_otp and not latest_otp.can_resend:
        rem = latest_otp.remaining_resend_seconds
        return jsonify({
            'status': 'error',
            'message': f'Please wait {rem} seconds before requesting a new code.',
            'retry_after': rem
        }), 429

    # Rate limiting: Maximum 10 requests per hour per email
    now_utc = datetime.now(timezone.utc)
    one_hour_ago = now_utc - timedelta(hours=1)
    hourly_count = EmailVerificationOTP.query.filter(
        EmailVerificationOTP.email == email,
        EmailVerificationOTP.created_at >= one_hour_ago
    ).count()

    if hourly_count >= 10:
        return jsonify({
            'status': 'error',
            'message': 'Too many verification code requests. Please try again later.'
        }), 429

    # Invalidate previous unverified OTP records for this email
    try:
        EmailVerificationOTP.query.filter_by(
            email=email,
            is_used=False
        ).update({'is_used': True})
        db.session.commit()
    except Exception as inv_err:
        db.session.rollback()
        current_app.logger.warning(f"Note on invalidating prior OTPs: {inv_err}")

    # Generate 6-digit OTP and store hashed
    otp_code = EmailVerificationOTP.generate_otp_code()
    otp_record = EmailVerificationOTP(
        email=email,
        candidate_name=name,
        attempts=0,
        is_verified=False,
        is_used=False,
        expires_at=now_utc + timedelta(minutes=5),
        resend_available_at=now_utc + timedelta(seconds=60)
    )
    otp_record.set_otp(otp_code)
    db.session.add(otp_record)
    try:
        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        current_app.logger.error(f"Failed to save OTP record: {db_err}")
        return jsonify({
            'status': 'error',
            'message': 'Unable to process verification code. Please try again.'
        }), 500

    # Send verification code email
    success, msg, _ = send_signup_otp_email(email, name, otp_code)
    if not success:
        current_app.logger.error(f"Email delivery failed for OTP to {email}: {msg}")
        return jsonify({
            'status': 'error',
            'message': 'Unable to send verification code email. Please check your email address or try again shortly.'
        }), 500

    return jsonify({
        'status': 'success',
        'message': "We've sent a verification code to your email address. Enter the code below to verify your email.",
        'email': email,
        'resend_in': 60
    })


@auth_bp.route('/auth/resend-otp', methods=['POST'], strict_slashes=False)
@auth_bp.route('/signup/resend-otp', methods=['POST'], strict_slashes=False)
def resend_otp():
    """
    Step 2 Resend: Invalidate prior code, enforce 60-second cooldown, generate new code,
    and email to applicant.
    """
    is_json = request.is_json
    data = request.get_json() if is_json else request.form

    email = (data.get('email') or '').strip().lower()

    if not email or not EMAIL_REGEX.match(email):
        return jsonify({
            'status': 'error',
            'message': 'Enter a valid email address.'
        }), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            'status': 'error',
            'already_registered': True,
            'message': 'An account with this email already exists. Please log in.'
        }), 400

    latest_otp = EmailVerificationOTP.query.filter_by(
        email=email
    ).order_by(EmailVerificationOTP.created_at.desc()).first()

    if not latest_otp:
        return jsonify({
            'status': 'error',
            'message': 'Please enter your name and email to request a verification code.'
        }), 400

    # Cooldown check
    if not latest_otp.can_resend:
        rem = latest_otp.remaining_resend_seconds
        return jsonify({
            'status': 'error',
            'message': f'Please wait {rem} seconds before requesting a new code.',
            'retry_after': rem
        }), 429

    now_utc = datetime.now(timezone.utc)
    one_hour_ago = now_utc - timedelta(hours=1)
    hourly_count = EmailVerificationOTP.query.filter(
        EmailVerificationOTP.email == email,
        EmailVerificationOTP.created_at >= one_hour_ago
    ).count()

    if hourly_count >= 10:
        return jsonify({
            'status': 'error',
            'message': 'Too many verification code requests. Please try again later.'
        }), 429

    # Invalidate previous OTPs
    try:
        EmailVerificationOTP.query.filter_by(
            email=email,
            is_used=False
        ).update({'is_used': True})
        db.session.commit()
    except Exception as inv_err:
        db.session.rollback()
        current_app.logger.warning(f"Note on invalidating prior OTPs on resend: {inv_err}")

    candidate_name = latest_otp.candidate_name or 'Applicant'
    otp_code = EmailVerificationOTP.generate_otp_code()
    new_otp = EmailVerificationOTP(
        email=email,
        candidate_name=candidate_name,
        attempts=0,
        is_verified=False,
        is_used=False,
        expires_at=now_utc + timedelta(minutes=5),
        resend_available_at=now_utc + timedelta(seconds=60)
    )
    new_otp.set_otp(otp_code)
    db.session.add(new_otp)
    try:
        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        current_app.logger.error(f"Failed to save resend OTP record: {db_err}")
        return jsonify({
            'status': 'error',
            'message': 'Unable to generate a new verification code. Please try again.'
        }), 500

    success, msg, _ = send_signup_otp_email(email, candidate_name, otp_code)
    if not success:
        current_app.logger.error(f"Email delivery failed on resend OTP to {email}: {msg}")
        return jsonify({
            'status': 'error',
            'message': 'Unable to send verification code email. Please try again shortly.'
        }), 500

    return jsonify({
        'status': 'success',
        'message': 'A new verification code has been sent to your email address.',
        'email': email,
        'resend_in': 60
    })


@auth_bp.route('/auth/verify-otp', methods=['POST'], strict_slashes=False)
@auth_bp.route('/signup/verify-otp', methods=['POST'], strict_slashes=False)
def verify_otp():
    """
    Step 2 Verify: Verify candidate OTP code using constant-time check, enforce 5-minute expiry,
    track attempts up to 5, and issue a secure single-use verification token.
    """
    is_json = request.is_json
    data = request.get_json() if is_json else request.form

    email = (data.get('email') or '').strip().lower()
    otp_code = (data.get('otp') or '').strip()

    if not email or not otp_code:
        return jsonify({
            'status': 'error',
            'message': 'Email address and 6-digit verification code are required.'
        }), 400

    if not re.match(r'^\d{6}$', otp_code):
        return jsonify({
            'status': 'error',
            'message': 'Verification code must be exactly 6 digits.'
        }), 400

    record = EmailVerificationOTP.query.filter_by(
        email=email,
        is_verified=False,
        is_used=False
    ).order_by(EmailVerificationOTP.created_at.desc()).first()

    if not record:
        return jsonify({
            'status': 'error',
            'message': 'No active verification code found. Please request a new code.'
        }), 400

    # Expiration check (5 minutes)
    if record.is_expired:
        return jsonify({
            'status': 'error',
            'expired': True,
            'message': 'Verification code has expired. Please request a new code.'
        }), 400

    # Max 5 attempts check
    if record.attempts >= 5:
        return jsonify({
            'status': 'error',
            'lockout': True,
            'message': 'Maximum verification attempts exceeded. Please request a new code.'
        }), 400

    # Increment attempts
    record.attempts += 1
    db.session.commit()

    # Constant-time comparison
    if not record.check_otp(otp_code):
        remaining = 5 - record.attempts
        if remaining <= 0:
            return jsonify({
                'status': 'error',
                'lockout': True,
                'message': 'Maximum verification attempts exceeded. Please request a new code.',
                'remaining_attempts': 0
            }), 400
        return jsonify({
            'status': 'error',
            'message': f'Incorrect verification code. {remaining} attempt(s) remaining.',
            'remaining_attempts': remaining
        }), 400

    # Verification successful: generate single-use verification token
    verification_token = secrets.token_hex(32)
    record.is_verified = True
    record.verification_token = verification_token
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'Email verified successfully!',
        'email': email,
        'verification_token': verification_token
    })


@auth_bp.route('/signup', methods=['GET', 'POST'], strict_slashes=False)
def signup():
    raw_target = (
        request.args.get('next') or
        request.args.get('redirect') or
        request.form.get('redirect') or
        request.form.get('next')
    )
    redirect_target = get_safe_redirect(raw_target)

    if current_user.is_authenticated:
        return redirect(redirect_target)

    # Contextual guidance for job application redirect
    if request.method == 'GET' and raw_target and '/careers/apply' in raw_target:
        flashes = session.get('_flashes', [])
        has_msg = any('continue your job application' in str(f[1]) for f in flashes)
        if not has_msg:
            flash('Please log in or create an account to continue your job application.', 'info')

    if request.method == 'POST':
        is_json = request.is_json
        data = request.get_json() if is_json else request.form

        name = (data.get('name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        terms = bool(data.get('terms', False))
        if isinstance(data.get('terms'), str):
            terms = data.get('terms') in ('true', '1', 'on', 'yes')
        verification_token = (data.get('verification_token') or '').strip()

        post_target = data.get('redirect') or data.get('next') or raw_target
        redirect_target = get_safe_redirect(post_target)

        errors = {}
        if not name:
            errors['name'] = 'Full name is required'

        if not email:
            errors['email'] = 'Email is required'
        elif not EMAIL_REGEX.match(email):
            errors['email'] = 'Enter a valid email address'

        if not password:
            errors['password'] = 'Password is required'
        elif len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters'

        if not terms:
            errors['terms'] = 'You must accept the terms to continue'

        # Server-side verification enforcement: require valid verified OTP token
        verified_otp = None
        if not verification_token:
            errors['verification'] = 'Email verification is required before creating an account'
        else:
            verified_otp = EmailVerificationOTP.query.filter_by(
                email=email,
                verification_token=verification_token,
                is_verified=True,
                is_used=False
            ).first()
            if not verified_otp:
                errors['verification'] = 'Email verification is required before creating an account. Please verify your email.'

        # Check existing user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            errors['email'] = 'An account with this email already exists. Please log in.'

        if errors:
            msg = next(iter(errors.values()))
            if is_json:
                return jsonify({
                    'status': 'error',
                    'errors': errors,
                    'message': msg,
                    'already_registered': bool(existing_user)
                }), 400
            for field, err in errors.items():
                flash(err, 'error')
            return render_template(
                'auth/signup.html',
                errors=errors,
                name=name,
                email=email,
                redirect_target=redirect_target
            ), 400

        # Mark OTP verification token as used (single-use protection)
        if verified_otp:
            verified_otp.is_used = True
            db.session.commit()

        # Create account in existing User model with email marked verified
        sync_users_sequence()
        user = User(
            name=name,
            email=email,
            email_verified=True
        )
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception as signup_err:
            db.session.rollback()
            sync_users_sequence()
            user = User(
                name=name,
                email=email,
                email_verified=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

        login_user(user)

        if is_json:
            return jsonify({
                'status': 'success',
                'message': 'Account created successfully!',
                'redirect': redirect_target,
                'user': user.to_dict()
            })

        return redirect(redirect_target)

    return render_template('auth/signup.html', redirect_target=redirect_target, errors={})


@auth_bp.route('/logout', methods=['GET', 'POST'], strict_slashes=False)
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for('main.home'))


# ============================================================================
# Google OAuth 2.0 Authentication Routes
# ============================================================================

@auth_bp.route('/auth/google', strict_slashes=False)
@auth_bp.route('/login/google', strict_slashes=False)
def google_login():
    """Initiate Google OAuth 2.0 authorization redirect."""
    if current_user.is_authenticated:
        return redirect(get_safe_redirect(request.args.get('next') or request.args.get('redirect')))

    if not is_google_configured():
        flash("Google Login is currently not configured. Please sign in with your email or contact support.", "warning")
        return redirect(url_for('auth.login'))

    target_url = get_safe_redirect(request.args.get('next') or request.args.get('redirect'))
    session['oauth_next'] = target_url
    redirect_uri = get_google_redirect_uri()

    try:
        return oauth.google.authorize_redirect(redirect_uri)
    except Exception as e:
        current_app.logger.error(f"Failed to initiate Google OAuth redirect: {str(e)}")
        flash("Unable to initiate Google sign-in. Please try again or use email login.", "error")
        return redirect(url_for('auth.login'))


@auth_bp.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth 2.0 callback, verify token, and create/link session."""
    # Check for authorization error or user cancellation
    error = request.args.get('error')
    if error:
        if error in ('access_denied', 'user_cancelled_authorize'):
            flash("Google sign-in was cancelled.", "info")
        else:
            flash("Google authorization was not completed. Please try again.", "error")
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash("No authorization code received from Google. Please try again.", "error")
        return redirect(url_for('auth.login'))

    token = None
    user_info = None

    # Step 1: Attempt standard Authlib token exchange
    try:
        token = oauth.google.authorize_access_token()
        if token:
            user_info = token.get('userinfo')
            if not user_info:
                try:
                    user_info = oauth.google.parse_id_token(token)
                except Exception:
                    pass
            if not user_info:
                try:
                    user_info = oauth.google.userinfo(token=token)
                except Exception as ui_err:
                    current_app.logger.warning(f"Failed to fetch userinfo via Authlib: {str(ui_err)}")
    except Exception as authlib_err:
        current_app.logger.warning(
            f"Authlib token exchange failed ({type(authlib_err).__name__}: {authlib_err}). Attempting direct code exchange fallback..."
        )

    # Step 2: Fallback direct server-to-server exchange with Google (resilient to session/state drops & host differences)
    if not user_info and code:
        try:
            import requests
            client_id = current_app.config.get('GOOGLE_CLIENT_ID')
            client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
            
            candidate_uris = []
            primary_uri = get_google_redirect_uri()
            if primary_uri:
                candidate_uris.append(primary_uri)

            # Dynamic URI matching incoming request
            try:
                host_clean = request.host.split(':')[0].lower()
                scheme = 'https' if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https' else request.scheme
                dyn_uri = f"{scheme}://{request.host}/auth/google/callback"
                if dyn_uri not in candidate_uris:
                    candidate_uris.append(dyn_uri)
            except Exception:
                pass

            # Standard canonical variants
            for base in ('https://www.antimatrix.co.in/auth/google/callback', 'https://antimatrix.co.in/auth/google/callback'):
                if base not in candidate_uris:
                    candidate_uris.append(base)

            for cand_uri in candidate_uris:
                token_resp = requests.post(
                    'https://oauth2.googleapis.com/token',
                    data={
                        'code': code,
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'redirect_uri': cand_uri,
                        'grant_type': 'authorization_code'
                    },
                    headers={'Accept': 'application/json'},
                    timeout=12
                )

                if token_resp.status_code == 200:
                    token_data = token_resp.json()
                    access_token = token_data.get('access_token')
                    id_token = token_data.get('id_token')
                    if access_token:
                        uinfo_resp = requests.get(
                            'https://www.googleapis.com/oauth2/v3/userinfo',
                            headers={'Authorization': f"Bearer {access_token}"},
                            timeout=10
                        )
                        if uinfo_resp.status_code == 200:
                            user_info = uinfo_resp.json()
                            break
                    if not user_info and id_token:
                        tinfo_resp = requests.get(
                            f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}',
                            timeout=10
                        )
                        if tinfo_resp.status_code == 200:
                            user_info = tinfo_resp.json()
                            break
                elif 'redirect_uri_mismatch' in token_resp.text:
                    current_app.logger.info(f"Direct token exchange redirect_uri_mismatch for {cand_uri}, trying next...")
                    continue
                else:
                    current_app.logger.warning(
                        f"Direct Google token exchange returned status {token_resp.status_code}: {token_resp.text}"
                    )
                    break
        except Exception as fallback_err:
            current_app.logger.error(f"Direct token exchange fallback error: {str(fallback_err)}")

    if not user_info:
        flash("Unable to complete Google sign-in. Please try again or use your email and password.", "error")
        return redirect(url_for('auth.login'))

    email = user_info.get('email')
    if not email:
        flash("Google account did not provide an email address. Please sign in with another method.", "error")
        return redirect(url_for('auth.login'))

    name = user_info.get('name') or user_info.get('given_name')
    picture = user_info.get('picture')
    provider_id = user_info.get('sub')

    try:
        user = find_or_create_oauth_user(
            provider='google',
            provider_id=provider_id,
            email=email,
            name=name,
            picture=picture
        )
        login_user(user, remember=True)
        flash(f"Welcome to Anti-Matrix, {user.name}!", "success")
    except Exception as e:
        current_app.logger.error(f"Error saving Google OAuth user: {str(e)}")
        flash("An error occurred during sign-in. Please try again.", "error")
        return redirect(url_for('auth.login'))

    raw_next = session.pop('oauth_next', None)
    redirect_target = get_safe_redirect(raw_next or '/')
    if getattr(user, 'role', '') == 'admin' and (not raw_next or redirect_target == '/'):
        redirect_target = url_for('admin.dashboard')
    return redirect(redirect_target)


# ============================================================================
# GitHub OAuth 2.0 Authentication Routes (Deprecated - redirected gracefully)
# ============================================================================

@auth_bp.route('/auth/github', strict_slashes=False)
@auth_bp.route('/login/github', strict_slashes=False)
def github_login():
    """GitHub login is discontinued in favor of Google and Email authentication."""
    flash("GitHub sign-in is not supported. Please sign in with Google or your email.", "info")
    return redirect(url_for('auth.login'))


@auth_bp.route('/auth/github/callback')
def github_callback():
    """Redirect legacy GitHub callback back to login page."""
    return redirect(url_for('auth.login'))

    try:
        token = oauth.github.authorize_access_token()
    except Exception as e:
        current_app.logger.warning(f"GitHub OAuth token exchange failed: {str(e)}")
        flash("Unable to sign you in with GitHub. Please try again.", "error")
        return redirect(url_for('auth.login'))

    # Fetch GitHub user profile
    try:
        resp = oauth.github.get('user', token=token)
        profile = resp.json()
    except Exception as e:
        current_app.logger.warning(f"Failed to fetch GitHub profile: {str(e)}")
        flash("Unable to retrieve your GitHub profile. Please try again.", "error")
        return redirect(url_for('auth.login'))

    provider_id = profile.get('id')
    name = profile.get('name') or profile.get('login')
    picture = profile.get('avatar_url')
    email = profile.get('email')

    # If email is private in GitHub user profile, fetch from /user/emails endpoint
    if not email:
        try:
            emails_resp = oauth.github.get('user/emails', token=token)
            emails_data = emails_resp.json()
            if isinstance(emails_data, list):
                for em in emails_data:
                    if em.get('primary') and em.get('verified'):
                        email = em.get('email')
                        break
                if not email and emails_data:
                    for em in emails_data:
                        if em.get('verified'):
                            email = em.get('email')
                            break
                    if not email:
                        email = emails_data[0].get('email')
        except Exception as e:
            current_app.logger.warning(f"Failed to fetch GitHub emails: {str(e)}")

    if not email:
        flash("GitHub account does not have a verified email address. Please sign in with another method.", "error")
        return redirect(url_for('auth.login'))

    try:
        user = find_or_create_oauth_user(
            provider='github',
            provider_id=provider_id,
            email=email,
            name=name,
            picture=picture
        )
        login_user(user, remember=True)
        flash(f"Welcome back, {user.name}!", "success")
    except Exception as e:
        current_app.logger.error(f"Error saving GitHub OAuth user: {str(e)}")
        flash("An error occurred during sign-in. Please try again.", "error")
        return redirect(url_for('auth.login'))

    redirect_target = get_safe_redirect(session.pop('oauth_next', None) or '/')
    return redirect(redirect_target)

