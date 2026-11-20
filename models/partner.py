from datetime import datetime, timezone
from . import db


class Partner(db.Model):
    """
    Model representing company partners contributing to Anti-Matrix income and projects.
    """
    __tablename__ = 'partners'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    email = db.Column(db.String(120), nullable=True, unique=True, index=True)
    role_title = db.Column(db.String(100), default='Partner', nullable=False)
    profile_picture = db.Column(db.String(500), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user = db.relationship('User', foreign_keys=[user_id], lazy=True)

    @property
    def initials(self):
        parts = (self.name or '').strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        elif parts and parts[0]:
            return parts[0][:2].upper()
        return "AM"

    def __repr__(self):
        return f"<Partner id={self.id} name='{self.name}' active={self.is_active}>"
