import unittest
from app import create_app


class PricingRouteTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_pricing_redirects_to_services(self):
        """Visiting /pricing should redirect to /services with a 301 redirect."""
        response = self.client.get('/pricing')
        self.assertEqual(response.status_code, 301)
        self.assertIn('/services', response.headers.get('Location', ''))


if __name__ == '__main__':
    unittest.main()
