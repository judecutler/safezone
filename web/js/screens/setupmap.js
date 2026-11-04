import { h } from '../dom.js';

// The live map beside setup. Each background job (location, hazard check, route, shelters) becomes a finding as it
// finishes; the map reveals it with a label card and the list under the map grows. Map views outlive app renders:
// they sit in `views`, keyed by slot, and only new findings touch them.

export const WIDE = '(min-width: 1024px)';
export const isWide = () => window.matchMedia?.(WIDE).matches ?? false;

const REVEAL_GAP_MS = 1500;
const SEV = { ok: 1, unknown: 2, info: 2, alert: 4 };
const views = {};

const shortAddress = (b) => (b.address ?? b.display_name ?? '').split(',').slice(0, 2).join(',').trim();
const round10 = (m) => Math.round(m / 10) * 10;

// What the person is shown as theirs. A demo with a real location lookup keeps DEMO on the photos only.
const usesDemoLocation = (session) => session.demo && !session.location.real;

function tagFor(session, obj) {
  if (obj?.provenance === 'sample') return 'SAMPLE';
  return usesDemoLocation(session) ? 'DEMO' : null;
}

function hazardFinding(session, b) {
  const flag = b.flags?.find((f) => f.kind === 'tsunami_zone');
  if (!flag) return null;
  const inside = flag.tone === 'alert';
  const us = (b.region ?? 'us-ca') === 'us-ca';
  const title = us
    ? (inside ? "Inside California's tsunami hazard area" : flag.tone === 'ok' ? "Outside California's tsunami hazard area" : flag.value)
    : flag.value;
  return { id: 'hazard', card: title, title, detail: flag.detail, source: flag.source_name, sev: SEV[flag.tone] ?? 2, tag: tagFor(session, flag) };
}

function routeFinding(session, route) {
  if (route?.kind === 'walking_route' || route?.kind === 'site_route') {
    const to = route.kind === 'site_route' ? route.site?.name ?? 'the evacuation site' : 'high ground';
    const title = `Checked route to ${to}: ${Math.round(route.walk_min)} min, ${round10(route.distance_m)} m`;
    const source = route.kind === 'site_route' && route.site?.source_name
      ? `Walking paths from OpenStreetMap; destination from ${route.site.source_name}`
      : 'Walking paths from OpenStreetMap, routed by OSRM, checked against the hazard map';
    return { id: 'route', card: title, title, source, tag: tagFor(session, route) };
  }
  if (route?.kind === 'direction_only') {
    const title = `No mapped path. Head ${route.compass} for ${round10(route.straight_m)} m`;
    return { id: 'route', card: title, title, source: 'Straight line to the edge of the hazard area', tag: tagFor(session, route) };
  }
  return null;
}

function placesFinding(session, shelters, region) {
  if (!shelters) return null;
  const n = shelters.matches.length;
  const jp = region === 'jp';
  const title = jp
    ? `${n} designated evacuation site${n === 1 ? '' : 's'} nearby`
    : n ? `${n} shelter${n === 1 ? '' : 's'} that fit your household` : 'No open shelter fits your household yet';
  const source = jp ? 'GSI designated emergency evacuation sites' : 'FEMA National Shelter System open shelters';
  return { id: 'places', card: title, title, source, tag: tagFor(session, shelters) };
}

// The findings so far, in the order they are revealed.
export function findings(session) {
  const loc = session?.location;
  if (loc?.status !== 'found') return [];
  const b = loc.building;
  const region = b.region ?? 'us-ca';
  const out = [{
    id: 'home', card: `Found: ${(b.address ?? '').split(',')[0]}`, title: `Found: ${shortAddress(b)}`,
    source: loc.real ? 'Your device location, matched to OpenStreetMap' : b.provenance === 'recorded' ? 'Demo address, recorded lookup' : 'Address lookup via OpenStreetMap',
    tag: tagFor(session, b),
  }];
  const hazard = hazardFinding(session, b);
  if (hazard) out.push(hazard);
  if (session.evac?.status === 'done') {
    const route = routeFinding(session, session.evac.route);
    if (route) out.push(route);
    const places = placesFinding(session, session.evac.shelters, region);
    if (places) out.push(places);
  }
  return out;
}

// The one line that says what is still being looked up, so the panel never sits silent.
function pendingLine(session) {
  const loc = session?.location;
  if (!loc || loc.status === 'idle') return 'Waiting for your location';
  if (loc.status === 'locating') return 'Finding your location…';
  if (loc.status === 'failed') return 'No location yet. Type the address to see the map.';
  if (session.evac?.status === 'working') return 'Checking walking routes and shelters…';
  if (session.evac?.status === 'failed') return 'The route lookup did not finish. It runs again when you save.';
  return null;
}

function applyToMap(ctrl, f, session) {
  const b = session.location.building;
  if (f.id === 'home') ctrl.setHome([b.lon, b.lat], 'Home');
  if (f.id === 'hazard') ctrl.setHazard(b.hazard_area ?? { polygons: [], land_polygons: [] });
  if (f.id === 'route') ctrl.setRoute(session.evac.route);
  if (f.id === 'places') {
    const kind = (b.region ?? 'us-ca') === 'jp' ? 'site' : 'shelter';
    ctrl.setPlaces(session.evac.shelters.matches.map((m) => ({ lon: m.shelter.lon, lat: m.shelter.lat, label: m.shelter.name, kind })));
  }
}

