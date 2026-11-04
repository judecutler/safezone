// Bump VERSION whenever any file in SHELL changes, so phones pick up the new shell.
const VERSION = 'safezone-v20';
const SHELL = [
  '/',
  '/app.css',
  '/css/base.css',
  '/css/capture.css',
  '/css/emergency.css',
  '/css/landing.css',
  '/css/tokens.css',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon.svg',
  '/index.html',
  '/js/api.js',
  '/js/app.js',
  '/js/art/neighborhood.js',
  '/js/art/seal.js',
  '/js/art/signs.js',
  '/js/camera.js',
  '/js/db.js',
  '/js/dom.js',
  '/js/geometry.js',
  '/js/guide.js',
  '/js/machine.js',
  '/js/overlay.js',
  '/js/photo.js',
  '/js/places.js',
  '/js/quality.js',
  '/js/routemap.js',
  '/js/screens/capture.js',
  '/js/screens/emergency.js',
  '/js/screens/landing.js',
  '/js/screens/parts.js',
  '/js/screens/permissions.js',
  '/js/screens/places.js',
  '/js/screens/prepare.js',
  '/js/screens/review.js',
  '/js/shots.js',
  '/js/standby.js',
  '/js/voice.js',
  '/manifest.webmanifest',
];

const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== `${VERSION}-fonts`).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  // The Japanese label font comes from Google Fonts; keep a copy so the labels render offline.
  if (FONT_HOSTS.has(url.hostname)) {
    event.respondWith(caches.open(`${VERSION}-fonts`).then((c) => c.match(event.request).then((hit) => hit ?? fetch(event.request).then((res) => {
      if (res.ok || res.type === 'opaque') c.put(event.request, res.clone());
      return res;
    }))));
    return;
  }
  if (url.origin !== location.origin) return;
  // The plan lives in IndexedDB, so API calls are never served stale from a cache.
  if (url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(caches.match('/index.html').then((hit) => hit ?? fetch(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then((hit) => hit ?? fetch(event.request)));
});
