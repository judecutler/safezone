import { h } from '../dom.js';
import { formatDistance } from '../geometry.js';
import { OFF_ROUTE_M, cue, insideHazard, pointAlong, progress, routeLength } from '../guide.js';
import { isMuted, keepAwake, onVoiceChange, repeat, say, setMuted, stopAll, vibrate } from '../voice.js';
import { TSUNAMI_MAP_MISSING, duringSpecials, routeView, shelterSection } from './parts.js';

// Everything shown or said here comes from state.emergency ({ place, guidance, images }, loaded from IndexedDB)
// and from guide.js. Spoken text is either the server's guidance verbatim, the saved spot instruction the
// server wrote from its fixed table, or a route step the server wrote, joined by the connectives in guide.js.
//
// One run spans shaking -> after -> shelters. `run.phase` is the spoken phase; a re-render of the same screen
// (mute toggle, position update) never restarts speech, and leaving a phase stops everything it started.

const REPEAT_MS = 15000;
const WALK_MPS = 1.4;
const SETTLE_MS = 3000;
const DEMO_SPEEDS = [1, 8];

// `ui` holds the live elements of the current render; a re-render swaps them without restarting the phase.
const run = { phase: null, stops: [], openedAt: 0, demoSpeed: 1, ui: null };

// A re-render inside the same phase swaps the live elements and leaves speech and position sources alone.
function enterPhase(phase, ui, start) {
  if (run.phase === phase) { run.ui = ui; return; }
  leavePhase();
  run.phase = phase;
  run.ui = ui;
  start();
}

function leavePhase() {
  for (const stop of run.stops.splice(0)) stop();
  run.phase = null;
  run.ui = null;
  stopAll();
}

function onStop(fn) { if (fn) run.stops.push(fn); }

const planOf = (em) => em?.place?.plan ?? em?.saved?.plan ?? null;
// Only demo mode itself simulates. A saved demo place outside demo mode gets real GPS like any other place.
const demoPrefix = (state) => (state.demo ? 'This is a demo. ' : '');

// What the shaking screen says: Drop, Cover, Hold On and the saved spot instruction for the nearest place's
// first room. Nothing here moves anyone; the spot instruction is the server's fixed wording.
export function shakingLine(em) {
  const plan = planOf(em);
  const spot = plan?.rooms?.[0]?.spots?.[0]?.instruction;
  return spot ? `Drop, cover and hold on. ${spot}` : 'Drop, cover and hold on.';
}

function muteButton() {
  const btn = h('button', { class: 'em-mute', 'aria-pressed': String(isMuted()), onclick: (e) => { e.stopPropagation(); setMuted(!isMuted()); } });
  const paint = (m) => { btn.textContent = m ? 'Voice off' : 'Voice on'; btn.setAttribute('aria-pressed', String(m)); };
  paint(isMuted());
  onStop(onVoiceChange(paint));
  return btn;
}

function exitLink(act) {
  return h('button', { class: 'em-exit', onclick: (e) => { e.stopPropagation(); leavePhase(); act.go('exit_emergency'); } }, 'Leave emergency mode');
}

function demoTag(text = 'Demo') {
  return h('span', { class: 'tag-demo' }, text);
}

function shaking(state, act) {
  const em = state.emergency;
  const plan = planOf(em);
  const guidance = em?.guidance;
  enterPhase('shaking', {}, () => {
    run.openedAt = Date.now();
    onStop(keepAwake());
    vibrate([300, 150, 300, 150, 300]);
    const prefix = demoPrefix(state);
    if (prefix) say(prefix.trim(), { interrupt: true });
    onStop(repeat(shakingLine(em), REPEAT_MS));
  });
  const stopped = () => {
    if (Date.now() - run.openedAt < SETTLE_MS) return;
    leavePhase();
    act.go('stopped');
  };
  return h('main', { class: 'em em-shaking', onclick: stopped },
    state.demo ? h('div', { class: 'demo-banner', role: 'status' }, 'DEMO: simulated earthquake') : null,
    h('div', { class: 'em-top' }, muteButton()),
    h('h1', { class: 'em-dch' }, h('span', null, 'Drop.'), h('span', null, 'Cover.'), h('span', null, 'Hold on.')),
    plan?.rooms?.length ? h('section', { class: 'em-spots' },
      h('h2', { class: 'em-label' }, `Your spots at ${em.place?.name ?? 'home'}`),
      plan.rooms.map((r) => h('div', { class: 'em-spot' }, h('h3', null, r.name), h('p', null, r.spots[0]?.instruction))))
      : h('p', { class: 'em-muted' }, 'No saved place on this device.'),
    guidance ? h('ol', { class: 'em-steps' }, guidance.during.map((t) => h('li', null, t))) : null,
    duringSpecials(plan, guidance).map((t) => h('p', { class: 'em-special' }, t)),
    h('div', { class: 'em-dock' },
      h('p', { class: 'em-tap-hint fine' }, 'Tap anywhere when it stops'),
      h('button', { class: 'em-big', onclick: (e) => { e.stopPropagation(); stopped(); } }, 'Shaking has stopped'),
      exitLink(act)));
}

