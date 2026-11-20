from datetime import datetime, timezone, date
from . import db


class MoneyTransaction(db.Model):
    """
    Model representing financial transactions (Income and Expense) for Anti-Matrix.
    Supports both automatic recordings from Cashfree and manual accounting entries.
    """
    __tablename__ = 'money_transactions'

    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'INCOME' or 'EXPENSE'
    amount = db.Column(db.Float, nullable=False)  # Amount in INR (must be > 0)
    transaction_date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    transaction_time = db.Column(db.String(20), nullable=True)  # e.g., "10:42 AM"
    
    category = db.Column(db.String(100), nullable=False)  # e.g. "Internship Application Fee", "Website Development", "Domain"
    purpose = db.Column(db.String(255), nullable=True)  # Short purpose/title
    description = db.Column(db.Text, nullable=True)  # Additional notes/details
    
    payment_method = db.Column(db.String(50), nullable=True)  # "Cashfree", "Bank Transfer", "UPI", "Cash", "Credit Card", etc.
    reference = db.Column(db.String(150), nullable=True)  # External ref, UPI ref, Invoice #, etc.
    
    source = db.Column(db.String(30), default='MANUAL', nullable=False)  # 'MANUAL' or 'AUTOMATIC'
    provider = db.Column(db.String(50), default='MANUAL', nullable=False)  # 'CASHFREE', 'MANUAL', 'TEST'
    provider_transaction_id = db.Column(db.String(150), nullable=True)  # e.g. cf_payment_id
    cashfree_order_id = db.Column(db.String(100), nullable=True, index=True)
    
    # Optional relational links
    application_id = db.Column(db.Integer, db.ForeignKey('job_applications.id', ondelete='SET NULL'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job_postings.id', ondelete='SET NULL'), nullable=True, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # Environment tagging
    environment = db.Column(db.String(30), default='PRODUCTION', nullable=False)  # 'PRODUCTION', 'SANDBOX', 'TEST', 'MANUAL'
    
    # Audit info
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    application = db.relationship('JobApplication', backref=db.backref('money_transactions', lazy=True), foreign_keys=[application_id])
    user = db.relationship('User', foreign_keys=[user_id], lazy=True)
    admin_creator = db.relationship('User', foreign_keys=[created_by_admin_id], lazy=True)
    job = db.relationship('JobPosting', foreign_keys=[job_id], lazy=True)
    partner = db.relationship('Partner', backref=db.backref('transactions', lazy=True), foreign_keys=[partner_id])

    @property
    def is_income(self):
        return (self.transaction_type or '').upper() == 'INCOME'

    @property
    def is_expense(self):
        return (self.transaction_type or '').upper() == 'EXPENSE'

    @property
    def is_cashfree(self):
        return (self.provider or '').upper() == 'CASHFREE'

    @property
    def is_manual(self):
        return (self.source or '').upper() == 'MANUAL'

    @property
    def formatted_amount(self):
        return f"₹{self.amount:,.2f}"

    @property
    def formatted_date_display(self):
        if not self.transaction_date:
            return ""
        try:
            return self.transaction_date.strftime('%d %b %Y')
        except Exception:
            return str(self.transaction_date)

    @property
    def formatted_datetime_display(self):
        date_str = self.formatted_date_display
        if self.transaction_time:
            return f"{date_str}, {self.transaction_time}"
        return date_str

    @property
    def environment_display(self):
        env = (self.environment or 'PRODUCTION').upper()
        if self.is_cashfree:
            if env == 'SANDBOX':
                return 'Cashfree • Sandbox'
            elif env == 'TEST':
                return 'Cashfree • Test Simulation'
            else:
                return 'Cashfree • Production'
        return 'Manual'

    @property
    def environment_badge_class(self):
        env = (self.environment or 'PRODUCTION').upper()
        if self.is_cashfree:
            if env in ['SANDBOX', 'TEST']:
                return 'badge-sandbox'
            return 'badge-production'
        return 'badge-manual'

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_type': self.transaction_type,
            'amount': self.amount,
            'formatted_amount': self.formatted_amount,
            'transaction_date': self.transaction_date.isoformat() if self.transaction_date else None,
            'transaction_time': self.transaction_time,
            'formatted_datetime': self.formatted_datetime_display,
            'category': self.category,
            'purpose': self.purpose or self.category,
            'description': self.description or '',
            'payment_method': self.payment_method or ('Cashfree' if self.is_cashfree else 'Manual'),
            'reference': self.reference or '',
            'source': self.source,
            'provider': self.provider,
            'provider_transaction_id': self.provider_transaction_id or '',
            'cashfree_order_id': self.cashfree_order_id or '',
            'application_id': self.application_id,
            'application_code': self.application.formatted_code if self.application else None,
            'candidate_name': self.application.full_name if self.application else (self.user.name if self.user else None),
            'partner_id': self.partner_id,
            'partner_name': self.partner.name if self.partner else None,
            'environment': self.environment,
            'environment_display': self.environment_display,
            'is_manual': self.is_manual,
            'is_cashfree': self.is_cashfree,
            'created_by_admin': self.admin_creator.name if self.admin_creator else None,
            'created_at': self.created_at.strftime('%d %b %Y, %I:%M %p') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%d %b %Y, %I:%M %p') if self.updated_at else None
        }

    def __repr__(self):
        return f"<MoneyTransaction id={self.id} type='{self.transaction_type}' amount={self.amount} category='{self.category}' env='{self.environment}'>"
