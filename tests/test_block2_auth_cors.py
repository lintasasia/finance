"""
Unit tests for Block 2: External API Authentication Middleware & CORS.
"""
import unittest
import sqlite3
import os
import sys
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask
from external_payroll import (
    external_api_bp,
    get_or_create_external_api_key,
    set_external_api_key
)

class TestBlock2AuthAndCORS(unittest.TestCase):
    def setUp(self):
        # Create an isolated Flask test app
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(external_api_bp)
        self.client = self.app.test_client()

        # In-memory database for API key management
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        
        # Seed test API key
        self.test_key = "la_sec_test_valid_key_1234567890abcdef1234567890"
        set_external_api_key(self.test_key, self.conn)

        # Set env var pointing to test key so require_external_api_key uses it during request context
        os.environ['EXTERNAL_PAYROLL_API_KEY'] = self.test_key

    def tearDown(self):
        self.conn.close()
        if 'EXTERNAL_PAYROLL_API_KEY' in os.environ:
            del os.environ['EXTERNAL_PAYROLL_API_KEY']

    def test_unauthorized_when_no_api_key(self):
        resp = self.client.get('/api/v1/auth/verify')
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Unauthorized')
        # Check CORS header present even on 401
        self.assertEqual(resp.headers.get('Access-Control-Allow-Origin'), '*')

    def test_unauthorized_when_invalid_api_key(self):
        resp = self.client.get('/api/v1/auth/verify', headers={'X-API-KEY': 'la_sec_invalid_dummy_key_00000000'})
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_authorized_with_x_api_key_header(self):
        # Exact case header
        resp = self.client.get('/api/v1/auth/verify', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'authenticated')

        # Lowercase header
        resp2 = self.client.get('/api/v1/auth/verify', headers={'x-api-key': self.test_key})
        self.assertEqual(resp2.status_code, 200)

    def test_authorized_with_bearer_token(self):
        # Capital Bearer
        resp = self.client.get('/api/v1/auth/verify', headers={'Authorization': f'Bearer {self.test_key}'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

        # Lowercase bearer
        resp2 = self.client.get('/api/v1/auth/verify', headers={'Authorization': f'bearer {self.test_key}'})
        self.assertEqual(resp2.status_code, 200)

    def test_authorized_with_query_param_fallback(self):
        resp = self.client.get(f'/api/v1/auth/verify?api_key={self.test_key}')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

    def test_cors_options_preflight(self):
        resp = self.client.open('/api/v1/auth/verify', method='OPTIONS')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers.get('Access-Control-Allow-Origin'), '*')
        self.assertIn('GET', resp.headers.get('Access-Control-Allow-Methods', ''))
        self.assertIn('X-API-KEY', resp.headers.get('Access-Control-Allow-Headers', ''))
        self.assertIn('Authorization', resp.headers.get('Access-Control-Allow-Headers', ''))

    def test_cross_block_key_rotation_immediately_invalidates_old_key(self):
        new_rotated_key = "la_sec_new_rotated_key_99998888777766665555"
        # Rotate key
        os.environ['EXTERNAL_PAYROLL_API_KEY'] = new_rotated_key

        # Old key now fails
        resp_old = self.client.get('/api/v1/auth/verify', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp_old.status_code, 401)

        # New key succeeds
        resp_new = self.client.get('/api/v1/auth/verify', headers={'X-API-KEY': new_rotated_key})
        self.assertEqual(resp_new.status_code, 200)

if __name__ == '__main__':
    unittest.main()
