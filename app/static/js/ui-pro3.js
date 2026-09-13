/* Finance UI PRO part 3 - FAB + palette + to-top + filter */
(function () {
  'use strict';
  function qsa(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  var fabWrap = document.getElementById('fabWrap');
  var fabMain = document.getElementById('fabMain');
  if (fabWrap && fabMain) {
    fabMain.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = fabWrap.classList.toggle('open');
      fabMain.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function (e) {
      if (fabWrap.classList.contains('open') && !fabWrap.contains(e.target)) {
        fabWrap.classList.remove('open'); fabMain.setAttribute('aria-expanded', 'false');
      }
    });
  }
  var MENU = [
    ['H', 'Beranda', '/'], ['T', 'Transaksi', '/transactions'],
    ['-', 'Tambah pengeluaran', '/transactions/add?tx_type=EXPENSE'],
    ['+', 'Tambah pemasukan', '/transactions/add?tx_type=INCOME'],
    ['R', 'Transfer', '/transfer'], ['S', 'Scan struk', '/receipts/upload'],
    ['L', 'Laporan', '/reports'], ['A', 'Akun', '/accounts'],
    ['D', 'Hutang', '/debts'], ['B', 'Tagihan', '/bills'],
    ['G', 'Budget', '/budgets'], ['V', 'Tabungan', '/savings'],
    ['E', 'Aset', '/assets'], ['I', 'Investasi', '/investments'],
    ['K', 'Kategori', '/categories'], ['M', 'Lainnya', '/more'], ['?', 'Bantuan', '/help']
  ];
  var palOverlay = document.getElementById('palOverlay');
  var palInput = document.getElementById('palInput');
  var palList = document.getElementById('palList');
  var palIdx = 0, palShown = [];
  function renderPal(filter) {
    if (!palList) return;
    var qq = (filter || '').toLowerCase().trim();
    palShown = MENU.filter(function (m) { return !qq || m[1].toLowerCase().indexOf(qq) !== -1; });
    palIdx = 0;
    if (!palShown.length) { palList.innerHTML = '<div class="empty-text" style="padding:14px">Tidak ketemu.</div>'; return; }
    var html = '';
    for (var i = 0; i < palShown.length; i++) {
      html += '<button type="button" class="pal-item' + (i === 0 ? ' pal-active' : '') + '" data-url="' + palShown[i][2] + '">' +
        '<span class="pal-ic">' + palShown[i][0] + '</span><span>' + palShown[i][1] + '</span><span class="pal-go">-></span></button>';
    }
    palList.innerHTML = html;
  }
  function openPalette() {
    if (!palOverlay) return;
    palOverlay.classList.add('show');
    palOverlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('pal-open');
    renderPal('');
    if (palInput) { palInput.value = ''; setTimeout(function () { palInput.focus(); }, 30); }
  }
  function closePalette() {
    if (!palOverlay) return;
    palOverlay.classList.remove('show');
    palOverlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('pal-open');
  }
  window.PFPalette = { open: openPalette, close: closePalette };
  if (palOverlay && palInput) {
    palInput.addEventListener('input', function () { renderPal(palInput.value); });
    palInput.addEventListener('keydown', function (e) {
      var items = qsa('.pal-item', palList);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!items.length) return;
        palIdx = e.key === 'ArrowDown' ? (palIdx + 1) % items.length : (palIdx - 1 + items.length) % items.length;
        items.forEach(function (it, i) { it.classList.toggle('pal-active', i === palIdx); });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items[palIdx]) window.location.href = items[palIdx].getAttribute('data-url');
      } else if (e.key === 'Escape') { closePalette(); }
    });
    palList.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.pal-item') : null;
      if (b) window.location.href = b.getAttribute('data-url');
    });
    palOverlay.addEventListener('click', function (e) { if (e.target === palOverlay) closePalette(); });
  }
  var fabSearch = document.getElementById('fabSearch');
  if (fabSearch) fabSearch.addEventListener('click', function () {
    if (fabWrap) fabWrap.classList.remove('open'); openPalette();
  });
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); openPalette(); }
  });
  var toTop = document.getElementById('toTop');
  if (toTop) {
    window.addEventListener('scroll', function () {
      toTop.classList.toggle('show', window.scrollY > 480);
    }, { passive: true });
    toTop.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
  }
  var search = document.querySelector('form.filter-form input[name="search"]');
  if (search) {
    var list = document.querySelector('.transaction-list');
    search.addEventListener('input', function () {
      if (!list) return;
      var qq = search.value.toLowerCase().trim();
      var rows = qsa('.transaction-item', list), shown = 0;
      rows.forEach(function (r) {
        var hit = !qq || (r.textContent || '').toLowerCase().indexOf(qq) !== -1;
        r.style.display = hit ? '' : 'none';
        if (hit) shown++;
      });
      var note = document.getElementById('client-filter-note');
      if (!shown) {
        if (!note) {
          note = document.createElement('div');
          note.id = 'client-filter-note';
          note.className = 'empty-text';
          note.textContent = 'Tidak ada yang cocok di halaman ini. Tekan Filter untuk cari ke server.';
          list.parentNode.insertBefore(note, list.nextSibling);
        }
        note.style.display = '';
      } else if (note) note.style.display = 'none';
    });
  }
})();