// Position sources. Each takes a callback and returns a stop function. The demo walker follows the server's
// path at walking pace and is labelled wherever it is shown.
function gpsSource(onFix, onStatus) {
  if (!('geolocation' in navigator)) { onStatus('Location is not available on this device. Follow the turns on the map.'); return null; }
  const id = navigator.geolocation.watchPosition(
    (p) => onFix([p.coords.longitude, p.coords.latitude], `Live position, within ${Math.round(p.coords.accuracy)} m`, p.coords.accuracy),
    () => onStatus('Location is off. Follow the turns on the map.'),
    { enableHighAccuracy: true, maximumAge: 3000, timeout: 20000 });
  return () => navigator.geolocation.clearWatch(id);
}

function walkerSource(route, onFix) {
  const total = routeLength(route);
  let m = 0;
  const started = performance.now();
  let last = started;
  const tick = () => {
    const now = performance.now();
    m = Math.min(total, m + ((now - last) / 1000) * WALK_MPS * run.demoSpeed);
    last = now;
    onFix(pointAlong(route, m), `Demo walker, ${formatDistance(m)} of ${formatDistance(total)}, ${run.demoSpeed}x`);
    if (m >= total) clearInterval(id);
  };
  const id = setInterval(tick, 1000);
  tick();
  return () => clearInterval(id);
}

