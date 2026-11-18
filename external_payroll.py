"""
Module External Payroll API untuk integrasi aman antara Finance (finance.lintas.asia)
dan Portal Karir/HRMS (karir.faishalnafi.com).
"""
import os
import secrets
import hmac
import sqlite3
from typing import Optional, Dict, Any, List
from functools import wraps
from flask import Blueprint, request, jsonify, make_response

SETTINGS_API_KEY = 'api_external_payroll_key'
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'finansial.db')

external_api_bp = Blueprint('external_api_v1', __name__, url_prefix='/api/v1')

BULAN_INDONESIA = [
    '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
]

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

        # Generate key baru berkekuatan tinggi (la_sec_ + 56 hex chars)
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

def _apply_cors_headers(response):
    """Menambahkan CORS headers standar untuk request API eksternal."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-KEY, x-api-key, Accept'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response

def require_external_api_key(f):
    """
    Decorator proteksi endpoint API eksternal.
    Mendukung autentikasi via:
    - Header 'X-API-KEY' / 'x-api-key'
    - Header 'Authorization: Bearer <token>'
    - Query parameter '?api_key=<token>' (fallback)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'OPTIONS':
            resp = make_response('', 204)
            return _apply_cors_headers(resp)

        # 1. Cek Header X-API-KEY
        provided_key = request.headers.get('X-API-KEY') or request.headers.get('x-api-key')
        
        # 2. Cek Header Authorization: Bearer <token>
        if not provided_key:
            auth_header = request.headers.get('Authorization', '').strip()
            if auth_header.lower().startswith('bearer '):
                provided_key = auth_header[7:].strip()

        # 3. Fallback query parameter
        if not provided_key:
            provided_key = request.args.get('api_key')

        if not verify_external_api_key(provided_key):
            resp = jsonify({
                'success': False,
                'error': 'Unauthorized',
                'message': "Invalid or missing API Key. Provide via 'X-API-KEY' or 'Authorization: Bearer <token>' header."
            })
            resp.status_code = 401
            return _apply_cors_headers(resp)

        return f(*args, **kwargs)
    return decorated_function

@external_api_bp.after_request
def after_api_request(response):
    """Menambahkan CORS dan security header ke setiap response API."""
    response = _apply_cors_headers(response)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

# ---------- Helper Pemformatan Slip & Terbilang ----------

def _terbilang_isi(n: int) -> str:
    satuan = ('', 'satu', 'dua', 'tiga', 'empat', 'lima', 'enam', 'tujuh', 'delapan', 'sembilan', 'sepuluh', 'sebelas')
    if n < 12:
        return satuan[n]
    if n < 20:
        return satuan[n - 10] + ' belas'
    if n < 100:
        return f'{satuan[n // 10]} puluh {_terbilang_isi(n % 10)}'.strip()
    if n < 200:
        return f'seratus {_terbilang_isi(n - 100)}'.strip()
    if n < 1000:
        return f'{_terbilang_isi(n // 100)} ratus {_terbilang_isi(n % 100)}'.strip()
    if n < 2000:
        return f'seribu {_terbilang_isi(n - 1000)}'.strip()
    for besar, nama in ((10 ** 12, 'triliun'), (10 ** 9, 'miliar'), (10 ** 6, 'juta'), (10 ** 3, 'ribu')):
        if n >= besar:
            return f'{_terbilang_isi(n // besar)} {nama} {_terbilang_isi(n % besar)}'.strip()
    return ''

def format_terbilang_rupiah(nilai: float) -> str:
    try:
        v = round(abs(float(nilai or 0)), 2)
    except (TypeError, ValueError):
        v = 0.0
    utuh = int(v)
    teks = (_terbilang_isi(utuh) or 'nol') + ' rupiah'
    return teks[0].upper() + teks[1:]

