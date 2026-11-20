import pytest
from datetime import datetime, timezone, date, timedelta
from app import create_app
from models import db, User, MoneyTransaction, Partner, JobPosting, JobApplication
from services.money_service import (
    format_inr,
    get_date_range_for_filter,
    ensure_default_partners_initialized,
    get_active_partners,
    get_partner_earnings_summary,
    get_financial_summary,
    filter_transactions,
    validate_manual_admin_mutation
)


@pytest.fixture
def app_client():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        # Clean test state for partners and transactions
        ensure_default_partners_initialized()

        # Admin user
        admin = User.query.filter_by(email='admin_money_test@antimatrix.ai').first()
        if not admin:
            admin = User(
                email='admin_money_test@antimatrix.ai',
                name='Money Admin',
                role='admin',
                is_active=True
            )
            admin.set_password('AdminMoneyPass123!')
            db.session.add(admin)
            db.session.commit()

        # Regular user (non-admin)
        regular = User.query.filter_by(email='regular_money_test@antimatrix.ai').first()
        if not regular:
            regular = User(
                email='regular_money_test@antimatrix.ai',
                name='Regular User',
                role='candidate',
                is_active=True
            )
            regular.set_password('RegularPass123!')
            db.session.add(regular)
            db.session.commit()

        client = app.test_client()
        yield client, app, admin, regular


# ==============================================================================
# TEST 1: INDIAN CURRENCY FORMATTER
# ==============================================================================

def test_format_inr():
    assert format_inr(0) == "₹0"
    assert format_inr(None) == "₹0"
    assert format_inr("invalid") == "₹0"
    assert format_inr(500) == "₹500"
    assert format_inr(1500) == "₹1,500"
    assert format_inr(132500) == "₹1,32,500"
    assert format_inr(1000000) == "₹10,00,000"
    assert format_inr(12345678) == "₹1,23,45,678"
    assert format_inr(132500.50, include_paise=True) == "₹1,32,500.50"
    assert format_inr(-50000) == "-₹50,000"


# ==============================================================================
# TEST 2: DATE RANGE RESOLVER
# ==============================================================================

def test_get_date_range_for_filter():
    today = datetime.now(timezone.utc).date()

    # Today
    s, e = get_date_range_for_filter('today')
    assert s == today and e == today

    # This Month
    s, e = get_date_range_for_filter('this_month')
    assert s == date(today.year, today.month, 1)
    assert e == today

    # Last Month
    s, e = get_date_range_for_filter('last_month')
    assert s is not None and e is not None
    assert s < e

    # This Year
    s, e = get_date_range_for_filter('this_year')
    assert s == date(today.year, 1, 1)
    assert e == today

    # Last Year
    s, e = get_date_range_for_filter('last_year')
    assert s == date(today.year - 1, 1, 1)
    assert e == date(today.year - 1, 12, 31)

    # All Time
    s, e = get_date_range_for_filter('all')
    assert s is None and e is None

    # Custom Range
    s, e = get_date_range_for_filter('custom', '2026-01-01', '2026-03-31')
    assert s == date(2026, 1, 1)
    assert e == date(2026, 3, 31)


# ==============================================================================
# TEST 3: DEFAULT PARTNERS INITIALIZATION & INITIALS
# ==============================================================================

def test_ensure_default_partners_initialized(app_client):
    _, app, _, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        assert len(partners) >= 4
        names = [p.name for p in partners]
        assert "Praveen R" in names
        assert "Rohit R" in names
        assert "Satish Kumar" in names
        assert "Bharat Babu" in names

        # Check initials property
        praveen = next(p for p in partners if p.name == "Praveen R")
        assert praveen.initials == "PR"
        satish = next(p for p in partners if p.name == "Satish Kumar")
        assert satish.initials == "SK"


# ==============================================================================
# TEST 4: PARTNER EARNINGS RANKING & ZERO-EARNINGS STABILITY
# ==============================================================================

def test_partner_earnings_summary_zero_state(app_client):
    """When no transactions exist for partners, displays ₹0 cleanly with 0% bar height."""
    _, app, _, _ = app_client
    with app.app_context():
        # Clear any existing transactions for testing
        MoneyTransaction.query.delete()
        db.session.commit()

        summary = get_partner_earnings_summary(date_filter='all')
        assert summary['has_earnings'] is False
        assert summary['max_earnings'] == 0.0
        assert len(summary['partners']) >= 4

        for p in summary['partners']:
            assert p['total_amount'] == 0.0
            assert p['formatted_amount'] == "₹0"
            assert p['bar_height_pct'] == 0.0

        # Verify Y-axis scale ticks exist and contain formatted currency
        assert len(summary['y_ticks']) >= 4
        assert any(t['percent'] == 0 for t in summary['y_ticks'])


