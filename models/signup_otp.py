from datetime import datetime, timezone, timedelta
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


class EmailVerificationOTP(db.Model):
    __tablename__ = 'email_verification_otps'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    candidate_name = db.Column(db.String(120), nullable=True)
    otp_hash = db.Column(db.String(256), nullable=False)
    verification_token = db.Column(db.String(100), nullable=True, unique=True, index=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    resend_available_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    @classmethod
    def generate_otp_code(cls) -> str:
        """Generates a cryptographically secure 6-digit decimal string."""
        return f"{secrets.randbelow(900000) + 100000:06d}"

    def set_otp(self, otp_plain: str):
        self.otp_hash = generate_password_hash(str(otp_plain).strip())

    def check_otp(self, otp_plain: str) -> bool:
        if not self.otp_hash or not otp_plain:
            return False
        return check_password_hash(self.otp_hash, str(otp_plain).strip())

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp is None:
            return True
        if exp.tzinfo is None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
        return now > exp

    @property
    def can_resend(self) -> bool:
        now = datetime.now(timezone.utc)
        resend_time = self.resend_available_at
        if resend_time is None:
            return True
        if resend_time.tzinfo is None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
        return now >= resend_time

    @property
    def remaining_resend_seconds(self) -> int:
        now = datetime.now(timezone.utc)
        resend_time = self.resend_available_at
        if resend_time is None:
            return 0
        if resend_time.tzinfo is None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
        if now >= resend_time:
            return 0
        diff = (resend_time - now).total_seconds()
        return max(0, int(diff))

    def __repr__(self):
        return f"<EmailVerificationOTP id={self.id} email='{self.email}' verified={self.is_verified} used={self.is_used}>"
