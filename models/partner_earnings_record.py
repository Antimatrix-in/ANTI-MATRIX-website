from datetime import datetime, timezone, date
from . import db


class PartnerEarningsRecord(db.Model):
    """
    Model representing verified earnings contributions attributed to individual partners.
    Maintains a normalized, persistent database structure separate from the company ledger.
    """
    __tablename__ = 'partner_earnings_records'

    id = db.Column(db.Integer, primary_key=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id', ondelete='CASCADE'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)  # Amount in INR (must be > 0)
    earnings_date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date(), index=True)
    description = db.Column(db.String(255), nullable=True)
    reference = db.Column(db.String(150), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    partner = db.relationship('Partner', backref=db.backref('earnings_records', lazy=True, cascade='all, delete-orphan'))
    creator = db.relationship('User', foreign_keys=[created_by], lazy=True)

    def to_dict(self):
        """Returns dictionary representation for modals and API endpoints."""
        return {
            'id': self.id,
            'partner_id': self.partner_id,
            'partner_name': self.partner.name if self.partner else '',
            'partner_role': self.partner.role_title if self.partner else '',
            'amount': float(self.amount or 0),
            'formatted_amount': f"₹{self.amount:,.2f}" if self.amount else "₹0.00",
            'earnings_date': self.earnings_date.strftime('%Y-%m-%d') if self.earnings_date else '',
            'formatted_date': self.earnings_date.strftime('%d %b %Y') if self.earnings_date else '',
            'description': self.description or '',
            'reference': self.reference or '',
            'notes': self.notes or '',
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<PartnerEarningsRecord id={self.id} partner_id={self.partner_id} amount={self.amount} date={self.earnings_date}>"
