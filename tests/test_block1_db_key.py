"""
Unit tests for Block 1: Database Migration & Private API Key Management.
"""
import unittest
import sqlite3
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from external_payroll import (
    SETTINGS_API_KEY,
    get_or_create_external_api_key,
    set_external_api_key,
    verify_external_api_key,
    migrate_payroll_status_columns
)

class TestBlock1DatabaseAndKey(unittest.TestCase):
    def setUp(self):
        # Use an in-memory database for isolated, reproducible testing
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Create settings table
        self.conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")

        # Create base payroll and related tables without the new columns
        self.conn.execute("""
            CREATE TABLE jurnal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                keterangan TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE karyawan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                no_karyawan TEXT,
                nama TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE payroll (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                karyawan_id INTEGER NOT NULL,
                periode_bulan INTEGER NOT NULL,
                periode_tahun INTEGER NOT NULL,
                gaji_bersih REAL DEFAULT 0,
                jurnal_id INTEGER,
                catatan TEXT DEFAULT '',
                dibuat DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Clean environment variable before each test
        if 'EXTERNAL_PAYROLL_API_KEY' in os.environ:
            del os.environ['EXTERNAL_PAYROLL_API_KEY']

    def tearDown(self):
        self.conn.close()
        if 'EXTERNAL_PAYROLL_API_KEY' in os.environ:
            del os.environ['EXTERNAL_PAYROLL_API_KEY']

    def test_migration_adds_columns_and_backfills(self):
        # Seed test data before migration
        self.conn.execute("INSERT INTO jurnal (id, tanggal, keterangan) VALUES (1, '2026-11-02', 'Jurnal Gaji Nov')")
        self.conn.execute("INSERT INTO payroll (id, karyawan_id, periode_bulan, periode_tahun, gaji_bersih, jurnal_id, dibuat) "
                          "VALUES (101, 1, 11, 2026, 1500000, 1, '2026-11-01 10:00:00')")
        self.conn.execute("INSERT INTO payroll (id, karyawan_id, periode_bulan, periode_tahun, gaji_bersih, jurnal_id, dibuat) "
                          "VALUES (102, 2, 11, 2026, 2000000, NULL, '2026-11-01 11:00:00')")
        self.conn.commit()

        # Run migration
        migrate_payroll_status_columns(self.conn)

        # Check table columns
        cur = self.conn.execute("PRAGMA table_info(payroll)")
        cols = {r['name'] for r in cur.fetchall()}
        self.assertIn('status_bayar', cols)
        self.assertIn('tanggal_bayar', cols)

        # Check backfilled record with jurnal_id
        row1 = self.conn.execute("SELECT status_bayar, tanggal_bayar FROM payroll WHERE id=101").fetchone()
        self.assertEqual(row1['status_bayar'], 'SUDAH_DIBAYAR')
        self.assertEqual(row1['tanggal_bayar'], '2026-11-02')

        # Check record without jurnal_id remains BELUM_DIBAYAR
        row2 = self.conn.execute("SELECT status_bayar, tanggal_bayar FROM payroll WHERE id=102").fetchone()
        self.assertEqual(row2['status_bayar'], 'BELUM_DIBAYAR')
        self.assertIsNone(row2['tanggal_bayar'])

    def test_migration_is_idempotent(self):
        # Running migration twice should not cause errors
        migrate_payroll_status_columns(self.conn)
        migrate_payroll_status_columns(self.conn)

        cur = self.conn.execute("PRAGMA table_info(payroll)")
        cols = [r['name'] for r in cur.fetchall()]
        self.assertEqual(cols.count('status_bayar'), 1)
        self.assertEqual(cols.count('tanggal_bayar'), 1)

    def test_api_key_auto_generation_and_persistence(self):
        key1 = get_or_create_external_api_key(self.conn)
        self.assertTrue(key1.startswith('la_sec_'))
        self.assertGreaterEqual(len(key1), 60)

        # Key must be stored in settings table
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (SETTINGS_API_KEY,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['value'], key1)

        # Subsequent retrieval must return identical key
        key2 = get_or_create_external_api_key(self.conn)
        self.assertEqual(key1, key2)

    def test_api_key_env_override(self):
        override_key = 'la_custom_env_secret_key_123456789'
        os.environ['EXTERNAL_PAYROLL_API_KEY'] = override_key

        key = get_or_create_external_api_key(self.conn)
        self.assertEqual(key, override_key)

    def test_set_external_api_key_and_validation(self):
        # Valid key
        new_key = 'la_sec_custom_rotated_key_9876543210'
        result = set_external_api_key(new_key, self.conn)
        self.assertEqual(result, new_key)
        self.assertEqual(get_or_create_external_api_key(self.conn), new_key)

        # Insecure short key should be rejected
        with self.assertRaises(ValueError):
            set_external_api_key('too_short', self.conn)

    def test_verify_external_api_key(self):
        valid_key = get_or_create_external_api_key(self.conn)

        # Correct key
        self.assertTrue(verify_external_api_key(valid_key, self.conn))
        # Correct key with surrounding whitespace
        self.assertTrue(verify_external_api_key(f"  {valid_key} \n", self.conn))

        # Incorrect keys
        self.assertFalse(verify_external_api_key('wrong_key_12345678901234567890', self.conn))
        self.assertFalse(verify_external_api_key(valid_key[:-1], self.conn))
        self.assertFalse(verify_external_api_key('', self.conn))
        self.assertFalse(verify_external_api_key(None, self.conn))
        self.assertFalse(verify_external_api_key(123456, self.conn))

if __name__ == '__main__':
    unittest.main()
