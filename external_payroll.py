"""
Module External Payroll API untuk integrasi aman antara Finance (finance.lintas.asia)
dan Portal Karir/HRMS (karir.faishalnafi.com).
"""
import os
import secrets
import hmac
import sqlite3
from typing import Optional

SETTINGS_API_KEY = 'api_external_payroll_key'
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'finansial.db')

def get_db_connection(db_path: Optional[str] = None):
    """Membuka koneksi sqlite3 dengan row factory Row."""
    path = db_path or os.environ.get('FINANCE_DB_PATH') or DEFAULT_DB_PATH
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_or_create_external_api_key(conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None) -> str:
    """
    Mengambil Private API Key aktif.
    Prioritas:
    1. Environment variable EXTERNAL_PAYROLL_API_KEY jika diset.
    2. Tabel settings (key: 'api_external_payroll_key').
    3. Jika belum ada, otomatis generate key baru (64-char secure random), simpan ke database, dan kembalikan.
    """
    env_key = os.environ.get('EXTERNAL_PAYROLL_API_KEY', '').strip()
    if env_key:
        return env_key

    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM settings WHERE key=?", (SETTINGS_API_KEY,)).fetchone()
        if row and row['value'] and row['value'].strip():
            return row['value'].strip()

        # Generate key baru berkekuatan tinggi
        # Format: la_sec_ + 56 karakter hex kriptografis (total 63 karakter)
        new_key = f"la_sec_{secrets.token_hex(28)}"
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SETTINGS_API_KEY, new_key)
        )
        conn.commit()
        return new_key
    finally:
        if close_after:
            conn.close()

def set_external_api_key(new_key: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None) -> str:
    """Mengatur atau merotasi Private API Key secara eksplisit."""
    clean_key = new_key.strip()
    if not clean_key or len(clean_key) < 16:
        raise ValueError("API Key minimal harus 16 karakter demi keamanan.")

    close_after = False
    if conn is None:
        conn = get_db_connection(db_path)
        close_after = True

    try:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SETTINGS_API_KEY, clean_key)
        )
        conn.commit()
        return clean_key
    finally:
        if close_after:
            conn.close()

def verify_external_api_key(provided_key: Optional[str], conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None) -> bool:
    """
    Memverifikasi apakah provided_key cocok dengan Private API Key resmi.
    Menggunakan hmac.compare_digest untuk mencegah timing attacks.
    """
    if not provided_key or not isinstance(provided_key, str):
        return False
    
    clean_provided = provided_key.strip()
    if not clean_provided:
        return False

    valid_key = get_or_create_external_api_key(conn=conn, db_path=db_path)
    return hmac.compare_digest(clean_provided, valid_key)

def migrate_payroll_status_columns(conn: sqlite3.Connection):
    """
    Melakukan migrasi skema tabel payroll:
    - Menambahkan kolom status_bayar (DEFAULT 'BELUM_DIBAYAR')
    - Menambahkan kolom tanggal_bayar (TEXT / DATE)
    - Melakukan backfill untuk record lama yang sudah terkait jurnal pembayaran
    """
    cur = conn.execute("PRAGMA table_info(payroll)")
    cols = {r['name'] if isinstance(r, sqlite3.Row) else r[1] for r in cur.fetchall()}

    if 'status_bayar' not in cols:
        conn.execute("ALTER TABLE payroll ADD COLUMN status_bayar TEXT DEFAULT 'BELUM_DIBAYAR'")
    
    if 'tanggal_bayar' not in cols:
        conn.execute("ALTER TABLE payroll ADD COLUMN tanggal_bayar TEXT")

    # Backfill record lama yang sudah memiliki jurnal_id
    conn.execute("""
        UPDATE payroll
        SET status_bayar = 'SUDAH_DIBAYAR',
            tanggal_bayar = COALESCE(
                (SELECT tanggal FROM jurnal WHERE jurnal.id = payroll.jurnal_id),
                DATE(payroll.dibuat)
            )
        WHERE jurnal_id IS NOT NULL 
          AND (status_bayar IS NULL OR status_bayar = '' OR status_bayar = 'BELUM_DIBAYAR')
    """)
    conn.commit()
