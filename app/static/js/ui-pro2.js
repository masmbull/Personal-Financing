/* Finance UI PRO part 2 - confirm modal + auto delete hook */
(function () {
  'use strict';
  function askConfirm(msg, onYes) {
    if (!window.PFModal) { if (confirm(msg)) onYes(); return; }
    window.PFModal.open('Konfirmasi',
      '<p>' + msg + '</p><div class="confirm-actions">' +
      '<button type="button" class="btn" data-no>Batal</button>' +
      '<button type="button" class="btn btn-danger" data-yes>Ya, lanjutkan</button></div>', 'sm');
    var body = document.getElementById('modalBody');
    var yes = body.querySelector('[data-yes]'), no = body.querySelector('[data-no]');
    if (no) no.addEventListener('click', window.PFModal.close);
    if (yes) yes.addEventListener('click', function () { window.PFModal.close(); onYes(); });
  }
  window.PFConfirm = askConfirm;
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var el = e.target.closest('[data-confirm]');
    var del = null;
    if (!el) {
      var a = e.target.closest('a[href*="/delete"]');
      if (a && !a.hasAttribute('data-no-confirm')) del = a;
    }
    var target = el || del;
    if (!target) return;
    e.preventDefault();
    var msg = target.getAttribute('data-confirm') || 'Hapus data ini? Tindakan tidak bisa dibatalkan.';
    var href = target.getAttribute('href');
    askConfirm(msg, function () { if (href) window.location.href = href; });
  });
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (f && f.hasAttribute && f.hasAttribute('data-confirm') && !f.hasAttribute('data-confirmed')) {
      e.preventDefault();
      askConfirm(f.getAttribute('data-confirm') || 'Yakin lanjutkan?', function () {
        f.setAttribute('data-confirmed', '1'); f.submit();
      });
    }
  });
})();
