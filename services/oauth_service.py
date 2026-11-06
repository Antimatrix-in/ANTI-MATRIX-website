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


def find_or_create_oauth_user(provider: str, provider_id: str, email: str, name: str = None, picture: str = None) -> User:
    """
    Finds or creates a user account authenticated via an OAuth provider.
    Intelligently links existing accounts registered via email/password or another provider
    with the same verified email address without creating duplicates.
    """
    provider = (provider or '').lower().strip()
    provider_id_str = str(provider_id).strip() if provider_id is not None else None
    email_clean = (email or '').lower().strip()
    name_clean = (name or '').strip()
    picture_clean = (picture or '').strip() if picture else None

    if not email_clean:
        raise ValueError("An email address is required to create or link an account.")

    user = None

    # 1. First, search by provider + provider_id match
    if provider_id_str:
        user = User.query.filter_by(provider=provider, provider_id=provider_id_str).first()

    # 2. If not found, look up by verified email address for intelligent account linking
    if not user:
        user = User.query.filter(db.func.lower(User.email) == email_clean).first()
        if user:
            logger.info(f"Linking existing account (email: {email_clean}) to OAuth provider: {provider}")
            # Link this provider and provider_id to existing user
            user.provider = provider
            if provider_id_str:
                user.provider_id = provider_id_str

    # 3. If user exists or was linked, update profile metadata and timestamp
    if user:
        if name_clean and (not user.name or '@' in user.name or user.name.startswith('User ')):
            user.name = name_clean
        if picture_clean and not user.profile_picture:
            user.profile_picture = picture_clean
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        return user

    # 4. If user does not exist, create a new User account
    fallback_name = name_clean or email_clean.split('@')[0].capitalize()
    new_user = User(
        name=fallback_name,
        email=email_clean,
        role='member',
        provider=provider,
        provider_id=provider_id_str,
        profile_picture=picture_clean,
        is_active=True,
        last_login=datetime.now(timezone.utc)
    )
    # Generate an unguessable high-entropy dummy password hash for SQLite/DB NOT NULL safety
    new_user.set_password(secrets.token_urlsafe(32))
    
    db.session.add(new_user)
    db.session.commit()
    logger.info(f"Created new user account from OAuth provider {provider}: {email_clean}")
    return new_user
