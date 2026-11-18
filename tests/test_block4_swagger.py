"""
Unit tests for Block 4: Swagger UI & OpenAPI 3.0.3 Specification.
"""
import unittest
import os
import sys
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from external_payroll import get_openapi_spec

class TestBlock4Swagger(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_openapi_spec_structure(self):
        spec = get_openapi_spec()
        self.assertEqual(spec['openapi'], '3.0.3')
        self.assertEqual(spec['info']['title'], 'Lintas Asia Finance - External Payroll API')
        self.assertEqual(spec['info']['version'], '1.0.0')

        # Check security schemes
        sec = spec['components']['securitySchemes']
        self.assertIn('ApiKeyAuth', sec)
        self.assertEqual(sec['ApiKeyAuth']['name'], 'X-API-KEY')
        self.assertEqual(sec['ApiKeyAuth']['in'], 'header')
        self.assertIn('BearerAuth', sec)
        self.assertEqual(sec['BearerAuth']['scheme'], 'bearer')

        # Check documented endpoints
        paths = spec['paths']
        self.assertIn('/auth/verify', paths)
        self.assertIn('/payroll/{employee_id}', paths)
        self.assertIn('/payroll/slip/{payroll_id}', paths)

        # Check schemas
        schemas = spec['components']['schemas']
        self.assertIn('Employee', schemas)
        self.assertIn('PayrollRecord', schemas)
        self.assertIn('PayrollSummary', schemas)
        self.assertIn('ApiError', schemas)

    def test_get_openapi_json_endpoint(self):
        resp = self.client.get('/api/v1/openapi.json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get('Access-Control-Allow-Origin'), '*')
        data = resp.get_json()
        self.assertEqual(data['openapi'], '3.0.3')
        self.assertIn('/payroll/{employee_id}', data['paths'])

    def test_get_swagger_ui_html(self):
        resp = self.client.get('/api/v1/docs')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp.content_type)
        html = resp.data.decode('utf-8')
        self.assertIn('SwaggerUIBundle', html)
        self.assertIn('/api/v1/openapi.json', html)
        self.assertIn('Lintas Asia Finance', html)

    def test_global_docs_redirects(self):
        # Test /api/docs redirect
        resp1 = self.client.get('/api/docs')
        self.assertEqual(resp1.status_code, 302)
        self.assertIn('/api/v1/docs', resp1.headers.get('Location', ''))

        # Test /docs redirect
        resp2 = self.client.get('/docs')
        self.assertEqual(resp2.status_code, 302)
        self.assertIn('/api/v1/docs', resp2.headers.get('Location', ''))

        # Follow redirect should return 200
        resp_follow = self.client.get('/api/docs', follow_redirects=True)
        self.assertEqual(resp_follow.status_code, 200)
        self.assertIn('SwaggerUIBundle', resp_follow.data.decode('utf-8'))

if __name__ == '__main__':
    unittest.main()
