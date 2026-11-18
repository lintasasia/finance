import unittest
import urllib.parse
from app import app, db, get_setting

class TestOAuthLogin(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_oauth_login_redirects_to_google(self):
        resp = self.client.get('/login/oauth', headers={'Host': 'finance.lintas.asia', 'X-Forwarded-Proto': 'https'})
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers.get('Location', '')
        self.assertTrue(loc.startswith('https://accounts.google.com/o/oauth2/v2/auth'))
        parsed = urllib.parse.urlparse(loc)
        qs = urllib.parse.parse_qs(parsed.query)
        self.assertIn('client_id', qs)
        self.assertIn('redirect_uri', qs)
        self.assertEqual(qs['redirect_uri'][0], 'https://finance.lintas.asia/auth/google/callback')
        self.assertEqual(qs['response_type'][0], 'code')
        self.assertIn('state', qs)

    def test_oauth_callback_rejects_missing_state(self):
        resp = self.client.get('/auth/google/callback?code=fake_code&state=fake_state', follow_redirects=False)
        # Should redirect to login because session state does not match
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers.get('Location', '').endswith('/login'))

if __name__ == '__main__':
    unittest.main()
