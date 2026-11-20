import pytest
from datetime import datetime, timezone, date, timedelta
from app import create_app
from models import db, User, MoneyTransaction, Partner, PartnerEarningsRecord
from services.money_service import (
    format_inr,
    get_date_range_for_filter,
    ensure_default_partners_initialized,
    ensure_money_management_schema,
    get_active_partners,
    get_partner_earnings_summary,
    get_financial_summary,
    create_partner_earnings_record,
    update_partner_earnings_record,
    delete_partner_earnings_record,
    filter_partner_earnings_records
)


@pytest.fixture
def app_client():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        ensure_money_management_schema()
        ensure_default_partners_initialized()

        # Admin user
        admin = User.query.filter_by(email='admin_partner_test@antimatrix.ai').first()
        if not admin:
            admin = User(
                email='admin_partner_test@antimatrix.ai',
                name='Partner Admin',
                role='admin',
                is_active=True
            )
            admin.set_password('AdminPass123!')
            db.session.add(admin)
            db.session.commit()

        # Regular user (candidate/non-admin)
        regular = User.query.filter_by(email='regular_partner_test@antimatrix.ai').first()
        if not regular:
            regular = User(
                email='regular_partner_test@antimatrix.ai',
                name='Regular User',
                role='candidate',
                is_active=True
            )
            regular.set_password('RegularPass123!')
            db.session.add(regular)
            db.session.commit()

        # Clean any preexisting partner earnings records in test DB
        PartnerEarningsRecord.query.delete()
        db.session.commit()

        client = app.test_client()
        yield client, app, admin, regular

        # Cleanup
        PartnerEarningsRecord.query.delete()
        db.session.commit()


# ==============================================================================
# TEST 1: CREATE PARTNER EARNINGS RECORD (SERVICE LEVEL)
# ==============================================================================

