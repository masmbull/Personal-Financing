/* Finance app - vanilla JS helpers */
(function () {
  'use strict';

  /* ---------- Theme ---------- */
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
    try { localStorage.setItem('theme', theme); } catch (e) {}
  }
  window.toggleTheme = function () {
    var btn = document.querySelector('.theme-toggle');
    if (btn) { btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin'); }
    applyTheme(document.documentElement.getAttribute('data-theme') === 'dark'
      ? 'light' : 'dark');
  };
  try {
    var saved = localStorage.getItem('theme');
    if (saved) applyTheme(saved);
    else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
      applyTheme('dark');
  } catch (e) {}

  /* ---------- Toast ---------- */
  var toastTimer = null;
  window.showToast = function (message, ok) {
    var c = document.getElementById('toast-container');
    if (!c) return;
    var t = document.createElement('div');
    t.className = 'toast toast-' + (ok === false ? 'error' : 'success');
    t.setAttribute('role', 'status');
    t.textContent = message;
    c.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.remove(); }, 3200);
  };

  /* ---------- Net worth chart (SVG, no libraries) ---------- */
  function fmtShort(n) {
    var abs = Math.abs(n);
    if (abs >= 1e9) return 'Rp' + (n / 1e9).toFixed(1).replace('.', ',') + 'M';
    if (abs >= 1e6) return 'Rp' + (n / 1e6).toFixed(1).replace('.', ',') + 'jt';
    if (abs >= 1e3) return 'Rp' + Math.round(n / 1e3) + 'rb';
    return 'Rp' + n;
  }

  function renderNetWorthChart(data) {
    var svg = document.getElementById('nw-chart');
    var empty = document.getElementById('nw-empty');
    var deltaEl = document.getElementById('nw-delta');
    var sk = document.getElementById('nw-skeleton');
    if (sk) sk.remove();
    if (!svg || !empty) return;

    var pts = (data.points || []).slice(-14);
    if (pts.length < 2) { empty.classList.remove('hidden'); return; }

    empty.classList.add('hidden');
    svg.classList.remove('hidden');

    var vals = pts.map(function (p) { return p.net_worth; });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    if (max === min) { max += 1; min -= 1; }
    var W = 320, H = 140, padX = 6, padY = 18;
    var step = (W - padX * 2) / (pts.length - 1);
    function x(i) { return padX + i * step; }
    function y(v) { return padY + (H - padY * 2) * (1 - (v - min) / (max - min)); }

    var line = pts.map(function (p, i) {
      return x(i).toFixed(1) + ',' + y(p.net_worth).toFixed(1);
    }).join(' ');
    var area = 'M' + line.split(' ').join(' L') +
               ' L' + x(pts.length - 1).toFixed(1) + ',' + (H - 2) +
               ' L' + x(0).toFixed(1) + ',' + (H - 2) + ' Z';

    var rising = vals[vals.length - 1] >= vals[0];
    var stroke = rising ? '#10b981' : '#ef4444';
    var ns = 'http://www.w3.org/2000/svg';
    svg.innerHTML = '';
    function el(name, attrs, txt) {
      var n = document.createElementNS(ns, name);
      for (var k in attrs) n.setAttribute(k, attrs[k]);
      if (txt) n.textContent = txt;
      svg.appendChild(n); return n;
    }
    el('path', { d: area, fill: stroke, opacity: '0.12' });
    el('path', { d: 'M' + line, fill: 'none', stroke: stroke, 'stroke-width': '2.5',
                 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    el('circle', { cx: x(pts.length - 1), cy: y(vals[vals.length - 1]), r: '4',
                   fill: stroke });
    el('text', { x: padX, y: H - 3, 'font-size': '9', fill: '#9ca3af',
                 'text-anchor': 'start' }, fmtShort(min));
    el('text', { x: W - padX, y: H - 3, 'font-size': '9', fill: '#9ca3af',
                 'text-anchor': 'end' }, fmtShort(max));

    if (deltaEl) {
      var diff = vals[vals.length - 1] - vals[0];
      deltaEl.hidden = false;
      deltaEl.className = 'badge ' + (diff >= 0 ? 'badge-green' : 'badge-red');
      deltaEl.textContent = (diff >= 0 ? '▲ +' : '▼ −') + fmtShort(Math.abs(diff)) +
                            ' periode ini';
    }
  }

  function initNetWorthChart() {
    var wrap = document.getElementById('nw-chart-wrap');
    if (!wrap) return;
    fetch(wrap.dataset.historyUrl, { headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : { points: [] }; })
      .then(renderNetWorthChart)
      .catch(function () {
        var e = document.getElementById('nw-empty');
        if (e) e.classList.remove('hidden');
        var sk = document.getElementById('nw-skeleton');
        if (sk) sk.remove();
      });
  }
  /* ---------- Receipt upload preview / validation ---------- */
  function initReceiptUpload() {
    var input = document.getElementById('file-input');
    var zone = document.getElementById('upload-zone');
    var form = document.getElementById('receipt-form');
    if (!input || !form) return;

    var maxMb = parseInt(form.dataset.maxMb || '3', 10);

    // ---- client-side image compression ----
    // Production reality: a 50 MP Android camera can produce a 10-20 MB JPEG.
    // Uploading that on slow mobile (3G/4G) easily exceeds Cloudflare's
    // 100-second free-tier read timeout and the browser shows
    // ERR_CONNECTION_ABORTED.  Solution: resize + re-encode in the browser
    // BEFORE the upload so the body is small (typically 200-500 KB) and the
    // request finishes in a few seconds on any connection.  Server-side
    // validation still runs (defence in depth); we never send garbage that
    // can't be decoded.
    var _COMPRESS_MAX_WIDTH = 1600;     // ~1280-1600 keeps OCR-grade text legibility
    var _COMPRESS_QUALITY = 0.82;
    var _COMPRESS_MIN_BYTES = 50 * 1024; // skip tiny inputs (<50 KB) — already small
    var _COMPRESS_MAX_BYTES = 250 * 1024; // target: 150-250 KB after compression
    function compressImage(file, cb) {
      // GIFs and SVGs are not raster -> skip; pass through.
      if (!file || !/^image\//.test(file.type)) { cb(file); return; }
      if (file.type === 'image/gif' || file.type === 'image/svg+xml') { cb(file); return; }
      // Already small? Don't waste CPU.
      if (file.size <= _COMPRESS_MIN_BYTES) { cb(file); return; }
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        try {
          var w = img.naturalWidth || img.width;
          var h = img.naturalHeight || img.height;
          if (!w || !h) { URL.revokeObjectURL(url); cb(file); return; }
          var scale = w > _COMPRESS_MAX_WIDTH ? (_COMPRESS_MAX_WIDTH / w) : 1;
          var cw = Math.max(1, Math.round(w * scale));
          var ch = Math.max(1, Math.round(h * scale));
          var canvas = document.createElement('canvas');
          canvas.width = cw; canvas.height = ch;
          var ctx = canvas.getContext('2d');
          if (!ctx) { URL.revokeObjectURL(url); cb(file); return; }
          ctx.drawImage(img, 0, 0, cw, ch);
          URL.revokeObjectURL(url);
          // Always emit JPEG for the body — keeps OCR quality at q=0.82 and
          // gives a predictable, small payload. Filename + extension track
          // the original so the user still sees "IMG_20240101.jpg".
          var origName = (file.name || 'receipt.jpg').replace(/\.[^.]+$/, '') + '.jpg';
          // Try the target quality; if still too big, drop to 0.7.
          var tryEncode = function (q, fallback) {
            canvas.toBlob(function (blob) {
              if (!blob) { cb(file); return; }
              if (blob.size > _COMPRESS_MAX_BYTES && q > 0.6) {
                tryEncode(Math.max(0.55, q - 0.1), true);
              } else {
                var compressed = new File([blob], origName, {
                  type: 'image/jpeg', lastModified: Date.now(),
                });
                cb(compressed, { original: file.size, compressed: blob.size,
                                 width: cw, height: ch });
              }
            }, 'image/jpeg', q);
          };
          tryEncode(_COMPRESS_QUALITY, false);
        } catch (e) {
          URL.revokeObjectURL(url);
          cb(file);
        }
      };
      img.onerror = function () { URL.revokeObjectURL(url); cb(file); };
      img.src = url;
    }
    function adoptCompressed(file, original, opts) {
      if (!file) { setError('Gagal memproses foto.'); return; }
      // If compression was a no-op, `opts` is undefined.
      var wasCompressed = !!(opts && opts.compressed && opts.compressed < original);
      var dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      input.files = dataTransfer.files;
      var prev = document.getElementById('preview');
      var imgEl = document.getElementById('preview-img');
      var nameEl = document.getElementById('preview-name');
      var sizeEl = document.getElementById('preview-size');
      if (nameEl) nameEl.textContent = file.name;
      if (sizeEl) {
        sizeEl.textContent = (file.size / 1024).toFixed(1) + ' KB' +
          (wasCompressed ? ' (ringan)' : '');
      }
      if (imgEl) {
        imgEl.onload = function () { if (prev) prev.classList.remove('hidden'); };
        imgEl.src = URL.createObjectURL(file);
      }
    }
    function setError(msg) {
      var e = document.getElementById('upload-error');
      if (!e) return;
      e.textContent = msg;
      e.classList.remove('hidden');
    }

    // ---- mobile picker (camera / gallery) ----
    var picker = document.getElementById('picker-modal');
    var btnCamera = document.getElementById('btn-camera');
    var btnGallery = document.getElementById('btn-gallery');
    var btnCancel = document.getElementById('btn-cancel');

    // Move the picker modal to <body> so position:fixed works even though the
    // template renders inside <main> which has a CSS transform animation
    // (pageIn).  Parent transforms create a containing block that breaks fixed
    // positioning.  The single canonical file input stays inside the form.
    if (picker && picker.parentNode !== document.body) {
      document.body.appendChild(picker);
    }

    var pickerMql = window.matchMedia('(max-width: 768px)');

    function openPicker() {
      if (!picker) return;
      picker.removeAttribute('hidden');
      picker.classList.add('show');
    }
    function closePicker() {
      if (picker) {
        picker.classList.remove('show');
        picker.setAttribute('hidden', '');
      }
    }

    // Move a file picked from either source into the main form input so the
    // existing validation/preview/submit flow handles it unchanged.  The
    // camera/gallery change handlers (below) call compressImage() first and
    // then adoptCompressed() to write the smaller body into the main input.

    if (picker) {
      // On mobile: tap upload zone → open source picker.
      // On desktop: let the <label> click through to the native file input.
      // Re-evaluate mql.matches on every click so rotation/resize is handled.
      if (zone) {
        zone.addEventListener('click', function (e) {
          if (!pickerMql.matches) return;
          e.preventDefault();
          e.stopPropagation();
          openPicker();
        });
      }

      // iOS silently ignores .click() on <input type="file"> when the input's
      // containing block is transformed/animated (the <main> pageIn animation).
      // So we never click the in-form input on mobile: instead we attach a
      // throwaway input directly to <body>, click THAT, then hand the picked
      // file back into the canonical form input via compressImage/adopt.
      var lastTmp = null;
      function cleanupTmp() {
        if (lastTmp && lastTmp.parentNode) lastTmp.parentNode.removeChild(lastTmp);
        lastTmp = null;
      }
      function ensureHiddenInput(camera) {
        cleanupTmp();
        var tmp = document.createElement('input');
        tmp.type = 'file';
        tmp.accept = 'image/*';
        tmp.style.cssText =
          'position:fixed;left:-150px;top:0;width:1px;height:1px;opacity:0;';
        if (camera) tmp.setAttribute('capture', 'environment');
        lastTmp = tmp;
        tmp.addEventListener('change', function () {
          var f = tmp.files && tmp.files[0];
          closePicker();
          if (!f) return;
          var prev = document.getElementById('preview');
          if (!/^image\//.test(f.type)) {
            input.value = '';
            if (prev) prev.classList.add('hidden');
            setError('File harus berupa gambar (JPG/PNG/WebP).');
            return;
          }
          if (f.size > maxMb * 1024 * 1024) {
            input.value = '';
            if (prev) prev.classList.add('hidden');
            setError('Ukuran maksimal ' + maxMb + ' MB.');
            return;
          }
          compressImage(f, function (file, opts) {
            adoptCompressed(file, f.size, opts);
          });
        });
        document.body.appendChild(tmp);
        return tmp;
      }
      function pickFromSource(camera) {
        if (!input) return;
        // Click synchronously while the user gesture is still active, then
        // hide the sheet — opening the dialog is async anyway.
        var tmp = ensureHiddenInput(camera);
        tmp.click();
        closePicker();
        // Auto-remove the leftover temp input in case the dialog is cancelled
        // via a back gesture and 'change' never fires.
        setTimeout(cleanupTmp, 60000);
      }

      if (btnCamera) {
        btnCamera.addEventListener('click', function (e) {
          e.preventDefault();
          pickFromSource(true);
        });
      }
      if (btnGallery) {
        btnGallery.addEventListener('click', function (e) {
          e.preventDefault();
          pickFromSource(false);
        });
      }
      if (btnCancel) btnCancel.addEventListener('click', closePicker);
      // backdrop click closes
      picker.addEventListener('click', function (e) { if (e.target === picker) closePicker(); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && picker.classList.contains('show')) closePicker();
      });
    }

    function showCompressing(msg) {
      var zone = document.getElementById('upload-zone');
      if (!zone) return;
      var prev = zone.innerHTML;
      zone.setAttribute('data-prev-html', prev);
      zone.innerHTML =
        '<div class="upload-compressing" role="status">' +
        '<div class="spinner" aria-hidden="true"></div>' +
        '<div class="upload-compressing-text">' + (msg || 'Mengompres foto…') + '</div>' +
        '</div>';
    }
    function hideCompressing() {
      var zone = document.getElementById('upload-zone');
      if (!zone) return;
      var prev = zone.getAttribute('data-prev-html');
      if (prev != null) { zone.innerHTML = prev; zone.removeAttribute('data-prev-html'); }
    }

    input.addEventListener('change', function () {
      var err = document.getElementById('upload-error');
      var prev = document.getElementById('preview');
      err.classList.add('hidden');

      var f = input.files && input.files[0];
      if (!f) { prev.classList.add('hidden'); return; }

      if (!/^image\//.test(f.type)) {
        setError('File harus berupa gambar (JPG/PNG/WebP).');
        input.value = ''; prev.classList.add('hidden');
        return;
      }
      if (f.size > maxMb * 1024 * 1024) {
        setError('Ukuran maksimal ' + maxMb + ' MB.');
        input.value = ''; prev.classList.add('hidden');
        return;
      }
      // Show preview immediately for the original, then run compression
      // asynchronously and replace the file with the compressed version.
      var prevImg = document.getElementById('preview-img');
      var nameEl = document.getElementById('preview-name');
      var sizeEl = document.getElementById('preview-size');
      if (nameEl) nameEl.textContent = f.name;
      if (sizeEl) sizeEl.textContent = (f.size / 1024).toFixed(1) + ' KB';
      if (prevImg) {
        prevImg.onload = function () { prev.classList.remove('hidden'); };
        prevImg.src = URL.createObjectURL(f);
      }
      // Always run compression so we get a small, predictable upload body.
      // For files already <50 KB this is a no-op.
      compressImage(f, function (file, opts) {
        adoptCompressed(file, f.size, opts);
      });
    });

    ['dragover', 'dragleave', 'drop'].forEach(function (ev) {
      if (!zone) return;
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.toggle('dragover', ev === 'dragover');
        if (ev === 'drop' && e.dataTransfer.files.length) {
          input.files = e.dataTransfer.files;
          input.dispatchEvent(new Event('change'));
        }
      });
    });

    form.addEventListener('submit', function (e) {
      // Guard: if no file is actually loaded in the canonical input, the
      // browser would show its generic "Please select a file" validation
      // message.  Show a clear Indonesian message instead and block submit.
      var f = input.files && input.files[0];
      if (!f) {
        e.preventDefault();
        setError('Silakan pilih foto struk terlebih dahulu.');
        return;
      }
      // If a file is selected, ensure it has been through compression before
      // the form posts.  compressImage() is async — if it's still running, we
      // delay the submit so the small compressed body goes over the wire.
      if (f.size > _COMPRESS_MIN_BYTES) {
        e.preventDefault();
        var b = document.getElementById('submit-btn');
        if (b) { b.disabled = true; b.textContent = 'Mengompres…'; }
        var zone = document.getElementById('upload-zone');
        if (zone) zone.classList.add('hidden');
        var err = document.getElementById('upload-error');
        if (err) err.classList.add('hidden');
        compressImage(f, function (file) {
          if (file) {
            var dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
          }
          if (b) b.textContent = 'Mengupload…';
          // Re-submit — this time without preventDefault, so it goes through.
          form.submit();
        });
        return;
      }
      var b = document.getElementById('submit-btn');
      if (b) { b.disabled = true; b.textContent = 'Mengupload…'; }
      var zone = document.getElementById('upload-zone');
      if (zone) zone.classList.add('hidden');
      var err = document.getElementById('upload-error');
      if (err) err.classList.add('hidden');
    });
  }

  /* ---------- Quick category chips (add transaction) ---------- */
  function initQuickCats() {
    var row = document.getElementById('quick-cats');
    var select = document.getElementById('category_id');
    if (!row || !select) return;
    Array.prototype.slice.call(select.options)
      .filter(function (o) { return o.value; })
      .slice(0, 8)
      .forEach(function (o) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'chip';
        b.textContent = o.text.trim();
        b.setAttribute('aria-pressed', 'false');
        b.addEventListener('click', function () {
          select.value = o.value;
          Array.prototype.forEach.call(row.children, function (c) {
            c.setAttribute('aria-pressed', String(c === b));
          });
        });
        row.appendChild(b);
      });
  }

  /* ---------- count-up money numbers (data-amount, respects reduced motion) ---------- */
  function initCountUp() {
    var els = document.querySelectorAll('[data-amount]');
    if (!els.length) return;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var fmt = function (n) {
      var neg = n < 0; n = Math.round(Math.abs(n));
      var s = n.toLocaleString('id-ID');
      return (neg ? '- Rp ' : 'Rp ') + s;
    };
    [].forEach.call(els, function (el) {
      var target = parseInt(el.getAttribute('data-amount'), 10) || 0;
      if (reduce) { el.textContent = fmt(target); return; }
      var t0 = null, dur = 700, from = Math.round(target * 0.6);
      el.classList.add('num');
      function step(ts) {
        if (!t0) t0 = ts;
        var p = Math.min((ts - t0) / dur, 1);
        var e = 1 - Math.pow(1 - p, 3); /* ease-out cubic */
        el.textContent = fmt(from + (target - from) * e);
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  /* ---------- stagger: set --i on children of .stagger lists ---------- */
  function initStagger() {
    [].forEach.call(document.querySelectorAll('.stagger'), function (list) {
      [].forEach.call(list.children, function (c, i) { c.style.setProperty('--i', i); });
    });
  }

  /* ---------- scroll reveal (global, auto-tag + IntersectionObserver) ---------- */
  var REVEAL_SEL = '.top-bar,.page-header,.balance-card,.worth-grid,.quick-actions,.summary-cards,.section,.transaction-item,.account-card,.more-row,.budget-row,.bill-row,.debt-tile';
  function initReveal() {
    var existing = [].slice.call(document.querySelectorAll('.reveal'));
    var fresh = [].slice.call(document.querySelectorAll(REVEAL_SEL))
      .filter(function (el) { return !el.classList.contains('reveal'); });
    fresh.forEach(function (el) { el.classList.add('reveal'); });
    var els = existing.concat(fresh);
    if (!els.length) return;
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    els.forEach(function (el, i) { el.style.setProperty('--d', (i % 8) * 55 + 'ms'); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.06, rootMargin: '0px 0px -40px 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- top loadbar ---------- */
  function runLoadbar() {
    var b = document.getElementById('loadbar');
    if (!b) return;
    b.classList.add('running');
    setTimeout(function () { b.classList.remove('running'); }, 1100);
  }

/* ---------- Money input sanitizer ----------
   * Conservative: never silently strip invalid characters.
   * Only canonical Indonesian forms are accepted by the backend:
   *   optional "Rp" + digits with optional dot thousands separators.
   * On invalid input we do NOT mutate the value; we flag custom validity
   * so the browser prevents submit. The backend remains authoritative. */
  var MONEY_RE = /^\d+(\.\d{3})*$/;
  function moneySanitize(raw) {
    var rp = /^[Rr][Pp]\s*/.exec(raw) || /^\s*/.exec(raw);
    return { prefix: rp[0], rest: raw.slice(rp[0].length) };
  }
  function moneyRecognize(raw) {
    if (raw == null) return null;
    var p = moneySanitize(String(raw).trim());
    var rest = p.rest;
    if (!MONEY_RE.test(rest)) return null;
    return p.prefix === '' ? p.rest : p.prefix + p.rest;
  }
  function initMoneyInputs() {
    var moneyFields = document.querySelectorAll('input[inputmode="numeric"]');
    for (var i = 0; i < moneyFields.length; i++) {
      (function (el) {
        var setMoneyValidity = function () {
          var raw = el.value;
          if (el.hasAttribute('required') && (!raw || moneyRecognize(raw) === null)) {
            el.setCustomValidity('Nominal harus berupa angka bulat (contoh: 10000 atau 10.000).');
          } else if (!el.hasAttribute('required') && raw && moneyRecognize(raw) === null) {
            el.setCustomValidity('Nominal harus berupa angka bulat (contoh: 10000 atau 10.000).');
          } else {
            el.setCustomValidity('');
          }
        };
        el.addEventListener('input', setMoneyValidity);
        el.addEventListener('blur', setMoneyValidity);
        el.addEventListener('change', setMoneyValidity);
        // Paste: only allow the clipboard text if it is a valid canonical form.
        el.addEventListener('paste', function (e) {
          var text = (e.clipboardData || window.clipboardData).getData('text');
          if (text && moneyRecognize(text) === null) {
            e.preventDefault();
            el.setCustomValidity('Nominal harus berupa angka bulat (contoh: 10000 atau 10.000).');
          }
        });
      })(moneyFields[i]);
    }
  }
  /* ---------- Keyboard shortcuts (no input focus) ---------- */
  function initKeyboardShortcuts() {
    var map = {
      g: '/accounts',     // g -> Akun
      t: '/transactions', // t -> Transaksi
      r: '/reports',      // r -> Laporan
      b: '/budgets',      // b -> Budget
      n: '/transactions/add' // n -> catat baru
    };
    document.addEventListener('keydown', function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var t = e.target;
      var tag = t && t.tagName ? t.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select' ||
          (t && t.isContentEditable)) return;
      var dest = map[e.key.toLowerCase()];
      if (dest) { e.preventDefault(); window.location.href = dest; }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    runLoadbar();
    initStagger();
    initCountUp();
    initReveal();
    initNetWorthChart();
    initReceiptUpload();
    initQuickCats();
    initMoneyInputs();
    initKeyboardShortcuts();
  });
})();
/* ---------- balance privacy toggle (eye) ---------- */
(function(){
  var root = document.documentElement;
  function isHidden(){ return root.classList.contains('bal-hidden'); }
  function sync(){
    var h = isHidden() ? 'true' : 'false';
    var btns = document.querySelectorAll('.priv-toggle');
    for (var i = 0; i < btns.length; i++) btns[i].setAttribute('aria-pressed', h);
  }
  document.addEventListener('click', function(e){
    var btn = e.target.closest ? e.target.closest('.priv-toggle') : null;
    if (!btn) return;
    var nowHidden = !isHidden();
    root.classList.toggle('bal-hidden', nowHidden);
    try { localStorage.setItem('pf_hide_balance', nowHidden ? '1' : '0'); } catch (err) {}
    sync();
  });
  sync();
})();
