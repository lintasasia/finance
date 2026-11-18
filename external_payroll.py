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
from flask import Blueprint, request, jsonify, make_response, render_template

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

# ---------- OpenAPI 3.0.3 Specification Generator ----------

def get_openapi_spec() -> Dict[str, Any]:
    """Menghasilkan struktur spesifikasi OpenAPI 3.0.3 resmi untuk Swagger UI."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Lintas Asia Finance - External Payroll API",
            "version": "1.0.0",
            "description": "API resmi untuk integrasi data penggajian dan slip gaji karyawan antara Finance ERP (finance.lintas.asia) dan Portal Karir siCare (karir.faishalnafi.com). Dilengkapi pengamanan Private API Key via header `X-API-KEY` atau `Authorization: Bearer <token>`.",
            "contact": {
                "name": "Tim IT Lintas Asia Group",
                "email": "faishalnafi50@gmail.com"
            }
        },
        "servers": [
            {
                "url": "/api/v1",
                "description": "API v1 Endpoint"
            }
        ],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-KEY",
                    "description": "Private API Key yang dikonfigurasi di menu Pengaturan Finance"
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Format token Bearer HTTP Authorization"
                }
            },
            "schemas": {
                "Employee": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "example": 2},
                        "no_karyawan": {"type": "string", "example": "EMP-002"},
                        "nama": {"type": "string", "example": "Safa"},
                        "jabatan": {"type": "string", "example": "Chief Financial Officer (CFO)"},
                        "status_kerja": {"type": "string", "example": "TETAP"},
                        "status_pajak": {"type": "string", "example": "TK0"},
                        "npwp": {"type": "string", "example": ""},
                        "aktif": {"type": "boolean", "example": True}
                    }
                },
                "PayrollSummary": {
                    "type": "object",
                    "properties": {
                        "total_records": {"type": "integer", "example": 1},
                        "total_dibayar": {"type": "integer", "example": 1},
                        "total_belum_dibayar": {"type": "integer", "example": 0}
                    }
                },
                "PayrollRecord": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "example": 1},
                        "periode": {
                            "type": "object",
                            "properties": {
                                "bulan": {"type": "integer", "example": 11},
                                "nama_bulan": {"type": "string", "example": "November"},
                                "tahun": {"type": "integer", "example": 2026}
                            }
                        },
                        "status_bayar": {"type": "string", "example": "SUDAH_DIBAYAR"},
                        "is_paid": {"type": "boolean", "example": True},
                        "tanggal_bayar": {"type": "string", "nullable": True, "example": "2026-11-02"},
                        "penghasilan": {
                            "type": "object",
                            "properties": {
                                "jenis_upah": {"type": "string", "example": "BULANAN"},
                                "gaji_pokok": {"type": "number", "example": 125000.0},
                                "tunjangan": {"type": "number", "example": 0.0},
                                "uang_makan": {"type": "number", "example": 0.0},
                                "uang_transport": {"type": "number", "example": 0.0},
                                "bonus": {"type": "number", "example": 0.0},
                                "lain_lain": {"type": "number", "example": 0.0},
                                "penghasilan_bruto": {"type": "number", "example": 125000.0}
                            }
                        },
                        "potongan": {
                            "type": "object",
                            "properties": {
                                "bpjs_kesehatan": {"type": "number", "example": 0.0},
                                "bpjs_ketenagakerjaan": {"type": "number", "example": 0.0},
                                "pph21": {"type": "number", "example": 0.0},
                                "total_potongan": {"type": "number", "example": 0.0}
                            }
                        },
                        "tanggungan_perusahaan": {
                            "type": "object",
                            "properties": {
                                "bpjs_kesehatan": {"type": "number", "example": 0.0},
                                "bpjs_ketenagakerjaan": {"type": "number", "example": 0.0},
                                "bpjs_jkk": {"type": "number", "example": 0.0},
                                "bpjs_jkm": {"type": "number", "example": 0.0},
                                "total_tanggungan": {"type": "number", "example": 0.0}
                            }
                        },
                        "take_home_pay": {"type": "number", "example": 125000.0},
                        "terbilang": {"type": "string", "example": "Seratus dua puluh lima ribu rupiah"},
                        "catatan": {"type": "string", "example": "Fee Safa Bulan November 2026"},
                        "tanggal_proses": {"type": "string", "example": "2026-11-15 02:57:22"}
                    }
                },
                "ApiError": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "error": {"type": "string", "example": "Unauthorized"},
                        "message": {"type": "string", "example": "Deskripsi pesan kesalahan"}
                    }
                }
            }
        },
        "security": [
            {"ApiKeyAuth": []},
            {"BearerAuth": []}
        ],
        "paths": {
            "/auth/verify": {
                "get": {
                    "tags": ["Autentikasi"],
                    "summary": "Validasi API Key",
                    "description": "Memeriksa apakah Private API Key yang dikirimkan valid dan terautentikasi.",
                    "responses": {
                        "200": {
                            "description": "API Key valid dan aktif",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean", "example": True},
                                            "message": {"type": "string", "example": "API Key is valid and authorized."},
                                            "status": {"type": "string", "example": "authenticated"}
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Unauthorized (Key hilang atau tidak cocok)",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            }
                        }
                    }
                }
            },
            "/payroll/{employee_id}": {
                "get": {
                    "tags": ["Payroll & Slip Gaji"],
                    "summary": "Ambil Riwayat Payroll & Status Gaji Karyawan",
                    "description": "Mengambil daftar slip gaji karyawan berdasarkan nomor karyawan (contoh: `EMP-001`, `EMP-002`) atau ID numerik. Menampilkan status pembayaran apakah sudah dibayar atau belum (`is_paid`, `status_bayar`, dan `tanggal_bayar`).",
                    "parameters": [
                        {
                            "name": "employee_id",
                            "in": "path",
                            "required": True,
                            "description": "Nomor Karyawan (contoh: EMP-002) atau ID internal",
                            "schema": {"type": "string", "example": "EMP-002"}
                        },
                        {
                            "name": "bulan",
                            "in": "query",
                            "required": False,
                            "description": "Filter bulan periode gaji (1 - 12)",
                            "schema": {"type": "integer", "minimum": 1, "maximum": 12, "example": 11}
                        },
                        {
                            "name": "tahun",
                            "in": "query",
                            "required": False,
                            "description": "Filter tahun periode gaji",
                            "schema": {"type": "integer", "example": 2026}
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "required": False,
                            "description": "Filter status pembayaran (SUDAH_DIBAYAR / BELUM_DIBAYAR / ALL)",
                            "schema": {
                                "type": "string",
                                "enum": ["SUDAH_DIBAYAR", "BELUM_DIBAYAR", "ALL"],
                                "example": "SUDAH_DIBAYAR"
                            }
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "description": "Batas jumlah slip yang dikembalikan (default 100)",
                            "schema": {"type": "integer", "default": 100, "example": 50}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Berhasil mengambil riwayat payroll",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean", "example": True},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "employee": {"$ref": "#/components/schemas/Employee"},
                                                    "summary": {"$ref": "#/components/schemas/PayrollSummary"},
                                                    "payrolls": {
                                                        "type": "array",
                                                        "items": {"$ref": "#/components/schemas/PayrollRecord"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            }
                        },
                        "404": {
                            "description": "Karyawan tidak ditemukan",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            }
                        }
                    }
                }
            },
            "/payroll/slip/{payroll_id}": {
                "get": {
                    "tags": ["Payroll & Slip Gaji"],
                    "summary": "Ambil Detail 1 Slip Gaji Spesifik",
                    "description": "Mengambil rincian breakdown lengkap satu slip gaji berdasarkan ID payroll.",
                    "parameters": [
                        {
                            "name": "payroll_id",
                            "in": "path",
                            "required": True,
                            "description": "ID Payroll unik",
                            "schema": {"type": "integer", "example": 1}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Detail slip gaji",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean", "example": True},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "employee": {"$ref": "#/components/schemas/Employee"},
                                                    "slip": {"$ref": "#/components/schemas/PayrollRecord"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            }
                        },
                        "404": {
                            "description": "Slip gaji tidak ditemukan",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }

# ---------- API Endpoints ----------

@external_api_bp.route('/openapi.json', methods=['GET', 'OPTIONS'])
def openapi_json():
    """Mengembalikan spesifikasi OpenAPI 3.0.3 resmi dalam format JSON."""
    if request.method == 'OPTIONS':
        resp = make_response('', 204)
        return _apply_cors_headers(resp)
    resp = jsonify(get_openapi_spec())
    return _apply_cors_headers(resp)

@external_api_bp.route('/docs', methods=['GET'])
def api_docs():
    """Halaman interaktif Swagger UI."""
    return render_template('swagger_ui.html')

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
        # Cari karyawan berdasarkan no_karyawan (case-insensitive), id numerik, atau nama
        k = conn.execute("""
            SELECT id, no_karyawan, nama, jabatan, status_kerja, status_pajak, npwp, aktif
            FROM karyawan
            WHERE LOWER(TRIM(no_karyawan)) = LOWER(TRIM(?))
               OR (CAST(? AS INTEGER) > 0 AND id = CAST(? AS INTEGER))
               OR LOWER(TRIM(nama)) = LOWER(TRIM(?))
            LIMIT 1
        """, (clean_id, clean_id, clean_id, clean_id)).fetchone()

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


def push_payroll_to_sicare(payroll_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Mengirimkan (HTTP POST Webhook) data slip gaji dari Finance ERP langsung ke siCare HRMS.
    Dipanggil otomatis saat:
    1. Bayar Karyawan di Finance ERP (/gaji/<pid>/bayar)
    2. Proses Gaji Karyawan (/gaji/proses)
    3. Cetak Slip Gaji (/gaji/<pid>/slip/cetak)
    """
    import json
    import urllib.request
    import urllib.error
    import ssl
    from datetime import date

    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        query = """
            SELECT p.*, k.no_karyawan, k.nama AS nama_karyawan, k.jabatan
            FROM payroll p
            JOIN karyawan k ON k.id = p.karyawan_id
            WHERE p.id = ?
        """
        row = conn.execute(query, (payroll_id,)).fetchone()
        if not row:
            return {'success': False, 'message': f'Payroll ID {payroll_id} tidak ditemukan.'}

        # HANYA kirim ke siCare jika status_bayar sudah SUDAH_DIBAYAR!
        if (row['status_bayar'] or '').upper() != 'SUDAH_DIBAYAR':
            return {'success': False, 'message': 'Payroll belum dibayar di rekening, slip tidak dikirim ke siCare.'}

        webhook_url = os.environ.get('SICARE_WEBHOOK_URL', 'https://karir.faishalnafi.com/api/v1/webhook/payroll-payment')
        api_key = get_or_create_external_api_key(conn)

        payload = {
            'event': 'payroll.payment_pushed',
            'payroll_id': row['id'],
            'no_karyawan': row['no_karyawan'] or '',
            'karyawan_nama': row['nama_karyawan'] or '',
            'periode_bulan': row['periode_bulan'],
            'periode_tahun': row['periode_tahun'],
            'gaji_pokok': float(row['gaji_pokok'] or 0),
            'tunjangan': float(row['tunjangan'] or 0),
            'uang_transport': float(row['uang_transport'] or 0),
            'uang_makan': float(row['uang_makan'] or 0),
            'bonus': float(row['bonus'] or 0),
            'lain_lain': float(row['lain_lain'] or 0),
            'bpjs_ketenagakerjaan': float(row['bpjs_tk_kar'] or 0),
            'bpjs_kesehatan': float(row['bpjs_kes_kar'] or 0),
            'pph21': float(row['pph21'] or 0),
            'take_home_pay': float(row['gaji_bersih'] or 0),
            'status_bayar': row['status_bayar'] or 'SUDAH_DIBAYAR',
            'tanggal_bayar': row['tanggal_bayar'] or date.today().isoformat(),
            'catatan': row['catatan'] or ''
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'X-API-KEY': api_key,
                'User-Agent': 'FinanceERP-Payroll-Webhook/1.0'
            },
            method='POST'
        )

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                resp_body = resp.read().decode('utf-8')
                result = json.loads(resp_body) if resp_body else {}
                return {'success': True, 'response': result}
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode('utf-8', errors='ignore')
            return {'success': False, 'status_code': http_err.code, 'error': err_body}
        except Exception as net_err:
            return {'success': False, 'error': str(net_err)}

    finally:
        if close_after:
            conn.close()