function findingRow(f) {
  return h('li', { class: `sf-item${f.sev ? ` sev-${f.sev}` : ''}`, 'data-finding': f.id },
    h('span', { class: 'sf-mark', 'aria-hidden': 'true' }),
    h('div', { class: 'sf-body' },
      h('p', { class: 'sf-title' }, f.title, f.tag ? h('span', { class: f.tag === 'SAMPLE' ? 'tag-sample' : 'tag-demo' }, f.tag === 'SAMPLE' ? 'Sample data' : 'Demo') : null),
      f.sev ? h('span', { class: 'sf-sev', role: 'img', 'aria-label': `Severity ${f.sev} of 4` },
        [1, 2, 3, 4].map((i) => h('span', { class: i <= f.sev ? 'on' : '' }))) : null,
      h('p', { class: 'sf-source mono' }, f.source)));
}

function newView(slot) {
  const mapBox = h('div', { class: 'sf-map', 'aria-label': 'Map of what SafeZone found', role: 'img' });
  const list = h('ol', { class: 'sf-list', 'aria-live': 'polite' });
  const pending = h('p', { class: 'sf-pending' }, h('span', { class: 'pulse-dot' }), h('span', null));
  const root = h('section', { class: `setup-map setup-map-${slot}` },
    mapBox,
    h('div', { class: 'sf-panel' },
      h('p', { class: 'label sf-head' }, 'What SafeZone found'),
      list, pending));
  return { slot, root, mapBox, list, pending, key: null, ctrl: null, ready: null, shown: new Set(), queue: [], timer: 0 };
}

// A new place (another session, or a real location replacing the demo one) starts the map over.
function reset(view, key, region) {
  clearTimeout(view.timer);
  view.ctrl?.destroy();
  Object.assign(view, { key, ctrl: null, shown: new Set(), queue: [], timer: 0 });
  view.list.replaceChildren();
  const box = h('div', { class: 'sf-map-inner' });
  view.mapBox.replaceChildren(box);
  view.ready = import('../livemap.js')
    .then(({ liveMap }) => liveMap(box, { region, interactive: view.slot === 'side' }))
    .then((ctrl) => { if (view.key === key) view.ctrl = ctrl; else ctrl.destroy(); return ctrl; })
    .catch(() => null);
}

// Findings are drawn as soon as they arrive; the camera visits them one at a time so each label can be read.
function drain(view) {
  if (view.timer || !view.queue.length) return;
  const key = view.key;
  view.ready.then((ctrl) => {
    if (!ctrl || view.key !== key || view.timer) return;
    const step = () => {
      const f = view.queue.shift();
      if (view.key !== key) { view.timer = 0; return; }
      // After the last reveal the camera pulls back to show everything found, keeping the last label.
      if (!f) { view.timer = 0; ctrl.fit('all'); return; }
      applyToMap(ctrl, f, view.session);
      ctrl.highlight(f.id, f.card);
      view.timer = setTimeout(step, REVEAL_GAP_MS);
    };
    step();
  });
}

function sync(view, session) {
  const b = session?.location?.status === 'found' ? session.location.building : null;
  const key = `${session?.id}:${b ? `${b.lon},${b.lat}` : 'none'}`;
  if (view.key !== key) reset(view, key, b?.region ?? 'us-ca');
  view.mapBox.classList.toggle('is-empty', !b);
  for (const f of findings(session)) {
    if (view.shown.has(f.id)) continue;
    view.shown.add(f.id);
    view.list.append(findingRow(f));
    view.queue.push(f);
  }
  const text = pendingLine(session);
  view.pending.hidden = !text;
  view.pending.lastChild.textContent = text ?? '';
  view.session = session;
  drain(view);
}

function viewFor(slot, session) {
  views[slot] ??= newView(slot);
  sync(views[slot], session);
  return views[slot].root;
}

// Wide screens: the map on the left, the setup screen on the right. The split and the map persist across renders,
// so only the right side is replaced.
export function mountSetup(root, state, screenEl) {
  const side = viewFor('side', state.session);
  let split = root.firstElementChild?.classList.contains('setup-split') ? root.firstElementChild : null;
  if (!split) {
    split = h('div', { class: 'setup-split' }, side, h('div', { class: 'setup-main' }));
    root.replaceChildren(split);
  }
  const main = split.lastElementChild;
  if (main.dataset.screen !== state.screen) main.scrollTop = 0;
  main.dataset.screen = state.screen;
  main.replaceChildren(screenEl);
}

// Narrow screens: the same findings as a card at the top of the review screen.
export function findingsCard(state) {
  return viewFor('card', state.session);
}

export function demoBannerText(state, fallback) {
  return state.session?.location?.real ? 'DEMO: recorded photos. Your location was looked up live.' : fallback;
}
