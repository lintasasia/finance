/* Printer struk POS, diatur per perangkat (tablet / HP / komputer kasir).
 *
 * Tiga cara mencetak, disimpan di browser perangkat ini (bukan di server), karena
 * printer Bluetooth tersambung ke perangkat, bukan ke usaha:
 *   dialog    : jendela cetak browser (window.print), sama seperti sebelumnya. Bawaan.
 *   bluetooth : langsung ke printer thermal lewat Web Bluetooth (Chrome / Edge), printer BLE.
 *   rawbt     : diteruskan ke aplikasi RawBT di Android, untuk printer Bluetooth biasa (Classic)
 *               yang tidak bisa dijangkau browser.
 * Isi struk untuk bluetooth & rawbt berupa perintah ESC/POS yang dibuat server
 * (/pos/struk/<id>/escpos), jadi isinya sama dengan struk di layar.
 *
 * KENAPA ADA BINGKAI /pos/app: sambungan Bluetooth hilang setiap kali halaman berganti, dan
 * browser hanya mengizinkan menyambung ulang lewat daftar pilih printer yang harus diketuk
 * (navigator.bluetooth.getDevices yang bisa mengambil printer lama tanpa memilih belum
 * aktif di Chrome). Padahal kasir berganti halaman tiap transaksi (kasir -> struk -> kasir).
 * Jadi saat memakai Bluetooth langsung, layar kasir dibuka di dalam bingkai /pos/app. Halaman
 * bingkai itu tidak pernah berganti dan memegang sambungan printer; halaman kasir & struk di
 * dalamnya meminjam sambungan itu lewat window.top.PosPrinter (INDUK di bawah). Hasilnya
 * printer cukup dipilih sekali per sesi, lalu setiap struk langsung tercetak.
 *
 * Sengaja ES5 (tanpa async, arrow, let/const): file ini juga dimuat di browser Android lama.
 * Kalau browser tidak mengenal sesuatu, fiturnya saja yang tidak tersedia, halaman tetap jalan.
 */
