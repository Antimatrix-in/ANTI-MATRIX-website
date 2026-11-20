import logging
from datetime import datetime, timezone, date, timedelta
from sqlalchemy import inspect, text
from flask import current_app
from models import db, MoneyTransaction, Payment, JobApplication, PartnerEarningsRecord
from models.partner import Partner
from models.partner_earnings_record import PartnerEarningsRecord

logger = logging.getLogger(__name__)


# ==============================================================================
# INDIAN CURRENCY FORMATTER
# ==============================================================================

def format_inr(amount, include_paise=False):
    """
    Formats a numeric amount into standard Indian Currency Notation:
    e.g. 132500 -> '₹1,32,500'
         1000000 -> '₹10,00,000'
         0 -> '₹0'
    """
    try:
        val = float(amount or 0)
    except (ValueError, TypeError):
        return "₹0"

    if val == 0:
        return "₹0.00" if include_paise else "₹0"

    sign = "-" if val < 0 else ""
    val = abs(val)
    int_part = int(val)
    paise_part = f"{val - int_part:.2f}"[1:] if include_paise else ""

    s = str(int_part)
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3

    return f"{sign}₹{formatted}{paise_part}"


def get_date_range_for_filter(date_filter, start_date=None, end_date=None):
    """
    Resolves standard date boundaries for a given date_filter.
    Supported: this_month, last_month, this_year, last_year, all, today, this_week, custom.
    Returns (start_date_obj or None, end_date_obj or None).
    """
    today = datetime.now(timezone.utc).date()
    date_filter = (date_filter or 'all').strip().lower()

    if date_filter == 'today':
        return today, today
    elif date_filter == 'this_week':
        start = today - timedelta(days=today.weekday())
        return start, today
    elif date_filter == 'this_month':
        start = date(today.year, today.month, 1)
        return start, today
    elif date_filter == 'last_month':
        first_this_month = date(today.year, today.month, 1)
        last_day_prev_month = first_this_month - timedelta(days=1)
        first_prev_month = date(last_day_prev_month.year, last_day_prev_month.month, 1)
        return first_prev_month, last_day_prev_month
    elif date_filter == 'this_year':
        start = date(today.year, 1, 1)
        return start, today
    elif date_filter == 'last_year':
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return start, end
    elif date_filter == 'custom':
        s = None
        e = None
        if start_date:
            try:
                s = datetime.strptime(start_date, '%Y-%m-%d').date() if isinstance(start_date, str) else start_date
            except Exception:
                pass
        if end_date:
            try:
                e = datetime.strptime(end_date, '%Y-%m-%d').date() if isinstance(end_date, str) else end_date
            except Exception:
                pass
        return s, e
    return None, None  # 'all'


# Standard Categories for Income and Expense
STANDARD_INCOME_CATEGORIES = [
    "Internship Application Fee",
    "Website Development",
    "Software Development",
    "Mobile App Development",
    "Digital Services",
    "Consulting",
    "Other Income"
]

STANDARD_EXPENSE_CATEGORIES = [
    "Domain",
    "Hosting",
    "Server",
    "Software",
    "API",
    "Advertising",
    "Marketing",
    "Salary",
    "Office",
    "Internet",
    "Travel",
    "Equipment",
    "Development",
    "Other Expense"
]

PAYMENT_METHODS = [
    "Cashfree",
    "Bank Transfer",
    "UPI",
    "Cash",
    "Credit Card",
    "Debit Card",
    "Cheque",
    "Other"
]

# ==============================================================================
# MONEY MANAGEMENT SECURITY & PERMISSION BOUNDARY
# ==============================================================================
# RULE:
# 1. No AI prompt, LLM agent, natural-language command, chatbot, or automated prompt
#    mechanism has write access (INSERT, UPDATE, DELETE) to Money Management transactions.
# 2. AI / Prompt systems have strictly READ-ONLY access (e.g. summary, analytics, search).
# 3. Only an authenticated Administrator explicitly submitting the web form in the
#    Admin Dashboard (Money Management -> Transaction History -> Edit) may update an existing transaction.
# 4. Cashfree automatic transactions are immutable regarding core payment facts.
# ==============================================================================