def format_payroll_record(p: Any) -> Dict[str, Any]:
    row = dict(p) if isinstance(p, sqlite3.Row) else p
    bln_idx = int(row.get('periode_bulan', 0) or 0)
    nama_bln = BULAN_INDONESIA[bln_idx] if 1 <= bln_idx <= 12 else ''

    bpjs_kes_kar = float(row.get('bpjs_kes_kar') or 0)
    bpjs_tk_kar = float(row.get('bpjs_tk_kar') or 0)
    pph21 = float(row.get('pph21') or 0)
    total_potongan = bpjs_kes_kar + bpjs_tk_kar + pph21

    bpjs_kes_prs = float(row.get('bpjs_kes_prs') or 0)
    bpjs_tk_prs = float(row.get('bpjs_tk_prs') or 0)
    bpjs_jkk_prs = float(row.get('bpjs_jkk_prs') or 0)
    bpjs_jkm_prs = float(row.get('bpjs_jkm_prs') or 0)
    total_tanggungan = bpjs_kes_prs + bpjs_tk_prs + bpjs_jkk_prs + bpjs_jkm_prs

    gaji_bersih = float(row.get('gaji_bersih') or 0)
    status_bayar = row.get('status_bayar') or 'BELUM_DIBAYAR'

    return {
        'id': row['id'],
        'periode': {
            'bulan': bln_idx,
            'nama_bulan': nama_bln,
            'tahun': int(row.get('periode_tahun', 0) or 0)
        },
        'status_bayar': status_bayar,
        'is_paid': (status_bayar == 'SUDAH_DIBAYAR'),
        'tanggal_bayar': row.get('tanggal_bayar'),
        'penghasilan': {
            'jenis_upah': row.get('jenis_upah') or 'BULANAN',
            'gaji_pokok': float(row.get('gaji_pokok') or 0),
            'tunjangan': float(row.get('tunjangan') or 0),
            'uang_makan': float(row.get('uang_makan') or 0),
            'uang_transport': float(row.get('uang_transport') or 0),
            'bonus': float(row.get('bonus') or 0),
            'lain_lain': float(row.get('lain_lain') or 0),
            'penghasilan_bruto': float(row.get('penghasilan_bruto') or 0)
        },
        'potongan': {
            'bpjs_kesehatan': bpjs_kes_kar,
            'bpjs_ketenagakerjaan': bpjs_tk_kar,
            'pph21': pph21,
            'total_potongan': round(total_potongan, 2)
        },
        'tanggungan_perusahaan': {
            'bpjs_kesehatan': bpjs_kes_prs,
            'bpjs_ketenagakerjaan': bpjs_tk_prs,
            'bpjs_jkk': bpjs_jkk_prs,
            'bpjs_jkm': bpjs_jkm_prs,
            'total_tanggungan': round(total_tanggungan, 2)
        },
        'take_home_pay': gaji_bersih,
        'terbilang': format_terbilang_rupiah(gaji_bersih),
        'catatan': row.get('catatan') or '',
        'tanggal_proses': str(row.get('dibuat') or '')
    }

# ---------- API Endpoints ----------

@external_api_bp.route('/auth/verify', methods=['GET', 'OPTIONS'])
@require_external_api_key
def auth_verify():
    """Endpoint pengecekan validitas API Key."""
    return jsonify({
        'success': True,
        'message': 'API Key is valid and authorized.',
        'status': 'authenticated'
    })

