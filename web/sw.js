// Bump VERSION whenever any file in SHELL changes, so phones pick up the new shell.
const VERSION = 'safezone-v33';
const SHELL = [
  '/',
  '/app.css',
  '/css/about.css',
  '/css/base.css',
  '/css/capture.css',
  '/css/emergency.css',
  '/css/landing.css',
  '/css/livemap.css',
  '/css/setup.css',
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
  '/js/livemap.js',
  '/js/machine.js',
  '/js/overlay.js',
  '/js/photo.js',
  '/js/places.js',
  '/js/quality.js',
  '/js/routemap.js',
  '/js/screens/about.js',
  '/js/screens/capture.js',
  '/js/screens/emergency.js',
  '/js/screens/landing.js',
  '/js/screens/parts.js',
  '/js/screens/permissions.js',
  '/js/screens/places.js',
  '/js/screens/prepare.js',
  '/js/screens/review.js',
  '/js/screens/setupmap.js',
  '/js/shots.js',
  '/js/standby.js',
  '/js/voice.js',
  '/manifest.webmanifest',
  '/vendor/leaflet/LICENSE',
  '/vendor/leaflet/README.md',
  '/vendor/leaflet/images/layers-2x.png',
  '/vendor/leaflet/images/layers.png',
  '/vendor/leaflet/images/marker-icon-2x.png',
  '/vendor/leaflet/images/marker-icon.png',
  '/vendor/leaflet/images/marker-shadow.png',
  '/vendor/leaflet/leaflet.css',
  '/vendor/leaflet/leaflet.js',
];

const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
const TILES = `${VERSION}-tiles`;
const TILE_MAX = 300;
const isTileHost = (host) => host === 'tile.openstreetmap.org' || host === 'disaportaldata.gsi.go.jp';

// Map tiles are cached as they are viewed, so a plan looked at online shows its map offline. Cache keys keep
// insertion order, so the first keys are the oldest.
async function tile(request) {
  const cache = await caches.open(TILES);
  const hit = await cache.match(request);
  if (hit) return hit;
  // Offline with no cached copy: an empty 504 lets the map draw its overlays on the plain background.
  const res = await fetch(request).catch(() => new Response(null, { status: 504, statusText: 'Offline' }));
  if (res.ok || res.type === 'opaque') {
    await cache.put(request, res.clone());
    const keys = await cache.keys();
    await Promise.all(keys.slice(0, Math.max(0, keys.length - TILE_MAX)).map((k) => cache.delete(k)));
  }
  return res;
}

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== `${VERSION}-fonts` && k !== TILES).map((k) => caches.delete(k))))
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
  if (isTileHost(url.hostname)) { event.respondWith(tile(event.request)); return; }
  if (url.origin !== location.origin) return;
  // The plan lives in IndexedDB, so API calls are never served stale from a cache.
  if (url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(caches.match('/index.html').then((hit) => hit ?? fetch(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then((hit) => hit ?? fetch(event.request)));
});
