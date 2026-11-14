/* Isian PPh lengkap di form transaksi (Penjualan, Pengeluaran, Pembelian, Pembelian PKP, Invoice,
 * Edit Item). Data objek PPh dari server: window.PPH_INFO (lihat pph_info_js di app.py).
 *
 * - Mengganti jenis/peruntukan mengisi tarif bawaannya (bisa diubah lagi) dan kode objek pajak
 *   bila isian kode objek masih kosong atau masih isian otomatis sebelumnya.
 * - Elemen berlabel data-pph-label="<idp>" ikut berganti teks jenis PPh (mis. "PPh 4 ayat (2)").
 * - pphAkun(idp, sisi) memberi "kode - nama akun" untuk pratinjau jurnal.
 *
 * Sengaja ES5 (tanpa arrow/let/const): form ini juga dibuka di browser Android lama.
 */
(function (w, d) {
  'use strict';

  function info(objek) {
    var m = w.PPH_INFO || {};
    return m[objek] || m[''] || {label: 'PPh 23', tarif: 2, kop: '', akun_jual: '1181 - PPh 23 Dibayar Dimuka',
                                 akun_beli: '2112 - Hutang PPh Pasal 23', final: false};
  }

  function setAngka(el, nilai) {
    if (!el) return;
    if (w.numFmtSet && el.getAttribute('data-nf') === '1') {
      w.numFmtSet(el, nilai);
    } else {
      el.value = String(nilai);
    }
  }

  function picu(el) {
    if (!el) return;
    if (typeof el.oninput === 'function') {
      el.oninput.call(el);
      return;
    }
    try { el.dispatchEvent(new Event('input', {bubbles: true})); } catch (e) { /* browser lama */ }
  }

  w.pphInfo = info;

  w.pphObjekDari = function (idp) {
    var sel = d.getElementById((idp || '') + 'pph_objek');
    return sel ? sel.value : '';
  };

  w.pphAkun = function (idp, sisi) {
    var o = info(w.pphObjekDari(idp));
    return sisi === 'BELI' ? o.akun_beli : o.akun_jual;
  };

  w.pphLabel = function (idp) {
    return info(w.pphObjekDari(idp)).label;
  };

  /* PPh final disetor sendiri oleh penjual: centang aktif dan peruntukannya memang bisa disetor sendiri
     (PPh 4 ayat (2) / PPh 15 selain UMKM). Tagihan customer tidak dipotong. */
  w.pphSendiri = function (idp) {
    var cb = d.getElementById((idp || '') + 'pph_sendiri');
    return !!(cb && cb.checked && !cb.disabled && info(w.pphObjekDari(idp)).sendiri);
  };

  /* Akun hutang PPh untuk PPh final yang disetor sendiri, untuk pratinjau jurnal. */
  w.pphAkunHutang = function (idp) {
    return info(w.pphObjekDari(idp)).akun_beli;
  };

  /* Keterangan dampak baris PPh di pratinjau jurnal. */
  w.pphDampak = function (idp, sisi) {
    var o = info(w.pphObjekDari(idp));
    if (sisi === 'BELI') return o.label + ' dipotong, wajib disetor ke kas negara';
    if (w.pphSendiri(idp)) return o.label + ' final disetor sendiri, dicatat sebagai beban';
    return o.final ? o.label + ' final, dicatat sebagai beban (tidak bisa dikreditkan)'
                   : 'Kredit pajak (klaim SPT Tahunan)';
  };

  w.pphSegarkanLabel = function (idp) {
    var o = info(w.pphObjekDari(idp));
    var el = d.querySelectorAll('[data-pph-label="' + (idp || '') + '"]');
    for (var i = 0; i < el.length; i++) el[i].textContent = o.label;
    var fin = d.querySelectorAll('[data-pph-final="' + (idp || '') + '"]');
    for (var j = 0; j < fin.length; j++) fin[j].style.display = o.final ? '' : 'none';
    var ur = d.querySelectorAll('[data-pph-uraian="' + (idp || '') + '"]');
    for (var m = 0; m < ur.length; m++) {
      ur[m].textContent = o.label + ' \u00b7 ' + o.uraian +
        (o.tarif ? ' (bawaan ' + String(o.tarif).replace('.', ',') + '%).' : '.');
    }
    var akun = d.querySelectorAll('[data-pph-akun="' + (idp || '') + '"]');
    for (var k = 0; k < akun.length; k++) {
      akun[k].textContent = akun[k].getAttribute('data-sisi') === 'BELI' ? o.akun_beli : o.akun_jual;
    }
    /* Centang "disetor sendiri" hanya untuk peruntukan yang bisa; pilihan lain melepas centangnya. */
    var kotak = d.querySelectorAll('[data-pph-sendiri-box="' + (idp || '') + '"]');
    for (var b = 0; b < kotak.length; b++) {
      kotak[b].style.display = o.sendiri ? '' : 'none';
      var cek = kotak[b].querySelector('input[type=checkbox]');
      if (cek && !o.sendiri) cek.checked = false;
    }
    var sendiri = w.pphSendiri(idp);
    var aksi = d.querySelectorAll('[data-pph-aksi="' + (idp || '') + '"]');
    for (var a = 0; a < aksi.length; a++) {
      var kata = sendiri ? 'disetor sendiri' : 'dipotong';
      aksi[a].textContent = aksi[a].getAttribute('data-kapital') === '1'
        ? kata.charAt(0).toUpperCase() + kata.slice(1) : kata;
    }
    var tanda = d.querySelectorAll('[data-pph-tanda="' + (idp || '') + '"]');
    for (var t = 0; t < tanda.length; t++) tanda[t].style.display = sendiri ? 'none' : '';
    var teks = d.querySelectorAll('[data-pph-sendiri-teks="' + (idp || '') + '"]');
    for (var x = 0; x < teks.length; x++) teks[x].style.display = sendiri ? '' : 'none';
  };

  w.pphObjekBerubah = function (sel) {
    var o = info(sel.value);
    var idp = sel.getAttribute('data-idp') || '';
    var lama = info(sel.getAttribute('data-sebelum') || '');
    var tarif = d.getElementById(sel.getAttribute('data-tarif') || '');
    if (tarif && !tarif.disabled) {
      setAngka(tarif, o.tarif);
      picu(tarif);
    }
    var kop = d.getElementById(idp + 'pph_kode_objek');
    /* Kode objek diganti kalau masih kosong, isian otomatis, atau sama dengan kode bawaan pilihan
       sebelumnya (mis. terisi dari data tersimpan). Kode yang diketik sendiri dibiarkan. */
    if (kop && (kop.value === '' || kop.getAttribute('data-auto') === '1' || (lama.kop && kop.value === lama.kop))) {
      kop.value = o.kop || '';
      kop.setAttribute('data-auto', o.kop ? '1' : '0');
    }
    sel.setAttribute('data-sebelum', sel.value);
    w.pphSegarkanLabel(idp);
  };

  /* Aktif/nonaktifkan semua isian di dalam kotak pajak (ikut toggle "Tambahkan Fitur Pajak"),
     supaya isian yang tersembunyi tidak ikut terkirim. */
  w.pphSetAktif = function (box, aktif) {
    if (!box) return;
    var el = box.querySelectorAll('input, select, textarea');
    for (var i = 0; i < el.length; i++) el[i].disabled = !aktif;
  };

  /* Buka blok rincian yang sudah berisi (mis. sesudah draf isian dipulihkan). */
  w.pphBukaRincianTerisi = function () {
    var blok = d.querySelectorAll('details.pph-rinci');
    for (var i = 0; i < blok.length; i++) {
      var el = blok[i].querySelectorAll('input, select');
      for (var j = 0; j < el.length; j++) {
        if (String(el[j].value || '').trim() !== '') { blok[i].open = true; break; }
      }
    }
  };

  function mulai() {
    var sel = d.querySelectorAll('select.pph-objek');
    for (var i = 0; i < sel.length; i++) {
      sel[i].setAttribute('data-sebelum', sel[i].value);
      w.pphSegarkanLabel(sel[i].getAttribute('data-idp') || '');
    }
  }
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', mulai); else mulai();
})(window, document);
