"""
Unit tests for Block 3: Payroll Employee & Pay Slip REST Endpoints.
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
    set_external_api_key,
    format_terbilang_rupiah
)

class TestBlock3PayrollEndpoints(unittest.TestCase):
    def setUp(self):
        # Create an isolated Flask test app
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(external_api_bp)
        self.client = self.app.test_client()

        # Temporary in-memory SQLite DB
        self.db_file = '/tmp/test_block3_finansial.db'
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

        self.conn = sqlite3.connect(self.db_file)
        self.conn.row_factory = sqlite3.Row

        # Tables setup
        self.conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute("""
            CREATE TABLE karyawan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                no_karyawan TEXT,
                nama TEXT,
                jabatan TEXT,
                status_kerja TEXT DEFAULT 'TETAP',
                status_pajak TEXT DEFAULT 'TK0',
                npwp TEXT DEFAULT '',
                aktif INTEGER DEFAULT 1
            )
        """)
        self.conn.execute("""
            CREATE TABLE payroll (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                karyawan_id INTEGER NOT NULL,
                periode_bulan INTEGER NOT NULL,
                periode_tahun INTEGER NOT NULL,
                gaji_pokok REAL DEFAULT 0,
                tunjangan REAL DEFAULT 0,
                penghasilan_bruto REAL DEFAULT 0,
                bpjs_kes_kar REAL DEFAULT 0,
                bpjs_tk_kar REAL DEFAULT 0,
                bpjs_kes_prs REAL DEFAULT 0,
                bpjs_tk_prs REAL DEFAULT 0,
                bpjs_jkk_prs REAL DEFAULT 0,
                bpjs_jkm_prs REAL DEFAULT 0,
                pph21 REAL DEFAULT 0,
                gaji_bersih REAL DEFAULT 0,
                status_bayar TEXT DEFAULT 'BELUM_DIBAYAR',
                tanggal_bayar TEXT,
                catatan TEXT DEFAULT '',
                dibuat DATETIME DEFAULT CURRENT_TIMESTAMP,
                jenis_upah TEXT DEFAULT 'BULANAN',
                bonus REAL DEFAULT 0,
                uang_makan REAL DEFAULT 0,
                uang_transport REAL DEFAULT 0,
                lain_lain REAL DEFAULT 0
            )
        """)

        # Seed Karyawan
        self.conn.execute("INSERT INTO karyawan (id, no_karyawan, nama, jabatan) VALUES (1, 'EMP-001', 'Faishal Nafi', 'CEO')")
        self.conn.execute("INSERT INTO karyawan (id, no_karyawan, nama, jabatan) VALUES (2, 'EMP-002', 'Safa', 'CFO')")

        # Seed Payroll
        # Safa: Nov 2026 (SUDAH_DIBAYAR)
        self.conn.execute("""
            INSERT INTO payroll (id, karyawan_id, periode_bulan, periode_tahun, gaji_pokok, tunjangan, penghasilan_bruto,
                                bpjs_kes_kar, bpjs_tk_kar, pph21, gaji_bersih, status_bayar, tanggal_bayar, catatan)
            VALUES (10, 2, 11, 2026, 125000, 0, 125000, 0, 0, 0, 125000, 'SUDAH_DIBAYAR', '2026-11-02', 'Fee Safa Nov')
        """)
        # Safa: Okt 2026 (BELUM_DIBAYAR)
        self.conn.execute("""
            INSERT INTO payroll (id, karyawan_id, periode_bulan, periode_tahun, gaji_pokok, tunjangan, penghasilan_bruto,
                                bpjs_kes_kar, bpjs_tk_kar, pph21, gaji_bersih, status_bayar, tanggal_bayar, catatan)
            VALUES (11, 2, 10, 2026, 110000, 10000, 120000, 2000, 3000, 5000, 110000, 'BELUM_DIBAYAR', NULL, 'Fee Safa Okt')
        """)
        self.conn.commit()

        # Configure API Key
        self.test_key = "la_sec_payroll_test_endpoint_key_123456789"
        set_external_api_key(self.test_key, self.conn)
        os.environ['EXTERNAL_PAYROLL_API_KEY'] = self.test_key
        os.environ['FINANCE_DB_PATH'] = self.db_file

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)
        if 'EXTERNAL_PAYROLL_API_KEY' in os.environ:
            del os.environ['EXTERNAL_PAYROLL_API_KEY']
        if 'FINANCE_DB_PATH' in os.environ:
            del os.environ['FINANCE_DB_PATH']

    def test_terbilang_formatter(self):
        self.assertEqual(format_terbilang_rupiah(125000), 'Seratus dua puluh lima ribu rupiah')
        self.assertEqual(format_terbilang_rupiah(0), 'Nol rupiah')
        self.assertEqual(format_terbilang_rupiah(2500000), 'Dua juta lima ratus ribu rupiah')

    def test_get_payroll_by_employee_id(self):
        # Fetch by no_karyawan
        resp = self.client.get('/api/v1/payroll/EMP-002', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp.status_code, 200)
        res = resp.get_json()
        self.assertTrue(res['success'])
        
        emp = res['data']['employee']
        self.assertEqual(emp['no_karyawan'], 'EMP-002')
        self.assertEqual(emp['nama'], 'Safa')

        summary = res['data']['summary']
        self.assertEqual(summary['total_records'], 2)
        self.assertEqual(summary['total_dibayar'], 1)
        self.assertEqual(summary['total_belum_dibayar'], 1)

        payrolls = res['data']['payrolls']
        self.assertEqual(len(payrolls), 2)
        # Check ordering (Nov first, then Okt)
        self.assertEqual(payrolls[0]['periode']['bulan'], 11)
        self.assertEqual(payrolls[0]['status_bayar'], 'SUDAH_DIBAYAR')
        self.assertTrue(payrolls[0]['is_paid'])
        self.assertEqual(payrolls[0]['tanggal_bayar'], '2026-11-02')

        self.assertEqual(payrolls[1]['periode']['bulan'], 10)
        self.assertEqual(payrolls[1]['status_bayar'], 'BELUM_DIBAYAR')
        self.assertFalse(payrolls[1]['is_paid'])

    def test_get_payroll_by_internal_numeric_id(self):
        # Fetch by numeric id 2 (Safa)
        resp = self.client.get('/api/v1/payroll/2', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp.status_code, 200)
        res = resp.get_json()
        self.assertEqual(res['data']['employee']['nama'], 'Safa')

    def test_get_payroll_filters(self):
        # Filter by month 11
        resp = self.client.get('/api/v1/payroll/EMP-002?bulan=11', headers={'X-API-KEY': self.test_key})
        res = resp.get_json()
        self.assertEqual(len(res['data']['payrolls']), 1)
        self.assertEqual(res['data']['payrolls'][0]['periode']['bulan'], 11)

        # Filter by status SUDAH_DIBAYAR
        resp2 = self.client.get('/api/v1/payroll/EMP-002?status=SUDAH_DIBAYAR', headers={'X-API-KEY': self.test_key})
        res2 = resp2.get_json()
        self.assertEqual(len(res2['data']['payrolls']), 1)
        self.assertEqual(res2['data']['payrolls'][0]['status_bayar'], 'SUDAH_DIBAYAR')

        # Filter by status BELUM_DIBAYAR
        resp3 = self.client.get('/api/v1/payroll/EMP-002?status=BELUM_DIBAYAR', headers={'X-API-KEY': self.test_key})
        res3 = resp3.get_json()
        self.assertEqual(len(res3['data']['payrolls']), 1)
        self.assertEqual(res3['data']['payrolls'][0]['status_bayar'], 'BELUM_DIBAYAR')

    def test_get_payroll_not_found(self):
        resp = self.client.get('/api/v1/payroll/EMP-NONEXISTENT', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp.status_code, 404)
        res = resp.get_json()
        self.assertFalse(res['success'])
        self.assertIn('tidak ditemukan', res['message'])

    def test_get_single_slip_detail(self):
        resp = self.client.get('/api/v1/payroll/slip/10', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp.status_code, 200)
        res = resp.get_json()
        self.assertTrue(res['success'])
        self.assertEqual(res['data']['employee']['nama'], 'Safa')
        slip = res['data']['slip']
        self.assertEqual(slip['id'], 10)
        self.assertEqual(slip['take_home_pay'], 125000.0)
        self.assertEqual(slip['terbilang'], 'Seratus dua puluh lima ribu rupiah')
        self.assertEqual(slip['status_bayar'], 'SUDAH_DIBAYAR')

    def test_get_single_slip_not_found(self):
        resp = self.client.get('/api/v1/payroll/slip/9999', headers={'X-API-KEY': self.test_key})
        self.assertEqual(resp.status_code, 404)
        res = resp.get_json()
        self.assertFalse(res['success'])

if __name__ == '__main__':
    unittest.main()
