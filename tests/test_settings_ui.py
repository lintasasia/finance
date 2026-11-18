"""
Unit tests for Settings Web UI: External API Key Configuration & Rotation.
"""
import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from external_payroll import get_or_create_external_api_key, set_external_api_key

class TestSettingsWebUI(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.original_key = get_or_create_external_api_key()

    def tearDown(self):
        if hasattr(self, 'original_key') and self.original_key:
            set_external_api_key(self.original_key)

    def test_settings_page_contains_api_card_for_admin(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'

        resp = self.client.get('/settings')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('Integrasi External API (siCare Karir', html)
        self.assertIn('name="external_api_key"', html)
        self.assertIn('value="save_external_api"', html)
        self.assertIn('value="generate_external_api_key"', html)
        self.assertIn('/api/v1/payroll/{employee_id}', html)

    def test_settings_save_external_api_key_via_web_form(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'

        custom_key = "la_sec_custom_from_web_form_12345678901234"
        resp = self.client.post('/settings', data={
            'action': 'save_external_api',
            'external_api_key': custom_key
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Private API Key berhasil disimpan', resp.data.decode('utf-8'))

        # Verify key is actively used
        active_key = get_or_create_external_api_key()
        self.assertEqual(active_key, custom_key)

    def test_settings_generate_new_key_via_web_button(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'

        resp = self.client.post('/settings', data={
            'action': 'generate_external_api_key'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Private API Key baru berhasil digenerate', resp.data.decode('utf-8'))

        active_key = get_or_create_external_api_key()
        self.assertTrue(active_key.startswith('la_sec_'))
        self.assertGreaterEqual(len(active_key), 60)

if __name__ == '__main__':
    unittest.main()
