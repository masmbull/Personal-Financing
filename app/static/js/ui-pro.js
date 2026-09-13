/* Finance UI PRO part 1 - modal manager + toast from query */
(function () {
  'use strict';
  function qsa(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function toastFromQuery() {
    try {
      var q = new URLSearchParams(window.location.search);
      var msg = null, ok = true;
      if (q.get('saved') === '1') { msg = 'Berhasil disimpan'; }
      else if (q.get('deleted') === '1') { msg = 'Berhasil dihapus'; }
      else if (q.get('error')) { msg = decodeURIComponent(q.get('error')); ok = false; }
      if (msg && window.showToast) window.showToast(msg, ok);
      if (q.get('saved') || q.get('deleted') || q.get('error')) {
        q.delete('saved'); q.delete('deleted'); q.delete('error');
        var qs = q.toString();
        window.history.replaceState({}, '', window.location.pathname + (qs ? '?' + qs : ''));
      }
    } catch (e) {}
  }
  var overlay = document.getElementById('modalOverlay');
  var body = document.getElementById('modalBody');
  var titleEl = document.getElementById('modalTitle');
  var dialog = overlay ? overlay.querySelector('.modal') : null;
  var lastFocus = null;
  function focusables() {
    if (!dialog) return [];
    return qsa('a[href],button:not([disabled]),input,select,textarea', dialog).filter(function (el) { return el.offsetParent !== null; });
  }
  function openModal(title, html, size) {
    if (!overlay || !body) return;
    lastFocus = document.activeElement;
    if (titleEl) titleEl.textContent = title || 'Detail';
    body.innerHTML = html || '';
    if (dialog) { dialog.classList.remove('modal-sm', 'modal-lg'); if (size) dialog.classList.add('modal-' + size); }
    overlay.classList.add('show');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    body.scrollTop = 0;
    var f = focusables();
    if (f.length) { try { f[0].focus({ preventScroll: true }); } catch (e) {} }
  }
  function closeModal() {
    if (!overlay) return;
    overlay.classList.remove('show');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    if (lastFocus && lastFocus.focus) { try { lastFocus.focus({ preventScroll: true }); } catch (e) {} }
    lastFocus = null;
  }
  window.PFModal = { open: openModal, close: closeModal };
  if (overlay) {
    overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModal(); });
    document.addEventListener('keydown', function (e) {
      if (!overlay.classList.contains('show')) return;
      if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
      if (e.key === 'Tab') {
        var f = focusables();
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }
  var mc = document.getElementById('modalClose');
  if (mc) mc.addEventListener('click', closeModal);
  window.PFToastQuery = toastFromQuery;
  document.addEventListener('DOMContentLoaded', toastFromQuery);
  toastFromQuery();
})();
