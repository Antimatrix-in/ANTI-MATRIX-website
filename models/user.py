from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(20), default='member', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Social OAuth & Profile fields
    profile_picture = db.Column(db.String(500), nullable=True)
    provider = db.Column(db.String(50), default='email', nullable=False)  # 'email', 'google', 'github'
    provider_id = db.Column(db.String(255), nullable=True, index=True)
    phone = db.Column(db.String(50), nullable=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    applications = db.relationship('JobApplication', backref='user', lazy=True)

    @property
    def is_verified(self):
        return bool(self.email_verified)

    @property
    def phone_number(self):
        """Returns the user's phone or falls back to their most recent job application phone."""
        if self.phone and self.phone.strip():
            return self.phone.strip()
        if self.applications:
            for app in reversed(self.applications):
                if hasattr(app, 'phone') and app.phone and app.phone.strip():
                    return app.phone.strip()
        return None

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone_number,
            'role': self.role,
            'profile_picture': self.profile_picture,
            'provider': self.provider,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

    def __repr__(self):
        return f"<User id={self.id} email='{self.email}' name='{self.name}'>"
