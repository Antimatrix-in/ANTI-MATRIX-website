import logging
import secrets
from datetime import datetime, timezone
from flask import current_app, url_for
from authlib.integrations.flask_client import OAuth
from models import db, User

logger = logging.getLogger(__name__)

oauth = OAuth()


def init_oauth(app):
    """
    Initialize OAuth client with Flask application and register
    Google OpenID Connect and GitHub OAuth providers.
    """
    oauth.init_app(app)

    # Register Google (OpenID Connect via official Google discovery)
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID') or 'placeholder-client-id',
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET') or 'placeholder-client-secret',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    # Register GitHub (OAuth2)
    oauth.register(
        name='github',
        client_id=app.config.get('GITHUB_CLIENT_ID') or 'placeholder-client-id',
        client_secret=app.config.get('GITHUB_CLIENT_SECRET') or 'placeholder-client-secret',
        access_token_url='https://github.com/login/oauth/access_token',
        access_token_params=None,
        authorize_url='https://github.com/login/oauth/authorize',
        authorize_params=None,
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email read:user'},
    )


def is_google_configured(app=None) -> bool:
    """Check if valid Google OAuth credentials are configured in environment."""
    config = (app or current_app).config
    cid = (config.get('GOOGLE_CLIENT_ID') or '').strip()
    csec = (config.get('GOOGLE_CLIENT_SECRET') or '').strip()
    return bool(cid and csec and 'your-google' not in cid and 'placeholder' not in cid)


def is_github_configured(app=None) -> bool:
    """Check if valid GitHub OAuth credentials are configured in environment."""
    config = (app or current_app).config
    cid = (config.get('GITHUB_CLIENT_ID') or '').strip()
    csec = (config.get('GITHUB_CLIENT_SECRET') or '').strip()
    return bool(cid and csec and 'your-github' not in cid and 'placeholder' not in cid)


def get_google_redirect_uri() -> str:
    """
    Determine the authorized redirect URI for Google OAuth callback.
    1. Highest priority: GOOGLE_REDIRECT_URI explicitly set in .env or app config.
    2. Dynamic match based on current request host & scheme.
    3. APP_URL in app config / .env.
    4. Fall back to url_for('auth.google_callback', _external=True).
    """
    custom_uri = current_app.config.get('GOOGLE_REDIRECT_URI', '').strip()
    if custom_uri:
        return custom_uri

    try:
        from flask import request
        if request and request.host:
            host_clean = request.host.split(':')[0].lower()
            if host_clean in ('antimatrix.co.in', 'www.antimatrix.co.in'):
                return f"https://{host_clean}/auth/google/callback"
            scheme = 'https' if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https' else request.scheme
            return f"{scheme}://{request.host}/auth/google/callback"
    except Exception:
        pass

    app_url = current_app.config.get('APP_URL', '').strip()
    if app_url:
        return f"{app_url.rstrip('/')}/auth/google/callback"

    return url_for('auth.google_callback', _external=True)


def get_github_redirect_uri() -> str:
    """
    Determine the authorized redirect URI for GitHub OAuth callback.
    1. Highest priority: GITHUB_REDIRECT_URI explicitly set in .env.
    2. APP_URL set in .env.
    3. Fall back to url_for external.
    """
    custom_uri = current_app.config.get('GITHUB_REDIRECT_URI', '').strip()
    if custom_uri:
        return custom_uri

    app_url = current_app.config.get('APP_URL', '').strip()
    if app_url:
        return f"{app_url.rstrip('/')}/auth/github/callback"

    return url_for('auth.github_callback', _external=True)


from sqlalchemy import text


def sync_users_sequence():
    """Ensure PostgreSQL primary key sequence for users table is properly synchronized with MAX(id)."""
    try:
        if db.engine.dialect.name == 'postgresql':
            db.session.execute(text("""
                DO $$
                DECLARE
                    seq_name text;
                    max_id bigint;
                BEGIN
                    seq_name := pg_get_serial_sequence('users', 'id');
                    IF seq_name IS NOT NULL THEN
                        SELECT COALESCE(MAX(id), 0) + 1 INTO max_id FROM users;
                        PERFORM setval(seq_name, max_id, false);
                    END IF;
                END $$;
            """))
            db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning(f"Note on users sequence synchronization: {e}")