function after(state, act) {
  const em = state.emergency;
  const plan = planOf(em);
  const guidance = em?.guidance;
  const route = plan?.route ?? null;
  const moving = route && route.kind !== 'not_in_zone';
  const afterSteps = guidance ? h('ol', { class: 'em-steps em-steps-small' }, guidance.after.map((t) => h('li', null, t))) : null;
  const noPlanLine = 'No saved place on this device. Follow official instructions. If the shaking was strong or lasted a long time and you are near the coast, move inland and uphill now.';

  const firstTurn = route?.steps?.[0] ? `${route.steps[0].instruction}, then ${route.steps.length - 1} more turns` : '';
  const nextLine = h('p', { class: 'em-next', 'aria-live': 'assertive' }, run.ui?.nextLine?.textContent || firstTurn);
  const positionLine = h('p', { class: 'em-pos mono', 'aria-live': 'polite' },
    run.ui?.positionLine?.textContent ?? (moving && route.kind === 'walking_route' ? 'Finding your position' : ''));
  enterPhase('after', { nextLine, positionLine, map: null }, () => {
    onStop(keepAwake());
    const prefix = demoPrefix(state);
    if (!plan) { say(prefix + noPlanLine, { interrupt: true }); return; }
    if (!route) { say(prefix + TSUNAMI_MAP_MISSING, { interrupt: true }); return; }
    if (route.kind === 'not_in_zone') { say(prefix + (guidance?.not_in_zone ?? route.reason), { interrupt: true }); return; }
    say(prefix + (guidance?.go_now ?? 'Go now, on foot, inland or to high ground.'), { interrupt: true });
    if (route.kind !== 'walking_route') { say(route.reason); return; }

    const hazard = plan.building?.hazard_area?.polygons ?? null;
    let prev = null, last = null;
    const onFix = (lonlat, status, accuracyM = 0) => {
      const prog = progress(route, lonlat, prev);
      prev = prog;
      const shown = run.ui.map?.showPosition(lonlat);
      run.ui.positionLine.textContent = shown === false ? `${status}. You are outside this map.` : status;
      const c = cue(route, prog, last, { outsideHazard: hazard ? !insideHazard(hazard, lonlat) : null, accuracyM });
      if (c) {
        last = c;
        say(c.text, { replace: true });
        vibrate(c.key === 'arrive' ? [200, 100, 200, 100, 600] : [120]);
        if (c.key === 'arrive' && guidance?.stay_away) say(guidance.stay_away);
      }
      run.ui.nextLine.textContent = prog.arrived ? 'End of the route' : prog.offRouteM > OFF_ROUTE_M + accuracyM
        ? `Off the route, ${formatDistance(prog.offRouteM)} to your ${prog.bearingToRoute}`
        : prog.metersToNext < 5 ? route.steps[prog.stepIndex]?.instruction ?? ''
          : `${route.steps[prog.stepIndex]?.instruction ?? ''} in ${formatDistance(prog.metersToNext)}`;
    };
    const source = state.demo
      ? walkerSource(route, onFix)
      : gpsSource(onFix, (text) => { run.ui.positionLine.textContent = text; });
    onStop(source);
  });

  let body;
  if (!plan) body = [h('p', { class: 'em-calm' }, noPlanLine), afterSteps];
  else if (!route) body = [h('p', { class: 'em-calm' }, TSUNAMI_MAP_MISSING), afterSteps];
  else if (route.kind === 'not_in_zone') body = [h('p', { class: 'em-calm' }, guidance?.not_in_zone ?? route.reason), afterSteps];
  else {
    const demo = state.demo;
    const view = routeView(route, plan.building, { onMap: (m) => { run.ui.map = m; } });
    const speedBtn = demo ? h('button', { class: 'em-speed', onclick: () => {
      run.demoSpeed = DEMO_SPEEDS[(DEMO_SPEEDS.indexOf(run.demoSpeed) + 1) % DEMO_SPEEDS.length];
      speedBtn.textContent = `Walker speed ${run.demoSpeed}x`;
    } }, `Walker speed ${run.demoSpeed}x`) : null;
    body = [
      route.kind === 'walking_route' ? h('div', { class: 'em-turn' },
        h('p', { class: 'em-label' }, 'Next'), nextLine,
        h('div', { class: 'em-pos-row' }, demo ? demoTag('Demo walker') : null, positionLine, speedBtn)) : null,
      h('p', { class: route.kind === 'walking_route' ? 'em-go em-go-small' : 'em-go' }, guidance?.go_now ?? 'Go now, on foot, inland or to high ground.'),
      view,
      guidance ? h('p', { class: 'em-muted' }, guidance.stay_away) : null,
      h('h2', { class: 'em-label' }, 'Also'),
      afterSteps,
    ];
  }
  return h('main', { class: 'em em-after' },
    state.demo ? h('div', { class: 'demo-banner', role: 'status' }, 'DEMO: simulated walk along the recorded route') : null,
    h('div', { class: 'em-top' }, muteButton()),
    body,
    plan?.shelters
      ? h('button', { class: 'em-big em-big-outline', onclick: () => act.go('shelters') }, 'Shelters that fit your household')
      : moving ? h('p', { class: 'em-muted' }, 'Shelter data was unavailable when this place was saved. Follow official instructions for where to go.') : null,
    guidance ? h('ul', { class: 'em-disclaimers' }, guidance.disclaimers.map((d) => h('li', null, d))) : null,
    exitLink(act));
}

function shelters(state, act) {
  const plan = planOf(state.emergency);
  return h('main', { class: 'em em-shelters' },
    h('div', { class: 'em-top' }, muteButton()),
    h('h1', { class: 'em-title' }, 'Shelters that fit your household'),
    plan ? shelterSection(plan, plan.shelters_error) : h('p', { class: 'em-calm' }, 'No saved place on this device.'),
    h('button', { class: 'em-big em-big-outline', onclick: () => act.go('back') }, 'Back to the route'),
    exitLink(act));
}

const SCREENS = { shaking, after, shelters };

export function renderEmergency(state, act) {
  return h('div', { class: 'em-root' }, SCREENS[state.screen](state, act));
}

// For the integrator: call when the app leaves the emergency screens by any path (popstate included).
export function stopEmergency() {
  leavePhase();
}
