import pytest
from app import create_app
from models import db, User, JobPosting, JobApplication, MoneyTransaction


@pytest.fixture
def client():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        # Ensure test admin user exists
        admin = User.query.filter_by(email='admin_nav_test@antimatrix.ai').first()
        if not admin:
            admin = User(
                email='admin_nav_test@antimatrix.ai',
                name='Admin Nav Tester',
                role='admin',
                is_active=True
            )
            admin.set_password('AdminPassword123!')
            db.session.add(admin)
            db.session.commit()

        # Ensure at least 1 job posting exists
        job = JobPosting.query.first()
        if not job:
            job = JobPosting(
                title='Test AI Engineer',
                department='Engineering',
                location='Remote',
                employment_type='Full-time',
                short_description='Test short description',
                description='Test full job description',
                requirements='Python, Flask',
                is_active=True,
                job_id='AM-TEST-001',
                job_code='AM-TEST-001'
            )
            db.session.add(job)
            db.session.commit()

        with app.test_client() as test_client:
            yield test_client, admin, job


def login_admin(client, admin):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True


def test_admin_dashboard_five_modules_and_widgets(client):
    test_client, admin, job = client
    login_admin(test_client, admin)

    response = test_client.get('/admin/dashboard')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Verify exactly 5 nav tabs
    assert 'class="admin-nav-tab active"' in html
    assert 'Overview' in html
    assert 'Job Postings' in html
    assert 'Candidate Applications' in html
    assert 'Templates' in html
    assert 'Money Management' in html

    # Verify retired module tabs are completely gone from the tabs
    assert 'Employees' not in html
    assert 'Inquiries' not in html
    assert 'Internship Benefits' not in html

    # Verify summary stat cards
    assert 'Total Jobs' in html
    assert 'Active Openings' in html
    assert 'Candidate Applications' in html
    assert 'Net Balance' in html


def test_admin_jobs_page_navigation(client):
    test_client, admin, job = client
    login_admin(test_client, admin)

    response = test_client.get('/admin/jobs')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Verify 5 nav tabs
    assert 'Overview' in html
    assert 'Job Postings' in html
    assert 'Candidate Applications' in html
    assert 'Templates' in html
    assert 'Money Management' in html
    assert 'Employees' not in html
    assert 'Internship Benefits' not in html


def test_admin_money_management_navigation(client):
    test_client, admin, job = client
    login_admin(test_client, admin)

    response = test_client.get('/admin/money-management')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Verify 5 nav tabs
    assert 'Overview' in html
    assert 'Job Postings' in html
    assert 'Candidate Applications' in html
    assert 'Templates' in html
    assert 'Money Management' in html
    assert 'Employees' not in html
    assert 'Inquiries' not in html
    assert 'Internship Benefits' not in html


def test_retired_routes_redirect_to_dashboard(client):
    test_client, admin, _ = client
    login_admin(test_client, admin)

    for retired_url in [
        '/admin/employees',
        '/admin/employees/create',
        '/admin/inquiries',
        '/admin/internship-benefits'
    ]:
        resp = test_client.get(retired_url, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'This administrative module has been retired.' in html
        assert 'Overview' in html


def test_navbar_admin_dropdown_links(client):
    test_client, admin, _ = client
    login_admin(test_client, admin)

    resp = test_client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    # In dropdown/drawer:
    assert 'Admin Dashboard' in html
    assert 'Job Postings' in html
    assert 'Candidate Applications' in html
    assert 'Templates' in html
    assert 'Money Management' in html


def test_public_careers_navbar_get_started(client):
    test_client, _, _ = client

    # /careers page displays Get Started
    resp = test_client.get('/careers')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Get Started' in html

    # Home page displays Get Started
    resp_home = test_client.get('/')
    assert resp_home.status_code == 200
    html_home = resp_home.data.decode('utf-8')
    assert 'Get Started' in html_home
