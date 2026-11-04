import { h } from './dom.js';
import { formatDistance } from './geometry.js';
import { insideHazard, pointAlong, routeLength, stepPoints } from './guide.js';

// The one module that draws a real map (contract: docs/livemap.md). Leaflet is vendored and loaded once.
// Every overlay is vector or a DOM marker, so with no tiles at all the hazard area, route and walker still draw.

const TILE_ATTR = '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';
const JP_TSUNAMI_URL = 'https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png';
const JP_ATTR = 'Tsunami: <a href="https://disaportal.gsi.go.jp/" target="_blank" rel="noopener">GSI Hazard Map Portal</a>';
const LOAD_TIMEOUT_MS = 8000;
const OFFSET = { left: [-12, 0], right: [12, 0], top: [0, -14] };

let leafletReady = null;

function loadLeaflet() {
  if (window.L?.map) return Promise.resolve(window.L);
  leafletReady ??= new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-leaflet]')) {
      document.head.append(h('link', { rel: 'stylesheet', href: '/vendor/leaflet/leaflet.css', 'data-leaflet': '' }));
    }
    const fail = () => { leafletReady = null; reject(new Error('Leaflet could not load')); };
    const timer = setTimeout(fail, LOAD_TIMEOUT_MS);
    const script = h('script', { src: '/vendor/leaflet/leaflet.js' });
    script.onload = () => { clearTimeout(timer); window.L?.map ? resolve(window.L) : fail(); };
    script.onerror = () => { clearTimeout(timer); script.remove(); fail(); };
    document.head.append(script);
  });
  return leafletReady;
}

const ll = ([lon, lat]) => [lat, lon];
// Leaflet sets tooltip strings as HTML, and names come from outside data, so every text is escaped.
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const isPoint = (p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]);
const FRAME_PLACES_M = 2000;
const EXIT_CLEAR_PX = 40;
// Lower ranks keep their labels when two collide.
const RANK = { 'lm-label-dest': 0, 'lm-label-home': 1, 'lm-label-exit': 2, 'lm-label-place': 3 };

// Where the route finally leaves the hazard area: the last step from inside to outside along the path,
// sampled every 5 m. Outside means off the hazard polygons and, when the map has land polygons, on mapped land,
// the same test the spoken guidance uses. Null when the route never crosses (or there are no polygons).
export function hazardExit(route, hazardArea) {
  const polys = hazardArea?.polygons ?? [];
  if (!polys.length || !route?.path?.length) return null;
  const land = hazardArea.land_polygons ?? [];
  const outside = (p) => !insideHazard(polys, p) && (!land.length || insideHazard(land, p));
  const total = routeLength(route);
  let wasOutside = outside(route.path[0]), exit = null;
  for (let m = 5; m <= total + 4; m += 5) {
    const p = pointAlong(route, Math.min(m, total));
    const out = outside(p);
    if (out && !wasOutside) exit = { at: p, alongM: Math.min(m, total) };
    if (!out) exit = null;
    wasOutside = out;
  }
  return exit;
}

function destinationPoint([lon, lat], bearingDeg, meters) {
  const R = 6371008.8, d = meters / R, b = (bearingDeg * Math.PI) / 180;
  const p1 = (lat * Math.PI) / 180, l1 = (lon * Math.PI) / 180;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [(l2 * 180) / Math.PI, (p2 * 180) / Math.PI];
}

const walkText = (min) => (min < 1 ? 'under 1 min walk' : `${Math.round(min)} min walk`);