def test_partner_earnings_summary_descending_ranking(app_client):
    """Partners are strictly sorted descending by total earnings with relative bar heights."""
    _, app, admin, _ = app_client
    with app.app_context():
        MoneyTransaction.query.delete()
        db.session.commit()

        partners = get_active_partners()
        p1 = partners[0]  # e.g. Praveen R
        p2 = partners[1]  # e.g. Rohit R
        p3 = partners[2]  # e.g. Satish Kumar
        p4 = partners[3]  # e.g. Bharat Babu

        today = datetime.now(timezone.utc).date()

        # p1: ₹1,50,000 (Highest)
        t1 = MoneyTransaction(
            transaction_type='INCOME',
            amount=150000.0,
            transaction_date=today,
            category='Software Development',
            purpose='Client Project A',
            partner_id=p1.id,
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        # p2: ₹90,000 (Second)
        t2 = MoneyTransaction(
            transaction_type='INCOME',
            amount=90000.0,
            transaction_date=today,
            category='Website Development',
            purpose='Client Project B',
            partner_id=p2.id,
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        # p3: ₹30,000 (Third)
        t3 = MoneyTransaction(
            transaction_type='INCOME',
            amount=30000.0,
            transaction_date=today,
            category='Consulting',
            purpose='Consulting Session',
            partner_id=p3.id,
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        # p4: ₹0 (Lowest)
        db.session.add_all([t1, t2, t3])
        db.session.commit()

        summary = get_partner_earnings_summary(date_filter='this_month')
        assert summary['has_earnings'] is True
        assert summary['max_earnings'] == 150000.0

        ranked = summary['partners']
        assert ranked[0]['id'] == p1.id
        assert ranked[0]['total_amount'] == 150000.0
        assert ranked[0]['formatted_amount'] == "₹1,50,000"
        assert ranked[0]['is_top_contributor'] is True
        assert ranked[0]['bar_height_pct'] > 50.0

        assert ranked[1]['id'] == p2.id
        assert ranked[1]['total_amount'] == 90000.0
        assert ranked[1]['formatted_amount'] == "₹90,000"
        assert ranked[1]['is_top_contributor'] is False

        assert ranked[2]['id'] == p3.id
        assert ranked[2]['total_amount'] == 30000.0
        assert ranked[2]['formatted_amount'] == "₹30,000"

        assert ranked[3]['id'] == p4.id
        assert ranked[3]['total_amount'] == 0.0
        assert ranked[3]['formatted_amount'] == "₹0"
        assert ranked[3]['bar_height_pct'] == 0.0


# ==============================================================================
# TEST 5: DATE FILTERING BEHAVIOR
# ==============================================================================

def test_partner_earnings_summary_date_filtering(app_client):
    """Transactions outside the selected date range are excluded from partner earnings."""
    _, app, admin, _ = app_client
    with app.app_context():
        MoneyTransaction.query.delete()
        db.session.commit()

        partners = get_active_partners()
        p1 = partners[0]

        today = datetime.now(timezone.utc).date()
        last_year_date = date(today.year - 1, 6, 15)

        # Current transaction
        t_current = MoneyTransaction(
            transaction_type='INCOME',
            amount=50000.0,
            transaction_date=today,
            category='Software Development',
            partner_id=p1.id,
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        # Historical transaction from last year
        t_old = MoneyTransaction(
            transaction_type='INCOME',
            amount=80000.0,
            transaction_date=last_year_date,
            category='Consulting',
            partner_id=p1.id,
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        db.session.add_all([t_current, t_old])
        db.session.commit()

        # This Month filter -> should only have 50000
        summary_month = get_partner_earnings_summary(date_filter='this_month')
        p1_month = next(p for p in summary_month['partners'] if p['id'] == p1.id)
        assert p1_month['total_amount'] == 50000.0

        # Last Year filter -> should only have 80000
        summary_last_year = get_partner_earnings_summary(date_filter='last_year')
        p1_last_year = next(p for p in summary_last_year['partners'] if p['id'] == p1.id)
        assert p1_last_year['total_amount'] == 80000.0

        # All Time filter -> should sum to 130000
        summary_all = get_partner_earnings_summary(date_filter='all')
        p1_all = next(p for p in summary_all['partners'] if p['id'] == p1.id)
        assert p1_all['total_amount'] == 130000.0


# ==============================================================================
# TEST 6: FINANCIAL SUMMARY 4 KPI TOTALS
# ==============================================================================

def test_financial_summary_kpi_cards(app_client):
    """KPI cards match ledger math: Total Income, Total Expense, Net Balance, Count."""
    _, app, admin, _ = app_client
    with app.app_context():
        MoneyTransaction.query.delete()
        db.session.commit()

        today = datetime.now(timezone.utc).date()

        # Income 1: 1,00,000
        t1 = MoneyTransaction(
            transaction_type='INCOME',
            amount=100000.0,
            transaction_date=today,
            category='Software Development',
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        # Expense 1: 40,000
        t2 = MoneyTransaction(
            transaction_type='EXPENSE',
            amount=40000.0,
            transaction_date=today,
            category='Hosting',
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        # Expense 2: 15,000
        t3 = MoneyTransaction(
            transaction_type='EXPENSE',
            amount=15000.0,
            transaction_date=today,
            category='Software',
            source='MANUAL',
            created_by_admin_id=admin.id
        )
        db.session.add_all([t1, t2, t3])
        db.session.commit()

        summary = get_financial_summary()
        assert summary['total_income'] == 100000.0
        assert summary['total_expense'] == 55000.0
        assert summary['balance'] == 45000.0
        assert summary['transaction_count'] == 3
        assert summary['formatted_income'] == "₹1,00,000"
        assert summary['formatted_expense'] == "₹55,000"
        assert summary['formatted_balance'] == "₹45,000"


# ==============================================================================
# TEST 7: TRANSACTION CREATION & EDIT WITH PARTNER ATTRIBUTION
# ==============================================================================

def test_transaction_partner_attribution(app_client):
    client, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        target_partner = partners[0]

        # Login as admin
        client.post('/login', data={'email': admin.email, 'password': 'AdminMoneyPass123!'}, follow_redirects=True)

        # Record new income transaction attributed to target_partner
        resp = client.post('/admin/money-management/add', data={
            'transaction_type': 'INCOME',
            'amount': '75000',
            'transaction_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'category': 'Website Development',
            'purpose': 'E-commerce platform',
            'payment_method': 'Bank Transfer',
            'partner_id': str(target_partner.id)
        }, follow_redirects=True)
        assert resp.status_code == 200

        # Verify record in DB
        txn = MoneyTransaction.query.filter_by(purpose='E-commerce platform').first()
        assert txn is not None
        assert txn.partner_id == target_partner.id
        assert txn.partner.name == target_partner.name

        # Verify to_dict serialization
        d = txn.to_dict()
        assert d['partner_id'] == target_partner.id
        assert d['partner_name'] == target_partner.name

        # Edit transaction: reassign partner to partner[1]
        new_partner = partners[1]
        edit_resp = client.post(f'/admin/money-management/transactions/{txn.id}/edit', data={
            'transaction_type': 'INCOME',
            'amount': '80000',
            'transaction_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'category': 'Website Development',
            'purpose': 'E-commerce platform updated',
            'payment_method': 'Bank Transfer',
            'partner_id': str(new_partner.id)
        }, follow_redirects=True)
        assert edit_resp.status_code == 200

        db.session.refresh(txn)
        assert txn.amount == 80000.0
        assert txn.partner_id == new_partner.id
        assert txn.partner.name == new_partner.name


# ==============================================================================
# TEST 8: AUTHENTICATION & ACCESS PROTECTION
# ==============================================================================

def test_money_management_auth_protection(app_client):
    client, _, _, regular = app_client

    # 1. Unauthenticated user redirected to login
    resp = client.get('/admin/money-management')
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

    # 2. Non-admin user redirected / forbidden
    client.post('/login', data={'email': regular.email, 'password': 'RegularPass123!'}, follow_redirects=True)
    resp = client.get('/admin/money-management')
    assert resp.status_code in [302, 403]


# ==============================================================================
# TEST 9: PAGE RENDERING & DASHBOARD COMPONENTS
# ==============================================================================

def test_money_management_page_renders_components(app_client):
    client, _, admin, _ = app_client

    client.post('/login', data={'email': admin.email, 'password': 'AdminMoneyPass123!'}, follow_redirects=True)
    resp = client.get('/admin/money-management')
    assert resp.status_code == 200

    html = resp.get_data(as_text=True)

    # 1. Main chart title & subtitle
    assert "Partner Earnings Overview" in html
    assert "Total contribution by partners (highest to lowest)" in html

    # 2. Date filter pills
    assert "This Month" in html
    assert "Last Month" in html
    assert "This Year" in html
    assert "Last Year" in html
    assert "All Time" in html
    assert "Custom Range" in html

    # 3. 4 KPI summary cards
    assert "TOTAL INCOME" in html
    assert "TOTAL EXPENSE" in html
    assert "NET BALANCE" in html
    assert "TRANSACTIONS" in html

    # 4. Standard 5 admin navigation tabs
    assert "Overview" in html
    assert "Job Postings" in html
    assert "Candidate Applications" in html
    assert "Templates" in html
    assert "Money Management" in html

    # 5. Transaction history section & actions
    assert "Transaction History" in html
    assert "Add Transaction" in html


# ==============================================================================
# TEST 10: CASHFREE MUTATION BOUNDARY & DELETION SAFEGUARDS
# ==============================================================================

def test_cashfree_automatic_records_are_protected(app_client):
    """Cashfree automatic records cannot be edited or deleted."""
    _, app, admin, _ = app_client
    with app.app_context():
        # Create simulated Cashfree transaction
        cf_txn = MoneyTransaction(
            transaction_type='INCOME',
            amount=500.0,
            transaction_date=datetime.now(timezone.utc).date(),
            category='Internship Application Fee',
            source='AUTOMATIC',
            provider='CASHFREE',
            cashfree_order_id='order_cf_test_999'
        )
        db.session.add(cf_txn)
        db.session.commit()

        # Mutation check should reject
        allowed, err = validate_manual_admin_mutation(admin, txn=cf_txn, action='edit')
        assert allowed is False
        assert "Cashfree automatic transactions cannot be manually modified or deleted." in err

        allowed_del, err_del = validate_manual_admin_mutation(admin, txn=cf_txn, action='delete')
        assert allowed_del is False