def test_create_partner_earnings_record_service(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        target = partners[0]

        ok, record, err = create_partner_earnings_record(
            partner_id=target.id,
            amount=50000.0,
            earnings_date='2026-03-15',
            description='Client consultation',
            reference='INV-001',
            notes='Initial milestone',
            created_by=admin.id
        )

        assert ok is True
        assert err is None
        assert record is not None
        assert record.id is not None
        assert record.amount == 50000.0
        assert record.partner_id == target.id
        assert record.partner.name == target.name
        assert record.earnings_date == date(2026, 3, 15)
        assert record.created_by == admin.id

        # Serialization to dict
        d = record.to_dict()
        assert d['id'] == record.id
        assert d['amount'] == 50000.0
        assert d['formatted_amount'] in ['₹50,000', '₹50,000.00']
        assert d['partner_name'] == target.name
        assert d['earnings_date'] == '2026-03-15'


# ==============================================================================
# TEST 2: CUMULATIVE SUMMATION FOR THE SAME PARTNER
# ==============================================================================

def test_partner_earnings_cumulative_sum(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        target = partners[0]

        # Record 1: ₹30,000
        create_partner_earnings_record(
            partner_id=target.id,
            amount=30000.0,
            earnings_date=date.today(),
            created_by=admin.id
        )

        # Record 2: ₹45,000
        create_partner_earnings_record(
            partner_id=target.id,
            amount=45000.0,
            earnings_date=date.today(),
            created_by=admin.id
        )

        # Record 3: ₹25,000
        create_partner_earnings_record(
            partner_id=target.id,
            amount=25000.0,
            earnings_date=date.today(),
            created_by=admin.id
        )

        summary = get_partner_earnings_summary(date_filter='all')
        partner_stats = {p['id']: p for p in summary['partners']}

        assert partner_stats[target.id]['total_amount'] == 100000.0
        assert partner_stats[target.id]['formatted_amount'] == '₹1,00,000'
        assert partner_stats[target.id]['record_count'] == 3


# ==============================================================================
# TEST 3: DESCENDING ORDER RANKING AND DYNAMIC RERANKING
# ==============================================================================

def test_partner_earnings_descending_ranking(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        p1, p2, p3 = partners[0], partners[1], partners[2]

        # p1: ₹10,000, p2: ₹50,000, p3: ₹30,000
        create_partner_earnings_record(p1.id, 10000.0, date.today(), created_by=admin.id)
        create_partner_earnings_record(p2.id, 50000.0, date.today(), created_by=admin.id)
        create_partner_earnings_record(p3.id, 30000.0, date.today(), created_by=admin.id)

        summary = get_partner_earnings_summary(date_filter='all')
        ordered_ids = [p['id'] for p in summary['partners']]

        # p2 (₹50k) > p3 (₹30k) > p1 (₹10k)
        assert ordered_ids[0] == p2.id
        assert ordered_ids[1] == p3.id
        assert ordered_ids[2] == p1.id
        assert summary['partners'][0]['is_top_contributor'] is True
        assert summary['partners'][1]['is_top_contributor'] is False

        # Add ₹60,000 to p1 -> p1 now has ₹70,000 and should take first place
        create_partner_earnings_record(p1.id, 60000.0, date.today(), created_by=admin.id)

        summary2 = get_partner_earnings_summary(date_filter='all')
        ordered_ids2 = [p['id'] for p in summary2['partners']]

        assert ordered_ids2[0] == p1.id
        assert summary2['partners'][0]['total_amount'] == 70000.0
        assert summary2['partners'][0]['is_top_contributor'] is True


# ==============================================================================
# TEST 4: PROPORTIONAL BAR HEIGHT SCALING AND ZERO EARNINGS HANDLING
# ==============================================================================

def test_partner_earnings_bar_proportions(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        p_max, p_half, p_zero = partners[0], partners[1], partners[2]

        create_partner_earnings_record(p_max.id, 100000.0, date.today(), created_by=admin.id)
        create_partner_earnings_record(p_half.id, 50000.0, date.today(), created_by=admin.id)

        summary = get_partner_earnings_summary(date_filter='all')
        stats = {p['id']: p for p in summary['partners']}

        # Max earner: >= 80% (scale with headroom)
        assert stats[p_max.id]['bar_height_pct'] >= 80.0
        # Half earner: proportional to max earner
        assert stats[p_half.id]['bar_height_pct'] < stats[p_max.id]['bar_height_pct']
        assert stats[p_half.id]['bar_height_pct'] >= 30.0
        # Zero earner: 0.0%
        assert stats[p_zero.id]['bar_height_pct'] == 0.0

        # Y-ticks must cover up to at least the max (₹100,000)
        ticks = summary['y_ticks']
        assert len(ticks) >= 3
        assert ticks[0]['percent'] == 100
        assert ticks[-1]['percent'] == 0


# ==============================================================================
# TEST 5: DATE FILTERING ACCURACY
# ==============================================================================

def test_date_filters_partner_earnings(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        target = partners[0]
        today = date.today()

        # Record today
        create_partner_earnings_record(target.id, 20000.0, today, created_by=admin.id)

        # Record 45 days ago (different month/period)
        past_date = today - timedelta(days=45)
        create_partner_earnings_record(target.id, 35000.0, past_date, created_by=admin.id)

        # Summary for today
        s_today = get_partner_earnings_summary(date_filter='today')
        t_stats = next(p for p in s_today['partners'] if p['id'] == target.id)
        assert t_stats['total_amount'] == 20000.0

        # Summary for all time
        s_all = get_partner_earnings_summary(date_filter='all')
        t_stats_all = next(p for p in s_all['partners'] if p['id'] == target.id)
        assert t_stats_all['total_amount'] == 55000.0

        # Custom date range covering only past date
        s_custom = get_partner_earnings_summary(
            date_filter='custom',
            start_date=past_date - timedelta(days=1),
            end_date=past_date + timedelta(days=1)
        )
        t_stats_custom = next(p for p in s_custom['partners'] if p['id'] == target.id)
        assert t_stats_custom['total_amount'] == 35000.0


# ==============================================================================
# TEST 6: EDIT AND DELETE RECALCULATIONS
# ==============================================================================

def test_edit_and_delete_partner_earnings(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        p1, p2 = partners[0], partners[1]

        # Create record: ₹40,000 for p1
        _, rec, _ = create_partner_earnings_record(p1.id, 40000.0, date.today(), created_by=admin.id)

        s1 = get_partner_earnings_summary(date_filter='all')
        assert next(p for p in s1['partners'] if p['id'] == p1.id)['total_amount'] == 40000.0

        # Edit record: reassign to p2 and increase to ₹60,000
        ok, updated, err = update_partner_earnings_record(
            rec.id,
            partner_id=p2.id,
            amount=60000.0,
            earnings_date=date.today(),
            description='Updated milestone'
        )
        assert ok is True
        assert err is None
        assert updated.partner_id == p2.id
        assert updated.amount == 60000.0

        s2 = get_partner_earnings_summary(date_filter='all')
        assert next(p for p in s2['partners'] if p['id'] == p1.id)['total_amount'] == 0.0
        assert next(p for p in s2['partners'] if p['id'] == p2.id)['total_amount'] == 60000.0

        # Delete record: p2 total reverts to 0
        success, err2 = delete_partner_earnings_record(rec.id)
        assert success is True
        assert err2 is None

        s3 = get_partner_earnings_summary(date_filter='all')
        assert next(p for p in s3['partners'] if p['id'] == p2.id)['total_amount'] == 0.0


# ==============================================================================
# TEST 7: INVALID INPUT REJECTION
# ==============================================================================

def test_invalid_input_validation(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        partners = get_active_partners()
        valid_partner = partners[0]

        # Zero or negative amount
        ok1, _, err1 = create_partner_earnings_record(valid_partner.id, 0.0, date.today(), created_by=admin.id)
        assert ok1 is False
        assert "greater than zero" in err1.lower()

        ok2, _, err2 = create_partner_earnings_record(valid_partner.id, -100.0, date.today(), created_by=admin.id)
        assert ok2 is False
        assert "greater than zero" in err2.lower()

        # Non-existent partner id
        ok3, _, err3 = create_partner_earnings_record(99999, 5000.0, date.today(), created_by=admin.id)
        assert ok3 is False
        assert "not found" in err3.lower()

        # Invalid date format
        ok4, _, err4 = create_partner_earnings_record(valid_partner.id, 5000.0, "not-a-date", created_by=admin.id)
        assert ok4 is False
        assert "invalid earnings date" in err4.lower()


# ==============================================================================
# TEST 8: COMPANY FINANCIAL LEDGER ISOLATION & UNASSIGNED INCOME SEPARATION
# ==============================================================================

def test_company_financial_integrity_isolated(app_client):
    _, app, admin, _ = app_client
    with app.app_context():
        # Clean existing transactions
        MoneyTransaction.query.delete()
        db.session.commit()

        # Add unassigned company revenue (e.g. ₹6,000 Cashfree income)
        company_income = MoneyTransaction(
            transaction_type='INCOME',
            amount=6000.0,
            transaction_date=datetime.now(timezone.utc).date(),
            category='Application Fee',
            purpose='Cashfree Candidate Application Fee',
            provider='CASHFREE',
            cashfree_order_id='ORDER_TEST_6000',
            partner_id=None
        )
        db.session.add(company_income)
        db.session.commit()

        # Check financial summary before adding any partner earnings
        fin_before = get_financial_summary()
        assert fin_before['total_income'] == 6000.0
        assert fin_before['net_profit'] == 6000.0

        # Add partner earnings record for ₹80,000
        partners = get_active_partners()
        p = partners[0]
        create_partner_earnings_record(p.id, 80000.0, date.today(), created_by=admin.id)

        # Financial summary of company ledger must REMAIN ₹6,000 (not ₹86,000 or modified)
        fin_after = get_financial_summary()
        assert fin_after['total_income'] == 6000.0
        assert fin_after['net_profit'] == 6000.0

        # Unassigned income metric in partner earnings summary is strictly ₹6,000
        partner_sum = get_partner_earnings_summary(date_filter='all')
        assert partner_sum['unassigned_income'] == 6000.0
        assert partner_sum['total_partner_earnings'] == 80000.0


# ==============================================================================
# TEST 9: HTTP ENDPOINTS: CREATE, EDIT, DELETE, GET & CSRF/SESSION FLOWS
# ==============================================================================

def test_http_admin_endpoints_partner_earnings(app_client):
    client, app, admin, _ = app_client

    with app.app_context():
        partners = get_active_partners()
        target = partners[0]

        # Login as admin
        login_res = client.post('/login', data={'email': admin.email, 'password': 'AdminPass123!'}, follow_redirects=True)
        assert login_res.status_code == 200

        # 1. CREATE via POST /admin/partner-earnings/create
        res_create = client.post('/admin/partner-earnings/create', data={
            'partner_id': str(target.id),
            'amount': '42000.50',
            'earnings_date': date.today().strftime('%Y-%m-%d'),
            'description': 'Mobile App Deliverable',
            'reference': 'REF-APP-42',
            'notes': 'Verified QA complete'
        }, follow_redirects=True)
        assert res_create.status_code == 200

        record = PartnerEarningsRecord.query.filter_by(reference='REF-APP-42').first()
        assert record is not None
        assert record.amount == 42000.50
        assert record.partner_id == target.id

        # 2. GET details via JSON /admin/partner-earnings/<id>
        res_get = client.get(f'/admin/partner-earnings/{record.id}')
        assert res_get.status_code == 200
        json_data = res_get.get_json()
        assert json_data['amount'] == 42000.50
        assert json_data['reference'] == 'REF-APP-42'
        assert json_data['partner_name'] == target.name

        # 3. EDIT via POST /admin/partner-earnings/<id>/edit
        res_edit = client.post(f'/admin/partner-earnings/{record.id}/edit', data={
            'partner_id': str(target.id),
            'amount': '55000.00',
            'earnings_date': date.today().strftime('%Y-%m-%d'),
            'description': 'Mobile App Deliverable (Revised Scope)',
            'reference': 'REF-APP-42-REV',
            'notes': 'Updated after client signoff'
        }, follow_redirects=True)
        assert res_edit.status_code == 200

        db.session.refresh(record)
        assert record.amount == 55000.00
        assert record.reference == 'REF-APP-42-REV'

        # 4. DELETE via POST /admin/partner-earnings/<id>/delete
        res_del = client.post(f'/admin/partner-earnings/{record.id}/delete', follow_redirects=True)
        assert res_del.status_code == 200

        record_check = db.session.get(PartnerEarningsRecord, record.id)
        assert record_check is None


# ==============================================================================
# TEST 10: AUTHENTICATION & ROLE-BASED ACCESS CONTROL
# ==============================================================================

def test_partner_earnings_auth_protection(app_client):
    client, app, _, regular = app_client

    with app.app_context():
        partners = get_active_partners()
        target = partners[0]

        # 1. Unauthenticated requests redirected to login
        res_unauth = client.post('/admin/partner-earnings/create', data={
            'partner_id': str(target.id),
            'amount': '10000',
            'earnings_date': date.today().strftime('%Y-%m-%d')
        })
        assert res_unauth.status_code == 302
        assert '/login' in res_unauth.headers.get('Location', '')

        # 2. Non-admin (candidate) forbidden/redirected
        client.post('/login', data={'email': regular.email, 'password': 'RegularPass123!'}, follow_redirects=True)
        res_nonadmin = client.post('/admin/partner-earnings/create', data={
            'partner_id': str(target.id),
            'amount': '10000',
            'earnings_date': date.today().strftime('%Y-%m-%d')
        })
        assert res_nonadmin.status_code in [302, 403]


# ==============================================================================
# TEST 11: UI RENDERING OF PARTNER EARNINGS COMPONENTS
# ==============================================================================

def test_partner_earnings_ui_elements_rendered(app_client):
    client, app, admin, _ = app_client

    with app.app_context():
        partners = get_active_partners()
        target = partners[0]

        # Seed one record
        create_partner_earnings_record(
            partner_id=target.id,
            amount=75000.0,
            earnings_date=date.today(),
            description='Strategic Consulting',
            reference='REF-STRAT-75',
            created_by=admin.id
        )

        client.post('/login', data={'email': admin.email, 'password': 'AdminPass123!'}, follow_redirects=True)
        res = client.get('/admin/money')
        assert res.status_code == 200

        html = res.get_data(as_text=True)

        # Header button
        assert "Add Record" in html
        assert "openAddPartnerEarningsModal()" in html

        # Chart overview card
        assert "Partner Earnings Overview" in html
        assert "Total contribution by partners (highest to lowest)" in html

        # Modals exist in DOM
        assert 'id="modalAddPartnerEarnings"' in html
        assert 'id="modalEditPartnerEarnings"' in html
        assert 'id="modalDeletePartnerEarnings"' in html

        # Records table section
        assert "Partner Earnings Records" in html
        assert "REF-STRAT-75" in html
        assert "Strategic Consulting" in html
        assert target.name in html
        assert "₹75,000" in html