export async function liveMap(container, { region = 'us-ca', interactive = true } = {}) {
  const L = await loadLeaflet();
  container.classList.add('livemap');
  const map = L.map(container, {
    zoomControl: false, dragging: interactive, touchZoom: interactive, doubleClickZoom: interactive,
    boxZoom: false, keyboard: interactive, scrollWheelZoom: false, tap: false, zoomSnap: 0.25,
    attributionControl: true, preferCanvas: false,
  });
  map.attributionControl.setPrefix(false);
  if (interactive) L.control.zoom({ position: 'bottomright' }).addTo(map);
  for (const [name, z] of [['lm-hazard', 405], ['lm-route', 420], ['lm-marks', 610], ['lm-walker', 640]]) {
    map.createPane(name).style.zIndex = z;
  }
  const dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  L.tileLayer(`https://{s}.basemaps.cartocdn.com/${dark ? 'dark_all' : 'light_all'}/{z}/{x}/{y}{r}.png`, {
    subdomains: 'abcd', maxZoom: 19, attribution: TILE_ATTR, className: 'lm-tiles',
    // CORS responses, so the service worker caches real-size tiles rather than padded opaque ones.
    crossOrigin: 'anonymous',
  }).addTo(map);
  L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
  map.setView([37.77, -122.5], 15);

  const card = h('div', { class: 'lm-card', hidden: true, role: 'status' });
  container.append(card);
  L.DomEvent.disableClickPropagation(card);

  const layers = { home: null, hazard: null, route: null, places: null, walker: null, exit: null };
  let homeText = 'Home', homeAt = null, hazardArea = null, routeData = null, walkerAt = null, follow = true;

  const divMarker = (at, cls, html, pane = 'lm-marks', size = [24, 24]) =>
    L.marker(ll(at), { pane, interactive: false, keyboard: false,
      icon: L.divIcon({ className: cls, html, iconSize: size, iconAnchor: [size[0] / 2, size[1] / 2] }) });
  const bindLabel = (marker, text, cls, direction) =>
    marker.unbindTooltip().bindTooltip(text, { permanent: true, direction, className: `lm-label ${cls}`, offset: OFFSET[direction], opacity: 1 });
  // Side labels face the middle of the map, so they never run off its edge. The crossing label sits on the
  // other side from the destination label. A label that would collide with a higher-ranked one is hidden.
  // orient() redoes all of this after each move and zoom.
  const sideLabels = new Map();
  const label = (marker, text, cls, direction = 'right') => {
    if (direction !== 'top') sideLabels.set(marker, { text, cls, direction });
    return bindLabel(marker, text, cls, direction);
  };
  function orient() {
    const width = map.getSize().x;
    let destDir = null;
    const live = [...sideLabels].filter(([marker]) => map.hasLayer(marker) || !sideLabels.delete(marker));
    for (const [marker, l] of live) {
      const x = map.latLngToContainerPoint(marker.getLatLng()).x;
      let dir = x > width * 0.5 ? 'left' : 'right';
      if (l.cls === 'lm-label-dest') destDir = dir;
      if (l.cls === 'lm-label-exit' && destDir) dir = destDir === 'left' ? 'right' : 'left';
      // Flip in place: unbinding and rebinding a permanent tooltip mid-zoom can leave the old element behind.
      if (dir !== l.direction) {
        l.direction = dir;
        const tip = marker.getTooltip();
        if (tip) { tip.options.direction = dir; tip.options.offset = OFFSET[dir]; tip.update(); }
      }
    }
    // A label still too wide for its side slides back inside the map edge.
    const box = container.getBoundingClientRect();
    for (const [marker] of live) {
      const el = marker.getTooltip()?.getElement();
      if (!el) continue;
      el.style.marginLeft = el.style.marginTop = '';
      const r = el.getBoundingClientRect();
      const dx = r.left < box.left + 4 ? box.left + 4 - r.left : r.right > box.right - 4 ? box.right - 4 - r.right : 0;
      const dy = r.top < box.top + 4 ? box.top + 4 - r.top : r.bottom > box.bottom - 4 ? box.bottom - 4 - r.bottom : 0;
      if (dx) el.style.marginLeft = `${dx}px`;
      if (dy) el.style.marginTop = `${dy}px`;
    }
    const kept = [];
    const view = map.getBounds();
    live.sort((a, b) => (RANK[a[1].cls] ?? 9) - (RANK[b[1].cls] ?? 9));
    for (const [marker, l] of live) {
      const el = marker.getTooltip()?.getElement();
      if (!el) continue;
      el.style.visibility = '';
      // A label whose marker is off the map would point at nothing.
      if (!view.contains(marker.getLatLng())) { el.style.visibility = 'hidden'; continue; }
      const r = el.getBoundingClientRect();
      const gap = l.cls === 'lm-label-exit' ? EXIT_CLEAR_PX : 2;
      const hit = kept.some((k) => r.left < k.right + gap && r.right > k.left - gap && r.top < k.bottom + gap && r.bottom > k.top - gap);
      if (hit) el.style.visibility = 'hidden'; else kept.push(r);
    }
  }
  map.on('moveend zoomend', orient);
  // The container can change size after the map is made (late CSS, a legend that wraps); without this the
  // vector layers stay clipped to the old size.
  const resize = new ResizeObserver(() => map.invalidateSize({ pan: false }));
  resize.observe(container);
  const replace = (key, layer) => { layers[key]?.remove(); layers[key] = layer ? layer.addTo(map) : null; };
  // Labels go on the side away from the other end of the route, so home and destination labels never collide.
  const sideAwayFrom = (at, other) => (other && other[0] > at[0] ? 'left' : 'right');

  function drawExit() {
    const exit = routeData ? hazardExit(routeData, hazardArea) : null;
    if (!exit) { replace('exit', null); return; }
    const m = divMarker(exit.at, 'lm-exit', '', 'lm-marks', [14, 14]);
    label(m, `Leaving the hazard area<br>after ${formatDistance(exit.alongM)}`, 'lm-label-exit', sideAwayFrom(exit.at, routeData.origin));
    replace('exit', m);
    orient();
  }

  // 'all' frames home, the route and its destination, plus only the places within FRAME_PLACES_M of home;
  // farther places keep their markers outside the frame.
  function boundsOf(what) {
    const pts = [];
    if ((what === 'home' || what === 'all') && homeAt) pts.push(ll(homeAt));
    if ((what === 'route' || what === 'all') && layers.route) pts.push(layers.route.getBounds());
    if (what === 'all' && layers.places && homeAt) {
      for (const m of layers.places.getLayers()) if (map.distance(m.getLatLng(), ll(homeAt)) <= FRAME_PLACES_M) pts.push(m.getLatLng());
    }
    if (what === 'all' && walkerAt) pts.push(ll(walkerAt));
    if (what === 'places' && layers.places) pts.push(layers.places.getBounds());
    if (what === 'hazard' && layers.hazard?.getBounds) pts.push(layers.hazard.getBounds());
    const b = L.latLngBounds([]);
    for (const p of pts) if (p && (!p.isValid || p.isValid())) b.extend(p);
    return b.isValid() ? b : null;
  }

  function fit(what = 'all') {
    const b = boundsOf(what) ?? boundsOf('all');
    if (!b) return;
    map.invalidateSize();
    if (b.getNorthEast().equals(b.getSouthWest())) map.setView(b.getCenter(), 17);
    else map.fitBounds(b, { paddingTopLeft: [48, 48], paddingBottomRight: [48, 56], maxZoom: 17 });
    orient();
  }

  const controller = {
    map,
    setHome(at, text = 'Home') {
      if (!isPoint(at)) return;
      homeAt = at;
      const m = divMarker(at, 'lm-home', '<span></span>', 'lm-marks', [22, 22]);
      homeText = text;
      label(m, esc(text), 'lm-label-home', sideAwayFrom(at, routeData?.destination));
      replace('home', m);
      orient();
    },
    setHazard(area) {
      hazardArea = area ?? null;
      if (region === 'jp') {
        replace('hazard', L.tileLayer(JP_TSUNAMI_URL, {
          opacity: 0.6, maxNativeZoom: 17, maxZoom: 19, attribution: JP_ATTR, pane: 'lm-hazard', className: 'lm-jp-tsunami',
        }));
      } else {
        const polys = (area?.polygons ?? [])
          .map((poly) => (poly ?? []).map((ring) => (ring ?? []).filter(isPoint).map(ll)).filter((ring) => ring.length >= 3))
          .filter((poly) => poly.length);
        replace('hazard', polys.length ? L.polygon(polys, {
          pane: 'lm-hazard', className: 'lm-hazard', interactive: false, color: '#FF7A1A', weight: 2, fillOpacity: 0.2,
        }) : null);
      }
      drawExit();
    },
    setRoute(input) {
      const path = (input?.path ?? []).filter(isPoint);
      const route = input && {
        ...input, path,
        origin: isPoint(input.origin) ? input.origin : path[0],
        destination: isPoint(input.destination) ? input.destination : path[path.length - 1],
        steps: (input.steps ?? []).filter((st) => st && Number.isFinite(st.distance_m)),
      };
      routeData = route && path.length >= 2 ? route : null;
      const group = L.featureGroup();
      if (routeData && (route.kind === 'walking_route' || route.kind === 'site_route')) {
        const line = route.path.map(ll);
        L.polyline(line, { pane: 'lm-route', className: 'lm-route-casing', interactive: false, weight: 10, color: '#17150F' }).addTo(group);
        L.polyline(line, { pane: 'lm-route', className: 'lm-route-line', interactive: false, weight: 5, color: '#FFC629' }).addTo(group);
        const pts = stepPoints(route);
        pts.slice(1, -1).filter((p) => isPoint(p.at)).forEach((p) =>
          divMarker(p.at, 'lm-turn', `<span>${p.index + 1}</span>`, 'lm-marks', [22, 22])
            .bindTooltip(esc(p.instruction), { direction: 'top', className: 'lm-label', offset: [0, -10] }).addTo(group));
        const site = route.kind === 'site_route' ? route.site : null;
        const dest = divMarker(route.destination, 'lm-dest', '<span></span>', 'lm-marks', [20, 20]);
        const name = site ? esc(site.name) : 'Outside the hazard area';
        label(dest, `${name}<br>${walkText(route.walk_min)}`, 'lm-label-dest', sideAwayFrom(route.destination, route.origin));
        dest.addTo(group);
      } else if (route?.kind === 'direction_only' && isPoint(route.origin) && Number.isFinite(route.bearing_deg)) {
        const end = destinationPoint(route.origin, route.bearing_deg, Math.min(route.straight_m ?? 500, 1500));
        L.polyline([ll(route.origin), ll(end)], { pane: 'lm-route', className: 'lm-route-bearing', interactive: false, weight: 4, dashArray: '10 8', color: '#17150F' }).addTo(group);
        const arrow = divMarker(end, 'lm-arrow', `<span style="transform: rotate(${route.bearing_deg}deg)"></span>`, 'lm-marks', [26, 26]);
        label(arrow, `Head ${esc(route.compass)}`, 'lm-label-dest');
        arrow.addTo(group);
      }
      replace('route', group.getLayers().length ? group : null);
      if (homeAt) controller.setHome(homeAt, homeText);
      drawExit();
    },
    setPlaces(list) {
      const group = L.featureGroup();
      const few = (list ?? []).length <= 3;
      for (const p of (list ?? []).filter((q) => q && Number.isFinite(q.lon) && Number.isFinite(q.lat))) {
        const m = divMarker([p.lon, p.lat], `lm-place lm-place-${p.kind}`, '<span></span>', 'lm-marks', [20, 20]);
        if (few) label(m, esc(p.label), 'lm-label-place', homeAt && p.lon < homeAt[0] ? 'left' : 'right');
        else m.bindTooltip(esc(p.label), { className: 'lm-label lm-label-place' });
        m.addTo(group);
      }
      replace('places', group.getLayers().length ? group : null);
      orient();
    },
    // `note` is a short callout shown beside the dot (the next turn); `follow` keeps the dot in view.
    setWalker(at, { note = null, follow: keep = follow } = {}) {
      if (!isPoint(at)) at = null;
      walkerAt = at;
      follow = keep;
      if (!at) { replace('walker', null); return; }
      if (!layers.walker) {
        layers.walker = divMarker(at, 'lm-walker', '<span class="lm-walker-halo"></span><span class="lm-walker-dot"></span>', 'lm-walker', [28, 28]).addTo(map);
      } else {
        layers.walker.setLatLng(ll(at));
      }
      const tip = layers.walker.getTooltip();
      if (note && !tip) label(layers.walker, esc(note), 'lm-callout', 'top').openTooltip();
      else if (note) tip.setContent(esc(note));
      else if (tip) layers.walker.unbindTooltip();
      if (follow && !map.getBounds().pad(-0.2).contains(ll(at))) map.panTo(ll(at), { animate: false });
    },
    highlight(what, text) {
      fit(what);
      card.hidden = !text;
      card.textContent = text ?? '';
    },
    fit,
    destroy() { resize.disconnect(); map.remove(); card.remove(); container.classList.remove('livemap'); },
  };
  return controller;
}
