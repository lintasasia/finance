# 📊 Lintas Asia - Sistem Informasi Keuangan & Operasional (ERP)

Aplikasi manajemen finansial, akuntansi terpadu, dan operasional bisnis berbasis web yang dirancang khusus untuk ekosistem **Lintas Asia Group**. Mengintegrasikan standar pencatatan akuntansi ganda (*double-entry bookkeeping*), sistem kasir point-of-sales (POS), perpajakan, penggajian (payroll), serta manajemen proyek.

---

## ✨ Fitur Utama

### 1. 💼 Akuntansi & Pembukuan Lengkap (Double-Entry)
* **Jurnal Umum & Transaksi**: Pencatatan transaksi terstandarisasi dengan penomoran otomatis (`TRX-YYYYMM-XXXX`).
* **Bagan Akun (Chart of Accounts)**: Klasifikasi hierarkis Aset, Liabilitas, Ekuitas, Pendapatan, dan Beban.
* **Laporan Finansial Real-time**:
  * Neraca (*Balance Sheet*)
  * Laba Rugi (*Profit & Loss*)
  * Laporan Arus Kas (*Cash Flow Statement*)
  * Laporan Perubahan Ekuitas
  * Buku Besar & Neraca Saldo
* **Analisis Rasio Keuangan**: Likuiditas, solvabilitas, dan profitabilitas usaha.

### 2. 🧾 Penjualan, Pembelian & Tagihan (Invoicing)
* **Manajemen Invoice**: Pembuatan invoice profesional lengkap dengan logo, nomor rekening bank, QR, dan stempel digital.
* **Tracker Piutang & Hutang**: Pemantauan jatuh tempo tagihan, riwayat angsuran, dan pelunasan bertahap.
* **Purchase Order (PO)**: Penerbitan dan pencatatan dokumen pesanan pembelian ke vendor/pemasok.

### 3. 🛒 Point of Sale (POS) Kasir
* Antarmuka kasir cepat dan responsif dengan dukungan layar sentuh.
* Manajemen shift kasir dan rekonsiliasi kas buka/tutup laci.
* Cetak struk belanja otomatis (format thermal 58mm & 80mm).
* Manajemen diskon, voucher, dan program loyalitas pelanggan.

### 4. 👥 Manajemen Penggajian (Payroll) & Karyawan
* Perhitungan gaji pokok, lembur, tunjangan, dan potongan pph21 secara otomatis.
* Integrasi potongan BPJS Ketenagakerjaan & BPJS Kesehatan.
* Cetak slip gaji resmi format A4 dan struk thermal.

### 5. 📦 Inventaris, Stok & Biaya Produksi (HPP)
* Pelacakan pergerakan stok barang masuk, keluar, dan penyesuaian (*stock opname*).
* Perhitungan HPP dinamis menggunakan metode rata-rata (*moving average*).
* Template bill of materials (BOM) untuk alur produksi bahan baku menjadi barang jadi.

### 6. 🏛️ Kepatuhan Pajak (Tax Hub)
* Rekapitulasi PPh 21, PPh 22, PPh 23, PPh Final UMKM, dan PPN.
* Penerbitan bukti potong pajak dan rekapitulasi data SPT Masa.

### 7. 🔐 Keamanan & Integrasi Sistem
* **Single Sign-On (SSO)**: Integrasi login dengan Google OAuth 2.0.
* **Role-Based Access Control (RBAC)**: Pembagian hak akses terperinci (Admin, Finance, Kasir, Viewer).
* **Audit Trail**: Pencatatan log aktivitas sistem untuk transparansi audit.
* **Progressive Web App (PWA)**: Dapat diinstal langsung di perangkat mobile & tablet.

---

## 🛠️ Tech Stack

* **Backend**: Python 3.12, Flask, WSGI (Gunicorn / uWSGI)
* **Database**: SQLite3 (Optimized with WAL mode & automated integrity checks)
* **Frontend**: HTML5, Jinja2 Templates, Bootstrap 5, JavaScript (ES6+), FontAwesome Icons
* **Deployment**: Nginx Reverse Proxy, AlmaLinux Enterprise Server

---

## 🚀 Panduan Menjalankan Proyek

### 1. Prasyarat Sistem
* Python 3.10+
* Virtualenv

### 2. Instalasi & Setup Lokal
```bash
# Clone repositori
git clone https://github.com/lintasasia/finance.git
cd finance

# Siapkan virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependensi
pip install -r requirements.txt

# Inisialisasi basis data
python3 -c "from app import db; db().close()"

# Jalankan server development
flask run --host=0.0.0.0 --port=5000
```

---

## 🏢 Kepemilikan & Hak Cipta

Dikelola dan dikembangkan oleh Tim Pengembang **Lintas Asia Group**.  
Hak Cipta © 2026 **Lintas Asia Group**. Seluruh hak cipta dilindungi undang-undang.