def cancel_payroll_in_sicare(payroll_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Mengirimkan webhook pembatalan bayar ke siCare HRMS agar slip yang dibatalkan dihapus dari siCare.
    """
    import json
    import urllib.request
    import urllib.error
    import ssl

    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        query = """
            SELECT p.*, k.no_karyawan, k.nama AS nama_karyawan
            FROM payroll p
            JOIN karyawan k ON k.id = p.karyawan_id
            WHERE p.id = ?
        """
        row = conn.execute(query, (payroll_id,)).fetchone()
        if not row:
            return {'success': False, 'message': f'Payroll ID {payroll_id} tidak ditemukan.'}

        webhook_url = os.environ.get('SICARE_WEBHOOK_URL', 'https://karir.faishalnafi.com/api/v1/webhook/payroll-payment')
        api_key = get_or_create_external_api_key(conn)

        payload = {
            'event': 'payroll.payment_cancelled',
            'payroll_id': row['id'],
            'no_karyawan': row['no_karyawan'] or '',
            'karyawan_nama': row['nama_karyawan'] or '',
            'periode_bulan': row['periode_bulan'],
            'periode_tahun': row['periode_tahun'],
            'status_bayar': 'BELUM_DIBAYAR'
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'X-API-KEY': api_key,
                'User-Agent': 'FinanceERP-Payroll-Webhook/1.0'
            },
            method='POST'
        )

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                resp_body = resp.read().decode('utf-8')
                result = json.loads(resp_body) if resp_body else {}
                return {'success': True, 'response': result}
        except Exception as net_err:
            return {'success': False, 'error': str(net_err)}
    finally:
        if close_after:
            conn.close()
