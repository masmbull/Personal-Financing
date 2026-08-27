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
      });
  }
  /* ---------- Receipt upload preview / validation ---------- */
  function initReceiptUpload() {
    var input = document.getElementById('file-input');
    var zone = document.getElementById('upload-zone');
    var form = document.getElementById('receipt-form');
    if (!input || !form) return;

    var maxMb = parseInt(form.dataset.maxMb || '5', 10);

    input.addEventListener('change', function () {
      var err = document.getElementById('upload-error');
      var prev = document.getElementById('preview');
      var img = document.getElementById('preview-img');
      var name = document.getElementById('preview-name');
      var size = document.getElementById('preview-size');
      err.classList.add('hidden');

      var f = input.files && input.files[0];
      if (!f) { prev.classList.add('hidden'); return; }

      if (!/^image\//.test(f.type)) {
        err.textContent = 'File harus berupa gambar (JPG/PNG/WebP).';
        err.classList.remove('hidden');
        input.value = ''; prev.classList.add('hidden');
        return;
      }
      if (f.size > maxMb * 1024 * 1024) {
        err.textContent = 'Ukuran maksimal ' + maxMb + ' MB.';
        err.classList.remove('hidden');
        input.value = ''; prev.classList.add('hidden');
        return;
      }
      name.textContent = f.name;
      size.textContent = (f.size / 1024).toFixed(1) + ' KB';
      img.onload = function () { prev.classList.remove('hidden'); };
      img.src = URL.createObjectURL(f);
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

    form.addEventListener('submit', function () {
      var b = document.getElementById('submit-btn');
      if (b) { b.disabled = true; b.textContent = 'Mengupload…'; }
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

  document.addEventListener('DOMContentLoaded', function () {
    initNetWorthChart();
    initReceiptUpload();
    initQuickCats();
  });
})();