// Bump VERSION whenever any file in SHELL changes, so phones pick up the new shell.
const VERSION = 'safezone-v2';
const SHELL = [
  '/',
  '/index.html',
  '/app.css',
  '/manifest.webmanifest',
  '/icons/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/js/api.js',
  '/js/app.js',
  '/js/db.js',
  '/js/dom.js',
  '/js/geometry.js',
  '/js/machine.js',
  '/js/overlay.js',
  '/js/photo.js',
  '/js/routemap.js',
  '/js/screens/emergency.js',
  '/js/screens/parts.js',
  '/js/screens/prepare.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;
  // The plan lives in IndexedDB, so API calls are never served stale from a cache.
  if (url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(caches.match('/index.html').then((hit) => hit ?? fetch(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then((hit) => hit ?? fetch(event.request)));
});
