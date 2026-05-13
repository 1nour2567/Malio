/* Malio PWA — Service Worker */
const CACHE_NAME = 'malio-v1';
const PRELOAD_CACHE = 'malio-preload-v1';

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/src/style.css',
  '/src/app.js',
  '/manifest.json'
];

// Install — cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME && k !== PRELOAD_CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API requests — network first, no cache
  if (url.pathname.startsWith('/api/') || url.pathname === '/stream') {
    return; // Let browser handle normally (no cache for API)
  }

  // Static assets — cache first, network fallback
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request).then((response) => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      });
      return cached || fetchPromise;
    })
  );
});

// Preload next track (triggered by main thread message)
self.addEventListener('message', (event) => {
  if (event.data.type === 'prefetch' && event.data.url) {
    const url = event.data.url;
    fetch(url).then((response) => {
      if (response.ok) {
        caches.open(PRELOAD_CACHE).then((cache) => {
          cache.put(url, response);
        });
      }
    }).catch(() => {});
  }
});
