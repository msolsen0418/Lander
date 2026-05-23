const CACHE = 'fl-arb-v3';
const SHELL = ['/', '/static/manifest.json', '/static/icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Never intercept non-GET requests (form POSTs, mutations).
  // Safari PWA throws "Response served by service worker has redirections"
  // when the SW intercepts a POST and the server replies with a 302.
  if (e.request.method !== 'GET') return;

  // Never intercept auth pages — their redirects confuse WebKit.
  if (url.pathname === '/login' || url.pathname === '/logout') return;

  // API: network-first, fall back to cache for offline viewing
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request)
        .then(r => {
          const clone = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return r;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // SSE stream: always network, never cache
  if (url.pathname.includes('/stream')) return;

  // Shell + static: network-first so updates are picked up immediately
  e.respondWith(
    fetch(e.request)
      .then(r => {
        const clone = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
