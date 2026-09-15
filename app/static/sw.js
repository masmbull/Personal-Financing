/* Finance PWA Service Worker — cache-first for static assets, network-first for HTML */

const CACHE_NAME = 'finance-v1';
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/ui-pro.js',
  '/static/js/ui-pro2.js',
  '/static/js/ui-pro3.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

/* Install: pre-cache shell */
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

/* Activate: evict old caches */
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

/* Fetch: network-first for HTML/API, cache-first for static */
self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);

  /* Skip non-GET and API calls */
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;

  /* HTML pages: network-first with offline fallback */
  if (e.request.headers.get('accept') && e.request.headers.get('accept').indexOf('text/html') !== -1) {
    e.respondWith(
      fetch(e.request).then(function (resp) {
        var clone = resp.clone();
        caches.open(CACHE_NAME).then(function (c) { c.put(e.request, clone); });
        return resp;
      }).catch(function () {
        return caches.match(e.request).then(function (cached) {
          return cached || caches.match('/');
        });
      })
    );
    return;
  }

  /* Static assets: cache-first */
  e.respondWith(
    caches.match(e.request).then(function (cached) {
      if (cached) return cached;
      return fetch(e.request).then(function (resp) {
        /* Only cache same-origin successful responses */
        if (resp.ok && url.origin === self.location.origin) {
          var clone = resp.clone();
          caches.open(CACHE_NAME).then(function (c) { c.put(e.request, clone); });
        }
        return resp;
      });
    })
  );
});