@external_api_bp.route('/payroll/<employee_id>', methods=['GET', 'OPTIONS'])
@require_external_api_key
def get_employee_payroll(employee_id: str):
    """
    Mengambil daftar slip gaji / payroll untuk karyawan tertentu berdasarkan
    no_karyawan (contoh: 'EMP-001') atau ID internal.
    
    Query Parameters opsional:
    - bulan: int (1-12)
    - tahun: int (misal: 2026)
    - status: str ('SUDAH_DIBAYAR' / 'BELUM_DIBAYAR' / 'ALL')
    - limit: int (default 100)
    """
    clean_id = (employee_id or '').strip()
    if not clean_id:
        return jsonify({
            'success': False,
            'error': 'Bad Request',
            'message': 'Parameter employee_id wajib disertakan.'
        }), 400

    conn = get_db_connection()
    try:
        # Cari karyawan berdasarkan no_karyawan (case-insensitive) atau id numerik
        k = conn.execute("""
            SELECT id, no_karyawan, nama, jabatan, status_kerja, status_pajak, npwp, aktif
            FROM karyawan
            WHERE LOWER(TRIM(no_karyawan)) = LOWER(TRIM(?))
               OR (CAST(? AS INTEGER) > 0 AND id = CAST(? AS INTEGER))
            LIMIT 1
        """, (clean_id, clean_id, clean_id)).fetchone()

        if not k:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f"Karyawan dengan ID/No. Karyawan '{clean_id}' tidak ditemukan di sistem Finance."
            }), 404

        # Filter query
        bulan = request.args.get('bulan', type=int)
        tahun = request.args.get('tahun', type=int)
        status = (request.args.get('status') or '').strip().upper()
        limit = min(request.args.get('limit', default=100, type=int), 500)

        query = "SELECT * FROM payroll WHERE karyawan_id = ?"
        params: List[Any] = [k['id']]

        if bulan and 1 <= bulan <= 12:
            query += " AND periode_bulan = ?"
            params.append(bulan)
        if tahun and tahun > 2000:
            query += " AND periode_tahun = ?"
            params.append(tahun)
        if status in ('SUDAH_DIBAYAR', 'BELUM_DIBAYAR'):
            query += " AND status_bayar = ?"
            params.append(status)

        query += " ORDER BY periode_tahun DESC, periode_bulan DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        payrolls = [format_payroll_record(r) for r in rows]

        total_paid = sum(1 for p in payrolls if p['is_paid'])
        total_unpaid = len(payrolls) - total_paid

        return jsonify({
            'success': True,
            'data': {
                'employee': {
                    'id': k['id'],
                    'no_karyawan': k['no_karyawan'],
                    'nama': k['nama'],
                    'jabatan': k['jabatan'],
                    'status_kerja': k['status_kerja'],
                    'status_pajak': k['status_pajak'],
                    'npwp': k['npwp'],
                    'aktif': bool(k['aktif'])
                },
                'summary': {
                    'total_records': len(payrolls),
                    'total_dibayar': total_paid,
                    'total_belum_dibayar': total_unpaid
                },
                'payrolls': payrolls
            }
        })
    finally:
        conn.close()

@external_api_bp.route('/payroll/slip/<int:payroll_id>', methods=['GET', 'OPTIONS'])
@require_external_api_key
def get_payroll_slip_detail(payroll_id: int):
    """Mengambil rincian detail satu slip gaji berdasarkan ID payroll."""
    conn = get_db_connection()
    try:
        row = conn.execute("""
            SELECT p.*, k.nama AS nama_karyawan, k.jabatan, k.no_karyawan,
                   k.npwp, k.status_pajak, k.status_kerja
            FROM payroll p
            JOIN karyawan k ON k.id = p.karyawan_id
            WHERE p.id = ?
        """, (payroll_id,)).fetchone()

        if not row:
            return jsonify({
                'success': False,
                'error': 'Not Found',
                'message': f"Data payroll dengan ID {payroll_id} tidak ditemukan."
            }), 404

        return jsonify({
            'success': True,
            'data': {
                'employee': {
                    'id': row['karyawan_id'],
                    'no_karyawan': row['no_karyawan'],
                    'nama': row['nama_karyawan'],
                    'jabatan': row['jabatan'],
                    'status_kerja': row['status_kerja'],
                    'status_pajak': row['status_pajak'],
                    'npwp': row['npwp']
                },
                'slip': format_payroll_record(row)
            }
        })
    finally:
        conn.close()

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
