/* ==== Receipt Review interactions (detail page) ==== */
function initReceiptDetail() {
  // --- flash: close button + auto-dismiss (longer for success) ---
  var flashes = document.querySelectorAll('.rr-flash');
  flashes.forEach(function (f) {
    var close = f.querySelector('.rr-flash-close');
    if (close) close.addEventListener('click', function () { f.remove(); });
    var isOk = f.classList.contains('rr-flash--ok');
    if (isOk && f.id === 'toast-success') {
      var t = setTimeout(function () { if (f.parentNode) f.remove(); }, 7000);
      if (close) close._rrTimer = t;
    } else {
      var t2 = setTimeout(function () { if (f.parentNode) f.remove(); }, 5000);
      if (close) close._rrTimer = t2;
    }
  });

  // --- viewer image: fade in, hide skeleton ---
  var viewerImg = document.querySelector('.rr-viewer-img');
  if (viewerImg) {
    if (viewerImg.complete && viewerImg.naturalWidth) {
      viewerImg.classList.add('loaded');
    } else {
      viewerImg.addEventListener('load', function () { viewerImg.classList.add('loaded'); });
    }
    var ghost = viewerImg.closest('.rr-viewer') && viewerImg.closest('.rr-viewer').querySelector('.rr-viewer-ghost');
    if (ghost) {
      if (viewerImg.classList.contains('loaded')) { ghost.classList.add('hidden'); }
      else viewerImg.addEventListener('load', function () { ghost.classList.add('hidden'); });
    }
  }

  // --- lightbox (premium viewer) ---
  var lb = document.getElementById('rrLightbox');
  var lbImg = document.getElementById('rrLightboxImg');
  if (lb && lbImg) {
    var open = function () {
      lb.setAttribute('aria-hidden', 'false');
      lb.classList.add('active');
      var src = viewerImg ? viewerImg.src : lbImg.src;
      if (src) lbImg.src = src;
      document.body.style.overflow = 'hidden';
      var c = document.getElementById('rrLightboxClose');
      if (c) c.focus();
    };
    var close = function () {
      lb.setAttribute('aria-hidden', 'true');
      lb.classList.remove('active');
      document.body.style.overflow = '';
    };
    var toggle = function (on) { on ? open() : close(); };
    var zooms = document.querySelectorAll('[data-rr-zoom]');
    zooms.forEach(function (el) { el.addEventListener('click', open); });
    if (lbImg) lbImg.addEventListener('click', open);
    var cl = document.getElementById('rrLightboxClose');
    if (cl) cl.addEventListener('click', close);
    // backdrop click closes
    lb.addEventListener('click', function (e) { if (e.target === lb) close(); });
    // ESC closes
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && lb.classList.contains('active')) { e.preventDefault(); close(); }
      // close also via Escape if a zoom is focused and lightbox open
    });
  }

  // --- save button: prevent double-submit, show spinner ---
  var saveBtn = document.querySelector('[data-rr-save]');
  if (saveBtn) {
    var form = saveBtn.closest('form');
    if (form) form.addEventListener('submit', function () {
      saveBtn.classList.add('rr-btn--loading');
      saveBtn.disabled = true;
      var label = saveBtn.querySelector('.rr-btn-label');
      if (label) label.textContent = 'Menyimpan…';
    });
  }

  // --- accordion (details): reduced-motion respected via CSS; here, ARIA sync ---
  var accords = document.querySelectorAll('[data-rr-accordion]');
  accords.forEach(function (d) {
    d.addEventListener('toggle', function () {
      var sum = d.querySelector('.rr-items-summary');
      if (sum) sum.setAttribute('aria-expanded', String(d.open));
    });
  });
}

document.addEventListener('DOMContentLoaded', function () {
  initReceiptDetail();
});