def validate_manual_admin_mutation(user, txn=None, action="edit"):
    """
    Enforces the non-negotiable security boundary for Money Management write operations.
    
    Requirements:
    - User must be authenticated and have role == 'admin'.
    - Action must be explicit manual admin action.
    - If modifying an existing transaction (edit/delete), Cashfree automatic records are locked.
    
    Returns:
        (is_allowed: bool, error_message: str or None)
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False, "Authentication required. Only authenticated administrators can modify transactions."

    role = (getattr(user, 'role', '') or '').strip().lower()
    if role != 'admin':
        return False, "Unauthorized. Only administrators have permission to modify transaction records."

    if txn:
        # Check source protection for Cashfree transactions
        if txn.source != 'MANUAL' and action in ['edit', 'delete']:
            return False, "Cashfree automatic transactions cannot be manually modified or deleted."

    return True, None


_MONEY_SCHEMA_INITIALIZED = False

def ensure_money_management_schema():
    """
    Safely inspects and updates the database schema for money management and partner earnings.
    Ensures:
    1. 'partners' table exists.
    2. 'partner_id' column on 'money_transactions' exists.
    3. Core founding partners are initialized.
    Works seamlessly across PostgreSQL and SQLite, preventing 500/404 crashes.
    """
    global _MONEY_SCHEMA_INITIALIZED
    if _MONEY_SCHEMA_INITIALIZED:
        return True

    try:
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # 1. Create partners table if not exists
        if 'partners' not in table_names:
            try:
                Partner.__table__.create(db.engine, checkfirst=True)
                logger.info("[MoneyService] 'partners' table created successfully.")
            except Exception as e:
                logger.warning(f"[MoneyService] Table creation note for partners: {e}")

        # 2. Add partner_id column to money_transactions if not exists
        if 'money_transactions' in table_names:
            mt_cols = [c['name'] for c in inspector.get_columns('money_transactions')]
            if 'partner_id' not in mt_cols:
                with db.engine.begin() as conn:
                    dialect_name = db.engine.dialect.name
                    if dialect_name == 'postgresql':
                        try:
                            conn.execute(text("ALTER TABLE money_transactions ADD COLUMN IF NOT EXISTS partner_id INTEGER REFERENCES partners(id)"))
                        except Exception:
                            conn.execute(text("ALTER TABLE money_transactions ADD COLUMN IF NOT EXISTS partner_id INTEGER"))
                    else:
                        conn.execute(text("ALTER TABLE money_transactions ADD COLUMN partner_id INTEGER REFERENCES partners(id)"))
                    try:
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_money_transactions_partner_id ON money_transactions (partner_id)"))
                    except Exception:
                        pass
                logger.info("[MoneyService] Added partner_id column to money_transactions.")

        # 3. Initialize default partners
        ensure_default_partners_initialized()

        # 4. Create partner_earnings_records table if not exists
        if 'partner_earnings_records' not in table_names:
            try:
                PartnerEarningsRecord.__table__.create(db.engine, checkfirst=True)
                logger.info("[MoneyService] 'partner_earnings_records' table created successfully.")
            except Exception as e:
                logger.warning(f"[MoneyService] Table creation note for partner_earnings_records: {e}")

        _MONEY_SCHEMA_INITIALIZED = True
        return True
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning(f"[MoneyService] Schema self-healing note: {e}")
        return False


def ensure_default_partners_initialized():
    """
    Safely seeds the verified core founding team partners into the Partner model
    if none exist. Resolves user_id by email match when available.
    """
    try:
        from models import User
        count = Partner.query.count()
        if count > 0:
            return count

        default_partners_data = [
            {
                "name": "Praveen R",
                "email": "praveen@antimatrix.co.in",
                "role_title": "Founder & CEO",
                "profile_picture": None,
                "display_order": 1,
            },
            {
                "name": "Rohit R",
                "email": "rohit@antimatrix.co.in",
                "role_title": "Co-Founder & COO",
                "profile_picture": None,
                "display_order": 2,
            },
            {
                "name": "Satish Kumar",
                "email": "satishkumar@antimatrix.co.in",
                "role_title": "Co-Founder & CTO",
                "profile_picture": None,
                "display_order": 3,
            },
            {
                "name": "Bharat Babu",
                "email": "bharatbabu@antimatrix.co.in",
                "role_title": "Co-Founder & CFO",
                "profile_picture": None,
                "display_order": 4,
            },
        ]

        for p_data in default_partners_data:
            user = User.query.filter(User.email.ilike(p_data["email"])).first()
            p = Partner(
                name=p_data["name"],
                email=p_data["email"],
                role_title=p_data["role_title"],
                profile_picture=p_data["profile_picture"],
                user_id=user.id if user else None,
                display_order=p_data["display_order"],
                is_active=True
            )
            db.session.add(p)
        db.session.commit()
        logger.info("[MoneyService] Successfully seeded default core partners.")
        return len(default_partners_data)
    except Exception as e:
        db.session.rollback()
        logger.warning(f"[MoneyService] Note on partner seed initialization: {e}")
        return 0


def get_active_partners():
    """
    Returns list of active partners ordered by display_order.
    """
    try:
        return Partner.query.filter_by(is_active=True).order_by(Partner.display_order.asc(), Partner.id.asc()).all()
    except Exception as e:
        logger.warning(f"[MoneyService] Could not retrieve partners: {e}")
        return []


def get_partner_earnings_summary(date_filter='all', start_date=None, end_date=None):
    """
    Computes partner earnings for the selected date range.
    Partners are sorted in descending order of contribution (highest to lowest).
    If a partner has zero earnings, displays ₹0 cleanly with 0% height.
    Generates nice Indian currency formatted labels and relative bar height percentages.
    """
    start_d, end_d = get_date_range_for_filter(date_filter, start_date, end_date)

    date_labels = {
        'today': 'Today',
        'this_week': 'This Week',
        'this_month': 'This Month',
        'last_month': 'Last Month',
        'this_year': 'This Year',
        'last_year': 'Last Year',
        'custom': 'Custom Range',
        'all': 'All Time'
    }
    date_filter_clean = (date_filter or 'all').strip().lower()
    date_filter_label = date_labels.get(date_filter_clean, 'All Time')
    if date_filter_clean == 'custom' and (start_d or end_d):
        s_str = start_d.strftime('%d %b %Y') if start_d else 'Start'
        e_str = end_d.strftime('%d %b %Y') if end_d else 'Now'
        date_filter_label = f"Custom ({s_str} – {e_str})"

    # Retrieve all active partners
    partners = get_active_partners()

    # 1. Query partner earnings records within the period
    records_query = PartnerEarningsRecord.query
    if start_d:
        records_query = records_query.filter(PartnerEarningsRecord.earnings_date >= start_d)
    if end_d:
        records_query = records_query.filter(PartnerEarningsRecord.earnings_date <= end_d)
    all_period_records = records_query.all()

    # Aggregate by partner_id
    partner_income_map = {}
    partner_txn_count_map = {}
    for rec in all_period_records:
        amt = float(rec.amount or 0)
        partner_income_map[rec.partner_id] = partner_income_map.get(rec.partner_id, 0.0) + amt
        partner_txn_count_map[rec.partner_id] = partner_txn_count_map.get(rec.partner_id, 0) + 1

    # 2. Query company income transactions for unassigned income and any linked transactions
    income_query = MoneyTransaction.query.filter(MoneyTransaction.transaction_type == 'INCOME')
    if start_d:
        income_query = income_query.filter(MoneyTransaction.transaction_date >= start_d)
    if end_d:
        income_query = income_query.filter(MoneyTransaction.transaction_date <= end_d)
    all_period_income = income_query.all()

    unassigned_income = 0.0
    for txn in all_period_income:
        amt = float(txn.amount or 0)
        if txn.partner_id:
            partner_income_map[txn.partner_id] = partner_income_map.get(txn.partner_id, 0.0) + amt
            partner_txn_count_map[txn.partner_id] = partner_txn_count_map.get(txn.partner_id, 0) + 1
        else:
            unassigned_income += amt

    partner_list = []
    total_partner_earnings = 0.0
    for p in partners:
        tot = partner_income_map.get(p.id, 0.0)
        cnt = partner_txn_count_map.get(p.id, 0)
        total_partner_earnings += tot
        partner_list.append({
            'id': p.id,
            'name': p.name,
            'email': p.email,
            'role_title': p.role_title,
            'initials': p.initials,
            'profile_picture': p.profile_picture,
            'display_order': p.display_order,
            'total_amount': tot,
            'formatted_amount': format_inr(tot),
            'transaction_count': cnt,
            'record_count': cnt,
            'bar_height_pct': 0.0,
            'is_top_contributor': False
        })

    # Sort descending by contribution (highest first). If equal, preserve display_order
    partner_list.sort(key=lambda x: (x['total_amount'], -x['display_order']), reverse=True)

    max_earnings = max([p['total_amount'] for p in partner_list], default=0.0)
    has_earnings = max_earnings > 0

    if has_earnings:
        partner_list[0]['is_top_contributor'] = True

        # Scale ceiling for Y-axis
        if max_earnings <= 1000:
            scale_max = 1000.0
        elif max_earnings <= 5000:
            scale_max = ((int(max_earnings) // 1000) + 1) * 1000.0
        elif max_earnings <= 25000:
            scale_max = ((int(max_earnings) // 5000) + 1) * 5000.0
        elif max_earnings <= 100000:
            scale_max = ((int(max_earnings) // 10000) + 1) * 10000.0
        elif max_earnings <= 500000:
            scale_max = ((int(max_earnings) // 50000) + 1) * 50000.0
        else:
            scale_max = ((int(max_earnings) // 100000) + 1) * 100000.0

        for p in partner_list:
            if p['total_amount'] > 0:
                pct = round((p['total_amount'] / scale_max) * 100.0, 1)
                p['bar_height_pct'] = max(12.0, min(100.0, pct))
            else:
                p['bar_height_pct'] = 0.0

        # Build 5 Y-axis ticks
        y_ticks = [
            {'label': format_inr(scale_max), 'percent': 100},
            {'label': format_inr(scale_max * 0.75), 'percent': 75},
            {'label': format_inr(scale_max * 0.50), 'percent': 50},
            {'label': format_inr(scale_max * 0.25), 'percent': 25},
            {'label': format_inr(0), 'percent': 0}
        ]
    else:
        for p in partner_list:
            p['bar_height_pct'] = 0.0
        y_ticks = [
            {'label': '₹1,00,000', 'percent': 100},
            {'label': '₹75,000', 'percent': 75},
            {'label': '₹50,000', 'percent': 50},
            {'label': '₹25,000', 'percent': 25},
            {'label': '₹0', 'percent': 0}
        ]

    return {
        'partners': partner_list,
        'max_earnings': max_earnings,
        'total_partner_earnings': total_partner_earnings,
        'formatted_total_earnings': format_inr(total_partner_earnings),
        'unassigned_income': unassigned_income,
        'formatted_unassigned_income': format_inr(unassigned_income),
        'has_earnings': has_earnings,
        'y_ticks': y_ticks,
        'date_filter': date_filter_clean,
        'date_filter_label': date_filter_label,
        'start_date': start_d.strftime('%Y-%m-%d') if start_d else '',
        'end_date': end_d.strftime('%Y-%m-%d') if end_d else '',
        'total_records_count': len(all_period_records)
    }


# ==============================================================================
# PARTNER EARNINGS RECORD MANAGEMENT CRUD
# ==============================================================================

def filter_partner_earnings_records(partner_id=None, date_filter='all', start_date=None, end_date=None, search_query=None, sort_by='newest'):
    """
    Filters PartnerEarningsRecord query by partner, date range, search terms, and sort order.
    """
    query = PartnerEarningsRecord.query.join(Partner, PartnerEarningsRecord.partner_id == Partner.id)

    if partner_id and str(partner_id).isdigit() and int(partner_id) > 0:
        query = query.filter(PartnerEarningsRecord.partner_id == int(partner_id))

    start_d, end_d = get_date_range_for_filter(date_filter, start_date, end_date)
    if start_d:
        query = query.filter(PartnerEarningsRecord.earnings_date >= start_d)
    if end_d:
        query = query.filter(PartnerEarningsRecord.earnings_date <= end_d)

    if search_query:
        q = f"%{search_query.strip()}%"
        query = query.filter(
            (Partner.name.ilike(q)) |
            (PartnerEarningsRecord.description.ilike(q)) |
            (PartnerEarningsRecord.reference.ilike(q)) |
            (PartnerEarningsRecord.notes.ilike(q))
        )

    if sort_by == 'oldest':
        query = query.order_by(PartnerEarningsRecord.earnings_date.asc(), PartnerEarningsRecord.id.asc())
    elif sort_by == 'highest':
        query = query.order_by(PartnerEarningsRecord.amount.desc(), PartnerEarningsRecord.earnings_date.desc())
    elif sort_by == 'lowest':
        query = query.order_by(PartnerEarningsRecord.amount.asc(), PartnerEarningsRecord.earnings_date.desc())
    else:  # newest default
        query = query.order_by(PartnerEarningsRecord.earnings_date.desc(), PartnerEarningsRecord.id.desc())

    return query


def create_partner_earnings_record(partner_id, amount, earnings_date=None, description=None, reference=None, notes=None, created_by=None):
    """
    Creates and persists a new PartnerEarningsRecord in the database.
    Validates partner existence, positive numeric amount, and valid date.
    Returns (success: bool, record: PartnerEarningsRecord or None, error_message: str or None).
    """
    try:
        if not partner_id:
            return False, None, "Partner is required."
        
        partner = db.session.get(Partner, int(partner_id))
        if not partner:
            return False, None, f"Partner with ID {partner_id} not found."

        try:
            val_amount = float(amount)
            if val_amount <= 0:
                return False, None, "Earnings amount must be greater than zero."
        except (ValueError, TypeError):
            return False, None, "Please enter a valid numeric earnings amount."

        if isinstance(earnings_date, str):
            clean_date = earnings_date.strip()
            if clean_date:
                try:
                    parsed_date = datetime.strptime(clean_date, '%Y-%m-%d').date()
                except ValueError:
                    return False, None, "Invalid earnings date format. Expected YYYY-MM-DD."
            else:
                parsed_date = datetime.now(timezone.utc).date()
        elif isinstance(earnings_date, date):
            parsed_date = earnings_date
        else:
            parsed_date = datetime.now(timezone.utc).date()

        record = PartnerEarningsRecord(
            partner_id=partner.id,
            amount=val_amount,
            earnings_date=parsed_date,
            description=(description or '').strip() or None,
            reference=(reference or '').strip() or None,
            notes=(notes or '').strip() or None,
            created_by=created_by
        )
        db.session.add(record)
        db.session.commit()
        logger.info(f"[MoneyService] Created PartnerEarningsRecord ID {record.id} for Partner {partner.name} amount ₹{val_amount:,.2f}")
        return True, record, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"[MoneyService] Error creating partner earnings record: {e}", exc_info=True)
        return False, None, str(e)


def update_partner_earnings_record(record_id, partner_id, amount, earnings_date=None, description=None, reference=None, notes=None):
    """
    Updates an existing PartnerEarningsRecord in place.
    Returns (success: bool, record: PartnerEarningsRecord or None, error_message: str or None).
    """
    try:
        record = db.session.get(PartnerEarningsRecord, int(record_id))
        if not record:
            return False, None, f"Earnings record with ID {record_id} not found."

        if not partner_id:
            return False, None, "Partner is required."
        
        partner = db.session.get(Partner, int(partner_id))
        if not partner:
            return False, None, f"Partner with ID {partner_id} not found."

        try:
            val_amount = float(amount)
            if val_amount <= 0:
                return False, None, "Earnings amount must be greater than zero."
        except (ValueError, TypeError):
            return False, None, "Please enter a valid numeric earnings amount."

        if isinstance(earnings_date, str):
            clean_date = earnings_date.strip()
            if clean_date:
                try:
                    parsed_date = datetime.strptime(clean_date, '%Y-%m-%d').date()
                except ValueError:
                    return False, None, "Invalid earnings date format. Expected YYYY-MM-DD."
            else:
                parsed_date = record.earnings_date
        elif isinstance(earnings_date, date):
            parsed_date = earnings_date
        else:
            parsed_date = record.earnings_date

        record.partner_id = partner.id
        record.amount = val_amount
        record.earnings_date = parsed_date
        record.description = (description or '').strip() or None
        record.reference = (reference or '').strip() or None
        record.notes = (notes or '').strip() or None
        record.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        logger.info(f"[MoneyService] Updated PartnerEarningsRecord ID {record.id} for Partner {partner.name} amount ₹{val_amount:,.2f}")
        return True, record, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"[MoneyService] Error updating partner earnings record: {e}", exc_info=True)
        return False, None, str(e)


def delete_partner_earnings_record(record_id):
    """
    Permanently deletes a PartnerEarningsRecord.
    Returns (success: bool, error_message: str or None).
    """
    try:
        record = db.session.get(PartnerEarningsRecord, int(record_id))
        if not record:
            return False, f"Earnings record with ID {record_id} not found."

        db.session.delete(record)
        db.session.commit()
        logger.info(f"[MoneyService] Deleted PartnerEarningsRecord ID {record_id}.")
        return True, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"[MoneyService] Error deleting partner earnings record: {e}", exc_info=True)
        return False, str(e)


def record_cashfree_income(application, payment, payment_details=None, env=None):
    """
    Safely and idempotently record a verified Cashfree payment as an INCOME transaction in Money Management.
    """
    if not application or not payment:
        logger.warning("[MoneyService] Missing application or payment object for cashfree income recording.")
        return False, None, "Missing application or payment object."

    order_id = payment.cashfree_order_id
    cf_payment_id = payment.cf_payment_id or (payment_details.get('cf_payment_id') if isinstance(payment_details, dict) else None)

    # 1. Idempotency Check: Verify if transaction has already been recorded
    existing_txn = None
    if order_id:
        existing_txn = MoneyTransaction.query.filter_by(cashfree_order_id=order_id).first()

    if not existing_txn and cf_payment_id:
        existing_txn = MoneyTransaction.query.filter_by(
            provider='CASHFREE',
            provider_transaction_id=str(cf_payment_id)
        ).first()

    if existing_txn:
        logger.info(f"[MoneyService] Cashfree order {order_id} already recorded in MoneyTransaction (ID: {existing_txn.id}). Skipping.")
        return True, existing_txn, "Already recorded"

    # 2. Determine Environment (SANDBOX vs PRODUCTION vs TEST)
    if not env:
        if current_app:
            if current_app.config.get('PAYMENT_TEST_MODE', False) and payment.gateway == 'TEST':
                env = 'TEST'
            else:
                raw_env = (
                    current_app.config.get('CASHFREE_ENVIRONMENT') or 
                    current_app.config.get('CASHFREE_ENV') or 
                    'sandbox'
                ).strip().lower()
                env = 'PRODUCTION' if raw_env == 'production' else 'SANDBOX'
        else:
            env = 'SANDBOX'
    else:
        env = env.strip().upper()

    now_utc = datetime.now(timezone.utc)
    txn_date = now_utc.date()
    txn_time = now_utc.strftime('%I:%M %p')

    # 3. Create MoneyTransaction
    amount = float(payment.amount or application.application_fee or 0)
    job_title = application.job.title if application.job else "Internship Application"
    app_code = application.formatted_code

    if getattr(payment, 'base_amount', None) and getattr(payment, 'gst_amount', None):
        description = f"Anti Matrix Internship Application Fee - {job_title} ({app_code}) [Base: ₹{payment.base_amount:.2f} + GST 18%: ₹{payment.gst_amount:.2f}]"
    elif getattr(application, 'base_amount', None) and getattr(application, 'gst_amount', None):
        description = f"Anti Matrix Internship Application Fee - {job_title} ({app_code}) [Base: ₹{application.base_amount:.2f} + GST 18%: ₹{application.gst_amount:.2f}]"
    else:
        description = f"Anti Matrix Internship Application Fee - {job_title} ({app_code})"
    purpose = f"Application Fee: {job_title}"
    ref = cf_payment_id or order_id

    try:
        txn = MoneyTransaction(
            transaction_type='INCOME',
            amount=amount,
            transaction_date=txn_date,
            transaction_time=txn_time,
            category='Internship Application Fee',
            purpose=purpose,
            description=description,
            payment_method='Cashfree',
            reference=ref,
            source='AUTOMATIC',
            provider='CASHFREE',
            provider_transaction_id=str(cf_payment_id) if cf_payment_id else None,
            cashfree_order_id=order_id,
            application_id=application.id,
            user_id=application.user_id,
            job_id=application.job_id,
            environment=env,
            created_at=now_utc,
            updated_at=now_utc
        )
        db.session.add(txn)
        db.session.commit()
        logger.info(f"[MoneyService] Successfully recorded Cashfree INCOME transaction (ID: {txn.id}) for Order: {order_id}, Amount: ₹{amount}")
        return True, txn, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"[MoneyService] Error recording Cashfree income transaction for Order {order_id}: {str(e)}")
        return False, None, str(e)


def get_financial_summary(env_filter='all', date_filter='all', start_date=None, end_date=None, category_filter='all', search_query=None):
    """
    Calculate financial totals and summary metrics dynamically from database transaction records.
    No hardcoded totals. All math is database-backed.
    """
    today = datetime.now(timezone.utc).date()

    # Base query for all transactions
    all_txns = MoneyTransaction.query.all()

    # Calculate overall breakdown across all recorded transactions
    prod_income = sum(t.amount for t in all_txns if t.is_income and t.environment in ['PRODUCTION', 'MANUAL'])
    prod_expense = sum(t.amount for t in all_txns if t.is_expense and t.environment in ['PRODUCTION', 'MANUAL'])
    prod_balance = prod_income - prod_expense

    sandbox_income = sum(t.amount for t in all_txns if t.is_income and t.environment in ['SANDBOX', 'TEST'])
    sandbox_expense = sum(t.amount for t in all_txns if t.is_expense and t.environment in ['SANDBOX', 'TEST'])
    sandbox_balance = sandbox_income - sandbox_expense

    manual_income = sum(t.amount for t in all_txns if t.is_income and t.is_manual)
    manual_expense = sum(t.amount for t in all_txns if t.is_expense and t.is_manual)

    cashfree_income = sum(t.amount for t in all_txns if t.is_income and t.is_cashfree)

    # Calculate Today's figures
    today_income = sum(t.amount for t in all_txns if t.is_income and t.transaction_date == today)
    today_expense = sum(t.amount for t in all_txns if t.is_expense and t.transaction_date == today)

    # Calculate This Month's figures
    month_income = sum(t.amount for t in all_txns if t.is_income and t.transaction_date and t.transaction_date.year == today.year and t.transaction_date.month == today.month)
    month_expense = sum(t.amount for t in all_txns if t.is_expense and t.transaction_date and t.transaction_date.year == today.year and t.transaction_date.month == today.month)

    # Now calculate filtered totals based on current view/filter selections
    filtered_txns = filter_transactions(
        env_filter=env_filter,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date,
        category_filter=category_filter,
        search_query=search_query
    ).all()

    filtered_income = sum(t.amount for t in filtered_txns if t.is_income)
    filtered_expense = sum(t.amount for t in filtered_txns if t.is_expense)
    filtered_balance = filtered_income - filtered_expense

    return {
        # Current Active Filter View Totals
        'total_income': filtered_income,
        'total_expense': filtered_expense,
        'balance': filtered_balance,
        'net_profit': filtered_balance,
        'transaction_count': len(filtered_txns),
        'formatted_income': format_inr(filtered_income),
        'formatted_expense': format_inr(filtered_expense),
        'formatted_balance': format_inr(filtered_balance),

        # Production vs Sandbox Breakdown
        'production_income': prod_income,
        'production_expense': prod_expense,
        'production_balance': prod_balance,
        'sandbox_income': sandbox_income,
        'sandbox_expense': sandbox_expense,
        'sandbox_balance': sandbox_balance,

        # Source Breakdown
        'manual_income': manual_income,
        'manual_expense': manual_expense,
        'cashfree_income': cashfree_income,

        # Time Periods
        'today_income': today_income,
        'today_expense': today_expense,
        'month_income': month_income,
        'month_expense': month_expense,
        'all_time_count': len(all_txns)
    }


def filter_transactions(type_filter='all', env_filter='all', date_filter='all', 
                        start_date=None, end_date=None, category_filter='all', 
                        search_query=None, sort_by='newest'):
    """
    Build a SQLAlchemy query for MoneyTransaction applying all filters and search parameters.
    """
    query = MoneyTransaction.query

    # 1. Type Filter (INCOME / EXPENSE)
    if type_filter and type_filter.lower() in ['income', 'expense']:
        query = query.filter(MoneyTransaction.transaction_type == type_filter.upper())

    # 2. Environment Filter (PRODUCTION / SANDBOX / MANUAL)
    if env_filter and env_filter.lower() != 'all':
        env_val = env_filter.lower()
        if env_val == 'production':
            query = query.filter(MoneyTransaction.environment.in_(['PRODUCTION', 'MANUAL']))
        elif env_val == 'sandbox':
            query = query.filter(MoneyTransaction.environment.in_(['SANDBOX', 'TEST']))
        elif env_val == 'manual':
            query = query.filter(MoneyTransaction.source == 'MANUAL')

    # 3. Category Filter
    if category_filter and category_filter.lower() != 'all':
        query = query.filter(MoneyTransaction.category == category_filter)

    # 4. Date Filter
    start_d, end_d = get_date_range_for_filter(date_filter, start_date, end_date)
    if start_d:
        query = query.filter(MoneyTransaction.transaction_date >= start_d)
    if end_d:
        query = query.filter(MoneyTransaction.transaction_date <= end_d)

    # 5. Search Query
    if search_query:
        q = f"%{search_query.strip()}%"
        query = query.outerjoin(JobApplication, MoneyTransaction.application_id == JobApplication.id).filter(
            (MoneyTransaction.category.ilike(q)) |
            (MoneyTransaction.purpose.ilike(q)) |
            (MoneyTransaction.description.ilike(q)) |
            (MoneyTransaction.reference.ilike(q)) |
            (MoneyTransaction.cashfree_order_id.ilike(q)) |
            (MoneyTransaction.provider_transaction_id.ilike(q)) |
            (MoneyTransaction.payment_method.ilike(q)) |
            (JobApplication.application_code.ilike(q)) |
            (JobApplication.full_name.ilike(q))
        )

    # 6. Sorting
    if sort_by == 'oldest':
        query = query.order_by(MoneyTransaction.transaction_date.asc(), MoneyTransaction.id.asc())
    elif sort_by == 'highest':
        query = query.order_by(MoneyTransaction.amount.desc(), MoneyTransaction.transaction_date.desc())
    elif sort_by == 'lowest':
        query = query.order_by(MoneyTransaction.amount.asc(), MoneyTransaction.transaction_date.desc())
    else:  # newest default
        query = query.order_by(MoneyTransaction.transaction_date.desc(), MoneyTransaction.id.desc())

    return query


def reconcile_cashfree_payments():
    """
    Scan all paid Payment records and ensure a corresponding MoneyTransaction exists.
    Returns (count_added, total_checked).
    """
    paid_payments = Payment.query.filter_by(payment_status='paid').all()
    count_added = 0

    for payment in paid_payments:
        if not payment.application:
            continue
        order_id = payment.cashfree_order_id
        existing = MoneyTransaction.query.filter_by(cashfree_order_id=order_id).first()
        if not existing and payment.cf_payment_id:
            existing = MoneyTransaction.query.filter_by(
                provider='CASHFREE',
                provider_transaction_id=str(payment.cf_payment_id)
            ).first()

        if not existing:
            success, txn, err = record_cashfree_income(
                application=payment.application,
                payment=payment
            )
            if success:
                count_added += 1

    return count_added, len(paid_payments)


def clear_all_transactions(admin_user=None):
    """
    Safely and permanently deletes ONLY records from the MoneyTransaction ledger table.
    Preserves all Users, JobPostings, JobApplications, Payments, Employees, and DocumentTemplates.
    Operates inside an atomic database transaction.
    Returns (success, deleted_count, error_message).
    """
    try:
        count = MoneyTransaction.query.count()
        if count > 0:
            MoneyTransaction.query.delete()
            db.session.commit()
            if admin_user:
                logger.warning(
                    f"[MoneyService] Admin ID {getattr(admin_user, 'id', 'unknown')} ({getattr(admin_user, 'email', 'unknown')}) permanently cleared all {count} MoneyTransaction ledger records."
                )
            else:
                logger.warning(f"[MoneyService] Permanently cleared all {count} MoneyTransaction ledger records.")
        return True, count, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"[MoneyService] Error clearing MoneyTransaction ledger: {str(e)}", exc_info=True)
        return False, 0, str(e)