def find_or_create_oauth_user(provider: str, provider_id: str, email: str, name: str = None, picture: str = None) -> User:
    """
    Finds or creates a user account authenticated via an OAuth provider.
    Intelligently links existing accounts registered via email/password or another provider
    with the same verified email address without creating duplicates.
    Includes automated self-healing for PostgreSQL primary key sequences.
    """
    provider = (provider or '').lower().strip()
    provider_id_str = str(provider_id).strip() if provider_id is not None else None
    email_clean = (email or '').lower().strip()
    name_clean = (name or '').strip()
    picture_clean = (picture or '').strip() if picture else None
    if picture_clean and len(picture_clean) > 500:
        picture_clean = picture_clean[:500]

    if not email_clean:
        raise ValueError("An email address is required to create or link an account.")

    now_utc = datetime.now(timezone.utc)
    user = None

    # 1. First, search by provider + provider_id match
    if provider_id_str:
        user = User.query.filter_by(provider=provider, provider_id=provider_id_str).first()

    # 2. If not found, look up by verified email address for intelligent account linking
    if not user:
        user = User.query.filter(db.func.lower(db.func.trim(User.email)) == email_clean).first()
        if user:
            logger.info(f"Linking existing account (email: {email_clean}) to OAuth provider: {provider}")
            user.provider = provider
            if provider_id_str:
                user.provider_id = provider_id_str

    # 3. If user exists or was linked, update profile metadata and timestamp
    if user:
        if name_clean and (not user.name or '@' in user.name or user.name.startswith('User ')):
            user.name = name_clean[:120]
        if picture_clean and not user.profile_picture:
            user.profile_picture = picture_clean
        user.last_login = now_utc
        try:
            db.session.commit()
        except Exception as update_err:
            db.session.rollback()
            logger.warning(f"Could not update OAuth metadata for existing user: {update_err}")
        return user

    # 4. If user does not exist, create a new User account with self-healing sequence recovery
    fallback_name = (name_clean or email_clean.split('@')[0].capitalize())[:120]
    
    # Proactively sync Postgres sequence
    if db.engine.dialect.name == 'postgresql':
        sync_users_sequence()

    new_user = User(
        name=fallback_name,
        email=email_clean,
        role='member',
        provider=provider,
        provider_id=provider_id_str,
        profile_picture=picture_clean,
        is_active=True,
        last_login=now_utc,
        created_at=now_utc,
        updated_at=now_utc
    )
    new_user.set_password(secrets.token_urlsafe(32))

    try:
        db.session.add(new_user)
        db.session.commit()
        logger.info(f"Created new user account from OAuth provider {provider}: {email_clean}")
        return new_user
    except Exception as insert_err:
        logger.warning(f"Initial insert of OAuth user failed ({insert_err}). Attempting sequence recovery and retry...")
        try:
            db.session.rollback()
        except Exception:
            pass

        # Check if the user was concurrently created
        existing_user = User.query.filter(
            (db.func.lower(db.func.trim(User.email)) == email_clean) |
            ((User.provider == provider) & (User.provider_id == provider_id_str))
        ).first()
        if existing_user:
            logger.info(f"User found after concurrent creation: {existing_user.id}")
            if not existing_user.provider_id and provider_id_str:
                existing_user.provider_id = provider_id_str
                existing_user.provider = provider
            existing_user.last_login = now_utc
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return existing_user

        # Recover PostgreSQL sequence by forcefully advancing to MAX(id) + 10
        if db.engine.dialect.name == 'postgresql':
            try:
                db.session.execute(text("""
                    DO $$
                    DECLARE
                        seq_name text;
                        max_id bigint;
                    BEGIN
                        seq_name := pg_get_serial_sequence('users', 'id');
                        IF seq_name IS NOT NULL THEN
                            SELECT COALESCE(MAX(id), 0) + 10 INTO max_id FROM users;
                            PERFORM setval(seq_name, max_id, false);
                        END IF;
                    END $$;
                """))
                db.session.commit()
            except Exception as seq_err:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                logger.error(f"Failed to reset users sequence during retry: {seq_err}")

        # Retry creation with a fresh user instance
        retry_user = User(
            name=fallback_name,
            email=email_clean,
            role='member',
            provider=provider,
            provider_id=provider_id_str,
            profile_picture=picture_clean,
            is_active=True,
            last_login=now_utc,
            created_at=now_utc,
            updated_at=now_utc
        )
        retry_user.set_password(secrets.token_urlsafe(32))
        db.session.add(retry_user)
        db.session.commit()
        logger.info(f"Successfully created user account on retry after sequence healing: {email_clean}")
        return retry_user