(function (w, d) {
  'use strict';

  var KUNCI = 'finansial_pos_printer_v1';
  // Web Bluetooth hanya boleh membuka layanan yang disebut di sini. Daftar ini layanan
  // yang umum dipakai printer thermal ESC/POS murah (Xprinter, Zjiang, Goojprt, dsb).
  var LAYANAN = [
    '000018f0-0000-1000-8000-00805f9b34fb',
    'e7810a71-73ae-499d-8c15-faa9aef0c3f2',
    '49535343-fe7d-4ae5-8fa9-9fafd205e455',
    '0000ff00-0000-1000-8000-00805f9b34fb',
    '0000ffe0-0000-1000-8000-00805f9b34fb',
    '0000fee7-0000-1000-8000-00805f9b34fb',
    '0000ae30-0000-1000-8000-00805f9b34fb'
  ];
  // Saluran tulis yang dikenal di layanan-layanan itu. Kalau tidak ada, dipakai saluran
  // tulis pertama yang ditemukan.
  var SALURAN = [
    '00002af1-0000-1000-8000-00805f9b34fb',
    'bef8d6c9-9c21-4c9e-b632-bd58c1009f9f',
    '49535343-8841-43f4-a8d4-ecbe34729bb3',
    '0000ff02-0000-1000-8000-00805f9b34fb',
    '0000ffe1-0000-1000-8000-00805f9b34fb',
    '0000ae01-0000-1000-8000-00805f9b34fb'
  ];
  var METODE = ['dialog', 'bluetooth', 'rawbt'];

  // Bingkai kasir (halaman induk) kalau halaman ini dibuka di dalamnya.
  var INDUK = null;
  try {
    if (w.top !== w && w.top.PosPrinter && w.top.PosPrinter.adalahInduk) INDUK = w.top.PosPrinter;
  } catch (e) { INDUK = null; }

  function bawaan() {
    return {metode: 'dialog', kolom: 'auto', otomatis: false, otomatisDiatur: false, btId: '', btNama: ''};
  }

  // null kalau penyimpanan browser tidak bisa dibaca (mode privat, diblokir).
  function baca() {
    var s;
    try { s = w.localStorage.getItem(KUNCI); } catch (e) { return null; }
    var c = bawaan(), o = null;
    try { o = JSON.parse(s || 'null'); } catch (e) { o = null; }
    if (o && typeof o === 'object') {
      for (var k in c) { if (Object.prototype.hasOwnProperty.call(o, k)) c[k] = o[k]; }
    }
    if (METODE.indexOf(c.metode) < 0) c.metode = 'dialog';
    return c;
  }

  function simpan() {
    try { w.localStorage.setItem(KUNCI, JSON.stringify(P.cfg)); } catch (e) { /* mode privat: tetap jalan */ }
  }

  // Setelan bisa diubah di halaman lain (mis. modal di dalam bingkai), jadi dibaca ulang
  // sebelum dipakai. Kalau penyimpanan tidak bisa dibaca, salinan di memori yang dipakai.
  function segar() {
    var c = baca();
    if (c) P.cfg = c;
    return P.cfg;
  }

  function el(id) { return d.getElementById(id); }

  var P = {
    cfg: baca() || bawaan(),
    kertas: '80',
    jurnalId: null,
    halaman: '',
    adalahInduk: false,
    perangkat: null,
    saluran: null,
    sibuk: false,
    cache: {},
    // Membuka aplikasi lain (RawBT). Dipisah supaya bisa diganti saat pengujian.
    bukaUrl: function (url) { w.location.href = url; }
  };

  P.btDidukung = function () {
    return !!(w.navigator && w.navigator.bluetooth && w.isSecureContext);
  };

  P.kolom = function () {
    var k = parseInt(P.cfg.kolom, 10);
    if (k === 32 || k === 42 || k === 48) return k;
    return P.kertas === '58' ? 32 : 48;
  };

  P.tersambung = function () {
    if (INDUK) return INDUK.tersambung();
    return !!(P.saluran && P.perangkat && P.perangkat.gatt && P.perangkat.gatt.connected);
  };

  // Dokumen yang ikut diperbarui: halaman ini + halaman di dalam bingkai (kalau ini induk).
  function semuaDokumen() {
    var out = [{doc: d, win: w}];
    if (P.adalahInduk) {
      var fr = d.querySelectorAll('iframe');
      for (var i = 0; i < fr.length; i++) {
        try { if (fr[i].contentDocument) out.push({doc: fr[i].contentDocument, win: fr[i].contentWindow}); } catch (e) { /* lain asal */ }
      }
    }
    return out;
  }

  // ── Pesan status (halaman struk & modal printer) ────────────────────────────
  P.status = function (teks, jenis) {
    if (INDUK) return INDUK.status(teks, jenis);
    var ds = semuaDokumen();
    for (var n = 0; n < ds.length; n++) {
      var ids = ['printerStatus', 'prnStatus'];
      for (var i = 0; i < ids.length; i++) {
        var e = ds[n].doc.getElementById(ids[i]);
        if (!e) continue;
        e.textContent = teks || '';
        e.className = (ids[i] === 'prnStatus' ? 'prn-status' : 'prn-status-struk') + (jenis ? ' ' + jenis : '');
        e.style.display = teks ? '' : 'none';
      }
    }
  };

  P.segarkanSemua = function () {
    if (INDUK) return INDUK.segarkanSemua();
    var ds = semuaDokumen();
    for (var n = 0; n < ds.length; n++) {
      try { if (ds[n].win.PosPrinter) ds[n].win.PosPrinter.segarkanModal(); } catch (e) { /* abaikan */ }
    }
  };

  // ── Data struk ESC/POS dari server ──────────────────────────────────────────
  function ambil(url) {
    if (P.cache[url]) return P.cache[url];
    var janji = w.fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}})
      .then(function (r) {
        if (r.redirected) throw new Error('Sesi kasir sudah berakhir. Muat ulang halaman lalu masuk lagi.');
        return r.json().then(function (j) { return j; }, function () { return {}; }).then(function (j) {
          if (!r.ok || !j || !j.data) throw new Error((j && j.error) || ('Server menolak permintaan (kode ' + r.status + ').'));
          return j;
        });
      });
    P.cache[url] = janji;
    janji.then(null, function () { delete P.cache[url]; });
    return janji;
  }

  function keBytes(b64) {
    var s = w.atob(b64), a = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
    return a;
  }

  P.urlStruk = function (jid) { return '/pos/struk/' + jid + '/escpos?kolom=' + P.kolom(); };
  P.urlTes = function () { return '/pos/printer/tes?kolom=' + P.kolom(); };

  // ── Bluetooth ────────────────────────────────────────────────────────────────
  function urutan(uuid) { var n = LAYANAN.indexOf(uuid); return n < 0 ? 99 : n; }

  function bisaTulis(k) { return k.properties && (k.properties.write || k.properties.writeWithoutResponse); }

  function cariSaluran(server) {
    return server.getPrimaryServices().then(null, function () { return []; }).then(function (layanan) {
      var antre = layanan.slice().sort(function (a, b) { return urutan(a.uuid) - urutan(b.uuid); });
      var i = 0;
      function coba() {
        if (i >= antre.length) {
          throw new Error('Printer tersambung, tetapi tidak menyediakan jalur untuk menerima struk. ' +
                          'Kemungkinan printer ini hanya Bluetooth biasa (bukan BLE): pakai cara RawBT.');
        }
        var l = antre[i++];
        return l.getCharacteristics().then(function (ks) {
          var pilih = null, j;
          for (j = 0; j < ks.length && !pilih; j++) { if (SALURAN.indexOf(ks[j].uuid) >= 0 && bisaTulis(ks[j])) pilih = ks[j]; }
          for (j = 0; j < ks.length && !pilih; j++) { if (bisaTulis(ks[j])) pilih = ks[j]; }
          return pilih || coba();
        }, coba);
      }
      return coba();
    });
  }

  function sambung(dev) {
    P.perangkat = dev;
    if (!dev._pantauFinansial) {
      dev._pantauFinansial = true;
      dev.addEventListener('gattserverdisconnected', function () { P.saluran = null; P.segarkanSemua(); });
    }
    return dev.gatt.connect().then(cariSaluran).then(function (k) { P.saluran = k; P.segarkanSemua(); return k; });
  }

  // Membuka daftar pilih printer. Hanya boleh tepat setelah orang menekan tombol.
  P.mintaPrinter = function () {
    if (INDUK) return INDUK.mintaPrinter();
    segar();
    return w.navigator.bluetooth.requestDevice({acceptAllDevices: true, optionalServices: LAYANAN})
      .then(function (dev) {
        P.cfg.btId = dev.id;
        P.cfg.btNama = dev.name || 'Printer Bluetooth';
        simpan();
        P.saluran = null;
        return sambung(dev);
      });
  };

  P.lupakan = function () {
    if (INDUK) return INDUK.lupakan();
    try { if (P.perangkat && P.perangkat.gatt.connected) P.perangkat.gatt.disconnect(); } catch (e) { /* abaikan */ }
    P.perangkat = null; P.saluran = null;
    segar();
    P.cfg.btId = ''; P.cfg.btNama = '';
    simpan();
    P.segarkanSemua();
  };

  function perluKetuk(pesan) {
    var e = new Error(pesan);
    e.perluKetuk = true;
    return e;
  }

  // bolehMinta = boleh membuka daftar pilih printer (hanya setelah tombol ditekan; cetak
  // otomatis tidak boleh memakainya).
  function siapkanPrinter(bolehMinta) {
    if (P.saluran && P.perangkat && P.perangkat.gatt && P.perangkat.gatt.connected) return Promise.resolve(P.saluran);
    if (P.perangkat) {
      // Printer sudah dipilih di sesi ini: sambung ulang tanpa daftar pilih.
      return sambung(P.perangkat).then(null, function () {
        if (bolehMinta) return P.mintaPrinter();
        throw perluKetuk('Printer belum tersambung. Pastikan printer menyala, lalu tekan Cetak.');
      });
    }
    var bt = w.navigator.bluetooth;
    // Kalau browser mendukung, printer yang pernah diizinkan diambil lagi tanpa memilih ulang.
    var cari = (P.cfg.btId && bt.getDevices)
      ? bt.getDevices().then(function (daftar) {
          for (var i = 0; i < daftar.length; i++) { if (daftar[i].id === P.cfg.btId) return daftar[i]; }
          return null;
        }, function () { return null; })
      : Promise.resolve(null);
    return cari.then(function (dev) {
      if (dev) {
        return sambung(dev).then(null, function () {
          if (bolehMinta) return P.mintaPrinter();
          throw perluKetuk('Printer belum tersambung. Pastikan printer menyala, lalu tekan Cetak.');
        });
      }
      if (bolehMinta) return P.mintaPrinter();
      throw perluKetuk(P.cfg.btNama
        ? 'Printer belum tersambung. Tekan Cetak lalu pilih ' + P.cfg.btNama + '.'
        : 'Belum ada printer Bluetooth. Tekan Cetak lalu pilih printernya.');
    });
  }

  function tunda(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // Data dikirim per potongan. Jalur "dengan balasan" dicoba 180 byte per potongan; kalau
  // printer menolak, turun ke 20 byte (ukuran yang pasti diterima semua printer BLE).
  // Jalur "tanpa balasan" selalu 20 byte dengan jeda kecil supaya penampung printer tidak luber.
  function kirimBytes(k, data) {
    var balas = !!k.properties.write;
    var ukuran = balas ? 180 : 20;
    var pos = 0;
    function satu() {
      if (pos >= data.length) return Promise.resolve();
      var potong = data.slice(pos, pos + ukuran);
      var janji;
      if (balas) janji = k.writeValueWithResponse ? k.writeValueWithResponse(potong) : k.writeValue(potong);
      else janji = k.writeValueWithoutResponse ? k.writeValueWithoutResponse(potong) : k.writeValue(potong);
      return janji.then(function () {
        pos += potong.length;
        return balas ? null : tunda(15);
      }, function (e) {
        if (ukuran > 20) { ukuran = 20; return null; }
        throw e;
      }).then(satu);
    }
    return satu();
  }

  function pesanGagal(e) {
    if (!e) return 'Gagal mencetak.';
    if (e.perluKetuk) return e.message;
    if (e.name === 'NotFoundError' && /cancel/i.test(e.message || '')) return 'Pemilihan printer dibatalkan.';
    if (e.name === 'NotFoundError') return 'Printer tidak ditemukan. Pastikan printer menyala dan Bluetooth perangkat aktif.';
    if (e.name === 'SecurityError') return 'Browser menolak membuka Bluetooth. Tekan Cetak sekali lagi.';
    if (e.name === 'NetworkError') return 'Sambungan ke printer terputus. Dekatkan printer lalu tekan Cetak lagi.';
    return 'Gagal mencetak: ' + (e.message || e);
  }
  P.pesanGagal = pesanGagal;

  // ── Kirim ke printer sesuai metode ──────────────────────────────────────────
  P.kirim = function (url, bolehMinta) {
    if (INDUK) return INDUK.kirim(url, bolehMinta);
    var m = segar().metode;
    if (m === 'rawbt') {
      P.status('Menyiapkan struk...', 'proses');
      return ambil(url).then(function (j) {
        P.bukaUrl('intent:base64,' + j.data + '#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;');
        P.status('Struk dikirim ke aplikasi RawBT. Kalau Play Store yang terbuka, pasang RawBT dulu.', 'ok');
      }, function (e) { P.status(pesanGagal(e), 'galat'); });
    }
    if (!P.btDidukung()) {
      P.status('Browser ini belum bisa menyambung printer Bluetooth. Pakai Chrome atau Edge, atau pilih cara lain di Printer.', 'galat');
      return Promise.resolve();
    }
    if (P.sibuk) return Promise.resolve();
    P.sibuk = true;
    P.status('Menyambung printer...', 'proses');
    // Sambung dulu, baru ambil data: daftar pilih printer harus muncul selagi izin dari
    // tekanan tombol masih berlaku.
    return siapkanPrinter(bolehMinta).then(function (k) {
      P.status('Mengirim struk ke ' + (P.cfg.btNama || 'printer') + '...', 'proses');
      return ambil(url).then(function (j) { return kirimBytes(k, keBytes(j.data)); });
    }).then(function () {
      P.sibuk = false;
      P.status('Struk terkirim ke ' + (P.cfg.btNama || 'printer') + '.', 'ok');
    }, function (e) {
      P.sibuk = false;
      P.status(pesanGagal(e), e && e.perluKetuk ? 'proses' : 'galat');
    });
  };

  P.cetak = function (jid, opsi) {
    opsi = opsi || {};
    jid = jid || P.jurnalId;
    segar();
    // Jendela cetak selalu dari halaman ini sendiri, supaya yang tercetak struknya, bukan bingkai.
    if (P.cfg.metode === 'dialog' || !jid) { w.print(); return Promise.resolve(); }
    return P.kirim(P.urlStruk(jid), !opsi.otomatis);
  };

  P.tes = function () {
    if (segar().metode === 'dialog') return Promise.resolve();
    return P.kirim(P.urlTes(), true);
  };

  // ── Pasang sebagai aplikasi (PWA) ───────────────────────────────────────────
  var tawaranPasang = null;
  w.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    tawaranPasang = e;
    P.segarkanSemua();
  });
  w.addEventListener('appinstalled', function () { tawaranPasang = null; P.segarkanSemua(); });

  P.bisaPasang = function () { return INDUK ? INDUK.bisaPasang() : !!tawaranPasang; };

  P.terpasang = function () {
    if (INDUK) return INDUK.terpasang();
    return (w.matchMedia && w.matchMedia('(display-mode: standalone)').matches) || w.navigator.standalone === true;
  };

  P.pasang = function () {
    if (INDUK) return INDUK.pasang();
    if (!tawaranPasang) return;
    var t = tawaranPasang;
    tawaranPasang = null;
    t.prompt();
    if (t.userChoice) t.userChoice.then(P.segarkanSemua, P.segarkanSemua);
  };

  // ── Bingkai kasir untuk Bluetooth langsung ───────────────────────────────────
  // Layar kasir dengan cara cetak Bluetooth dipindah ke dalam bingkai /pos/app, supaya
  // sambungan printer tidak putus setiap ganti halaman.
  P.perluBingkai = function () {
    return P.halaman === 'kasir' && !INDUK && w.top === w && segar().metode === 'bluetooth' && P.btDidukung();
  };
  P.masukBingkai = function () {
    if (P.perluBingkai()) { w.location.replace('/pos/app'); return true; }
    return false;
  };

  // ── Modal "Printer struk" ───────────────────────────────────────────────────
  P.segarkanModal = function () {
    var m = el('printerModal');
    segar();
    var tombolAtas = el('btnPrinterAtas');
    if (tombolAtas) {
      var belum = P.cfg.metode === 'bluetooth' && !P.tersambung();
      var teksAtas = tombolAtas.querySelector('.prn-teks');
      tombolAtas.className = 'cb-pill' + (belum ? ' prn-belum' : '');
      tombolAtas.setAttribute('aria-label', belum ? 'Sambungkan printer' : 'Printer');
      if (teksAtas) teksAtas.textContent = belum ? 'Sambungkan printer' : 'Printer';
    }
    if (!m) return;
    var metode = P.cfg.metode;
    var radio = m.querySelectorAll('input[name="prnMetode"]');
    for (var i = 0; i < radio.length; i++) {
      radio[i].checked = radio[i].value === metode;
      var kartu = radio[i].parentNode;
      if (kartu && kartu.className.indexOf('prn-opsi') >= 0) kartu.className = 'prn-opsi' + (radio[i].checked ? ' aktif' : '');
    }
    var sambungan = P.tersambung();
    var bt = el('prnBagianBt');
    if (bt) bt.style.display = metode === 'bluetooth' ? '' : 'none';
    var tak = el('prnBtTakDidukung');
    if (tak) tak.style.display = P.btDidukung() ? 'none' : '';
    var cari = el('prnBtCari'), lupa = el('prnBtLupa');
    if (cari) {
      cari.disabled = !P.btDidukung();
      cari.textContent = !P.cfg.btId ? 'Cari printer'
        : (sambungan ? 'Ganti printer' : 'Sambungkan ' + (P.cfg.btNama || 'printer'));
    }
    if (lupa) lupa.style.display = P.cfg.btId ? '' : 'none';
    var nama = el('prnBtNama');
    if (nama) {
      nama.textContent = !P.cfg.btId ? 'Belum ada printer yang dipilih.'
        : (P.cfg.btNama || 'Printer Bluetooth') + (sambungan ? ': tersambung.'
          : ': belum tersambung. Tekan tombol di bawah lalu pilih printer ini. Cukup sekali setiap kasir dibuka.');
    }
    var kolom = el('prnBagianKolom');
    if (kolom) kolom.style.display = metode === 'dialog' ? 'none' : '';
    var sel = el('prnKolom');
    if (sel) sel.value = String(P.cfg.kolom || 'auto');
    var oto = el('prnOtomatis');
    if (oto) oto.checked = !!P.cfg.otomatis;
    var tes = el('prnTes');
    if (tes) tes.style.display = metode === 'dialog' ? 'none' : '';
    var ket = el('prnPasangKet'), tombol = el('prnPasang');
    if (ket) {
      if (P.terpasang()) {
        ket.textContent = 'Kasir sudah terbuka sebagai aplikasi.';
      } else if (P.bisaPasang()) {
        ket.textContent = 'Pasang Kasir POS di layar utama supaya terbuka penuh layar seperti aplikasi, tanpa baris alamat browser.';
      } else if (!w.isSecureContext) {
        ket.textContent = 'Pemasangan sebagai aplikasi butuh alamat https.';
      } else {
        ket.textContent = 'Di Chrome atau Edge: buka menu titik tiga, lalu pilih Instal aplikasi atau Tambahkan ke layar utama. ' +
                          'Di iPad atau iPhone: tombol Bagikan, lalu Tambahkan ke Layar Utama.';
      }
    }
    if (tombol) tombol.style.display = (P.bisaPasang() && !P.terpasang()) ? '' : 'none';
  };

  P.pasangModal = function () {
    var m = el('printerModal');
    if (!m || m._siapFinansial) return;
    m._siapFinansial = true;
    var radio = m.querySelectorAll('input[name="prnMetode"]');
    for (var i = 0; i < radio.length; i++) {
      radio[i].addEventListener('change', function () {
        segar();
        P.cfg.metode = this.value;
        // Pertama kali memilih cetak langsung: cetak otomatis dinyalakan, itu tujuan utamanya.
        if (this.value === 'bluetooth' && !P.cfg.otomatisDiatur) P.cfg.otomatis = true;
        simpan();
        P.status('', '');
        P.segarkanModal();
      });
    }
    var sel = el('prnKolom');
    if (sel) sel.addEventListener('change', function () { segar(); P.cfg.kolom = this.value; simpan(); });
    var oto = el('prnOtomatis');
    if (oto) oto.addEventListener('change', function () { segar(); P.cfg.otomatis = this.checked; P.cfg.otomatisDiatur = true; simpan(); });
    var cari = el('prnBtCari');
    if (cari) cari.addEventListener('click', function () {
      if (!P.btDidukung()) return;
      P.status('Pilih printer di daftar yang muncul...', 'proses');
      P.mintaPrinter().then(function () {
        P.status('Tersambung ke ' + segar().btNama + '. Tekan Tes cetak untuk mencoba.', 'ok');
      }, function (e) { P.status(pesanGagal(e), 'galat'); P.segarkanModal(); });
    });
    var lupa = el('prnBtLupa');
    if (lupa) lupa.addEventListener('click', function () {
      P.lupakan();
      P.status('Printer dilupakan di perangkat ini.', '');
    });
    var tes = el('prnTes');
    if (tes) tes.addEventListener('click', function () { P.tes(); });
    var pasang = el('prnPasang');
    if (pasang) pasang.addEventListener('click', P.pasang);
    m.addEventListener('show.bs.modal', P.segarkanModal);
    // Baru memilih Bluetooth langsung di layar kasir biasa: pindah ke bingkai kasir.
    m.addEventListener('hidden.bs.modal', P.masukBingkai);
    P.segarkanModal();
  };

  // ── Mulai ────────────────────────────────────────────────────────────────────
  // opsi.induk: halaman bingkai /pos/app. opsi.halaman: 'kasir' / 'struk'.
  P.mulai = function (opsi) {
    opsi = opsi || {};
    if (opsi.kertas === '58' || opsi.kertas === '80') P.kertas = opsi.kertas;
    if (opsi.induk) { P.adalahInduk = true; return; }
    P.halaman = opsi.halaman || (opsi.jurnalId ? 'struk' : 'kasir');
    P.jurnalId = opsi.jurnalId || null;
    if (INDUK) INDUK.kertas = P.kertas;
    if (P.masukBingkai()) return;
    P.pasangModal();
    if (!P.jurnalId) return;
    if (P.cfg.metode !== 'dialog' && w.fetch && !INDUK) ambil(P.urlStruk(P.jurnalId));   // siapkan data lebih dulu
    if (!opsi.baru) return;
    // Tanda "baru" dibuang dari alamat supaya memuat ulang halaman tidak mencetak dua kali.
    try { w.history.replaceState(null, '', w.location.pathname); } catch (e) { /* abaikan */ }
    if (!P.cfg.otomatis) return;
    if (P.cfg.metode === 'dialog') {
      var cetakNanti = function () { setTimeout(function () { w.print(); }, 300); };
      if (d.readyState === 'complete') cetakNanti(); else w.addEventListener('load', cetakNanti);
    } else if (P.cfg.metode === 'bluetooth') {
      P.cetak(P.jurnalId, {otomatis: true});
    } else {
      P.status('Tekan Cetak untuk mengirim struk ke RawBT.', 'proses');
    }
  };

  w.PosPrinter = P;
})(window, document);
