import unittest
from flask import url_for
from app import create_app
from models import db, User


class AdminLoginRoutingTestCase(unittest.TestCase):
    """
    Test suite for admin login routing:
    - /admin/login compatibility redirect to canonical /login?next=/admin/
    - Preserving safe next targets and sanitizing open redirects
    - Redirecting already-authenticated admins who visit /login to admin.dashboard
    - Preserving existing member login redirects (to /)
    - Relative next path generation in admin_required decorator
    - Post-login redirection for admin vs member roles
    - Role-based authorization enforcement on admin routes
    """

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Regular member user
        self.member = User(
            name='Regular Member',
            email='member@test.com',
            role='member',
            phone='+1 555-0100',
            provider='email'
        )
        self.member.set_password('MemberPass123!')
        db.session.add(self.member)

        # Admin user
        self.admin = User(
            name='Admin User',
            email='admin@test.com',
            role='admin',
            phone='+1 555-0200',
            provider='email'
        )
        self.admin.set_password('AdminPass123!')
        db.session.add(self.admin)

        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _dashboard_url(self):
        with self.app.test_request_context():
            return url_for('admin.dashboard')

    def _login(self, email, password):
        return self.client.post('/login', data={
            'email': email,
            'password': password
        }, follow_redirects=False)

    def test_unauthenticated_admin_login_redirects_to_canonical_login(self):
        """GET /admin/login should redirect to /login?next=/admin/ without 404."""
        resp = self.client.get('/admin/login', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/', resp.headers['Location'])

    def test_unauthenticated_admin_login_trailing_slash_redirects_safely(self):
        """GET /admin/login/ should redirect safely without 404."""
        resp = self.client.get('/admin/login/', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/', resp.headers['Location'])

    def test_unauthenticated_admin_login_post_redirects_to_canonical_login(self):
        """POST /admin/login redirects to canonical /login."""
        resp = self.client.post('/admin/login', data={'next': '/admin/'}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/', resp.headers['Location'])

    def test_admin_login_preserves_safe_next_parameter(self):
        """GET /admin/login?next=/admin/inquiries redirects with that safe target."""
        resp = self.client.get('/admin/login?next=/admin/inquiries', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/inquiries', resp.headers['Location'])

    def test_admin_login_sanitizes_open_redirect_attempts(self):
        """Open redirect targets on /admin/login are sanitized to /admin/."""
        resp = self.client.get('/admin/login?next=https://evil.com/phish', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/', resp.headers['Location'])
        self.assertNotIn('evil.com', resp.headers['Location'])

        resp_scheme = self.client.get('/admin/login?next=//attacker.com/bypass', follow_redirects=False)
        self.assertEqual(resp_scheme.status_code, 302)
        self.assertIn('/login?next=/admin/', resp_scheme.headers['Location'])
        self.assertNotIn('attacker.com', resp_scheme.headers['Location'])

    def test_admin_required_passes_relative_path_in_next(self):
        """Unauthenticated access to /admin/ passes relative path in next parameter, not absolute URL."""
        resp = self.client.get('/admin/', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login?next=/admin/', resp.headers['Location'])
        self.assertNotIn('http://localhost/admin/', resp.headers['Location'])

    def test_authenticated_admin_visiting_login_redirects_to_admin_dashboard(self):
        """Authenticated admin visiting /login without next target redirects to url_for('admin.dashboard')."""
        self._login('admin@test.com', 'AdminPass123!')
        resp = self.client.get('/login', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], self._dashboard_url())

    def test_authenticated_admin_visiting_login_with_invalid_target_redirects_to_dashboard(self):
        """Authenticated admin visiting /login with unsafe next target redirects to url_for('admin.dashboard')."""
        self._login('admin@test.com', 'AdminPass123!')
        resp = self.client.get('/login?next=https://malicious.site', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], self._dashboard_url())

    def test_authenticated_admin_visiting_login_with_valid_target_preserves_target(self):
        """Authenticated admin visiting /login with valid relative target redirects to that target."""
        self._login('admin@test.com', 'AdminPass123!')
        resp = self.client.get('/login?next=/admin/inquiries', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], '/admin/inquiries')

    def test_authenticated_admin_visiting_admin_login_redirects_to_dashboard(self):
        """Authenticated admin visiting /admin/login directly redirects to admin dashboard."""
        self._login('admin@test.com', 'AdminPass123!')
        resp = self.client.get('/admin/login', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], self._dashboard_url())

    def test_authenticated_member_visiting_login_redirects_to_home(self):
        """Authenticated regular member visiting /login without next target continues to redirect to /."""
        self._login('member@test.com', 'MemberPass123!')
        resp = self.client.get('/login', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], '/')

    def test_authenticated_member_visiting_login_with_valid_target_preserves_target(self):
        """Authenticated regular member visiting /login with next target redirects to target."""
        self._login('member@test.com', 'MemberPass123!')
        resp = self.client.get('/login?next=/profile', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], '/profile')

    def test_admin_post_login_redirects_to_admin_dashboard_without_next(self):
        """Admin submitting credentials to /login without next target redirects to url_for('admin.dashboard')."""
        resp = self._login('admin@test.com', 'AdminPass123!')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], self._dashboard_url())

    def test_member_post_login_redirects_to_home_without_next(self):
        """Regular member submitting credentials to /login without next target redirects to /."""
        resp = self._login('member@test.com', 'MemberPass123!')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], '/')

    def test_admin_post_login_preserves_requested_next_target(self):
        """Admin submitting credentials to /login with next target is redirected to that target."""
        resp = self.client.post('/login?next=/admin/inquiries', data={
            'email': 'admin@test.com',
            'password': 'AdminPass123!'
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], '/admin/inquiries')

    def test_member_accessing_admin_area_returns_403(self):
        """Member role attempting to access admin dashboard receives 403 Forbidden."""
        self._login('member@test.com', 'MemberPass123!')
        resp = self.client.get('/admin/', follow_redirects=False)
        self.assertEqual(resp.status_code, 403)

    def test_admin_accessing_admin_area_returns_200(self):
        """Admin role accessing admin dashboard receives 200 OK."""
        self._login('admin@test.com', 'AdminPass123!')
        resp = self.client.get('/admin/', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
