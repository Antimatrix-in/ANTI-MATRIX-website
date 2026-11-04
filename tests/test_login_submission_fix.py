import unittest
from unittest.mock import patch
from app import create_app, db
from models import User, Employee


class LoginSubmissionFixTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Member user
        self.member = User.query.filter_by(email='member@antimatrix.ai').first()
        if not self.member:
            self.member = User(
                name='Standard Member',
                email='member@antimatrix.ai',
                role='member',
                is_active=True
            )
            self.member.set_password('MemberSecret123!')
            db.session.add(self.member)
        else:
            self.member.set_password('MemberSecret123!')

        # Admin user (may already exist from create_app)
        self.admin = User.query.filter_by(email='admin@antimatrix.ai').first()
        if not self.admin:
            self.admin = User(
                name='System Admin',
                email='admin@antimatrix.ai',
                role='admin',
                is_active=True
            )
            self.admin.set_password('AdminSecret123!')
            db.session.add(self.admin)
        else:
            self.admin.set_password('AdminSecret123!')

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_get_login_page_200(self):
        """GET /login returns 200 OK and contains login form elements."""
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Sign In', html)
        self.assertIn('name="csrf_token"', html)

    def test_get_homepage_200(self):
        """GET / returns 200 OK."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_get_api_health_200(self):
        """GET /api/health returns 200 OK."""
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'OK')

    def test_get_admin_unauthenticated_redirects(self):
        """GET /admin/ without authentication redirects to login with next parameter."""
        resp = self.client.get('/admin/', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/', resp.headers['Location'])

    def test_post_login_invalid_credentials_returns_401_json(self):
        """POST /login with invalid password returns 401 with proper error, never 404 or 500."""
        resp = self.client.post('/login', json={
            'email': 'member@antimatrix.ai',
            'password': 'WrongPassword123!'
        })
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'error')
        self.assertIn('password', data.get('errors', {}))

    def test_post_login_invalid_credentials_returns_401_form(self):
        """POST /login form submit with invalid password returns 401 on template, never 404 or 500."""
        resp = self.client.post('/login', data={
            'email': 'member@antimatrix.ai',
            'password': 'WrongPassword123!'
        })
        self.assertEqual(resp.status_code, 401)
        html = resp.get_data(as_text=True)
        self.assertIn('Invalid email or password', html)

    def test_post_login_nonexistent_user_returns_401(self):
        """POST /login with unknown email returns 401, not 404."""
        resp = self.client.post('/login', json={
            'email': 'nonexistent@antimatrix.ai',
            'password': 'SomePassword123!'
        })
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'error')

    def test_post_login_invalid_format_returns_400(self):
        """POST /login with invalid format returns 400 validation error."""
        resp = self.client.post('/login', json={
            'email': 'invalidformat',
            'password': 'ValidPassword123!'
        })
        self.assertEqual(resp.status_code, 400)

    def test_post_login_valid_member_redirects_home(self):
        """POST /login with valid member credentials redirects to /."""
        resp = self.client.post('/login', json={
            'email': 'member@antimatrix.ai',
            'password': 'MemberSecret123!'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('redirect'), '/')

    def test_post_login_valid_admin_redirects_admin_dashboard(self):
        """POST /login with valid admin credentials redirects to admin dashboard."""
        resp = self.client.post('/login', json={
            'email': 'admin@antimatrix.ai',
            'password': 'AdminSecret123!'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('/admin', data.get('redirect', ''))

    def test_post_login_survives_employee_table_exception(self):
        """
        Critical regression test: If Employee query fails (e.g. table/column missing in production),
        member and admin login MUST STILL SUCCEED and invalid login MUST return 401, NEVER 500 or 404!
        """
        with patch.object(Employee.query, 'filter', side_effect=Exception('relation "employees" does not exist')):
            # 1. Invalid login should return 401, not 500
            resp_bad = self.client.post('/login', json={
                'email': 'baduser@antimatrix.ai',
                'password': 'WrongPassword123!'
            })
            self.assertEqual(resp_bad.status_code, 401)

            # 2. Valid user login should succeed despite Employee query exception
            resp_good = self.client.post('/login', json={
                'email': 'member@antimatrix.ai',
                'password': 'MemberSecret123!'
            })
            self.assertEqual(resp_good.status_code, 200)
            self.assertEqual(resp_good.get_json().get('status'), 'success')


if __name__ == '__main__':
    unittest.main()
