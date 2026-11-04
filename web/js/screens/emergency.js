import { h } from '../dom.js';
import { TSUNAMI_MAP_MISSING, duringSpecials, routeView, shelterSection } from './parts.js';

// Everything here comes from state.emergency, which is loaded from IndexedDB on entry.

let stopWatch = null;

function endWatch() {
  stopWatch?.();
  stopWatch = null;
}

function exitLink(act) {
  return h('button', { class: 'em-exit', onclick: () => { endWatch(); act.go('exit_emergency'); } }, 'Back to plan');
}

function shaking({ saved, guidance }, act) {
  const plan = saved?.plan;
  return h('main', { class: 'em em-shaking' },
    h('h1', { class: 'em-dch' }, h('span', null, 'Drop.'), h('span', null, 'Cover.'), h('span', null, 'Hold on.')),
    guidance ? h('ol', { class: 'em-steps' }, guidance.during.map((t) => h('li', null, t))) : null,
    plan?.rooms?.length ? h('section', { class: 'em-spots' },
      h('h2', { class: 'em-label' }, 'Your safe spots'),
      plan.rooms.map((r) => h('div', { class: 'em-spot' }, h('h3', null, r.name), h('p', null, r.spots[0]?.instruction))))
      : h('p', { class: 'em-muted' }, 'No saved plan on this device.'),
    duringSpecials(plan, guidance).map((t) => h('p', { class: 'em-special' }, t)),
    h('div', { class: 'em-dock' },
      h('button', { class: 'em-big', onclick: () => act.go('stopped') }, 'Shaking has stopped'),
      exitLink(act)));
}

function after({ saved, guidance }, act) {
  endWatch();
  const plan = saved?.plan;
  const route = plan?.route ?? null;
  const moving = route && route.kind !== 'not_in_zone';
  const afterSteps = guidance ? h('ol', { class: 'em-steps em-steps-small' }, guidance.after.map((t) => h('li', null, t))) : null;
  let body;
  if (moving) {
    const positionLine = h('p', { class: 'em-pos mono', 'aria-live': 'polite' }, 'Finding your position');
    const view = routeView(route, plan.building, {
      onMap: (map) => { stopWatch = watch(map, (text) => { positionLine.textContent = text; }); },
    });
    body = [
      h('p', { class: 'em-go' }, guidance?.go_now ?? 'Go now, on foot, inland or to high ground.'),
      view,
      route.kind === 'walking_route' ? positionLine : null,
      guidance ? h('p', { class: 'em-muted' }, guidance.stay_away) : null,
      h('h2', { class: 'em-label' }, 'Also'),
      afterSteps,
    ];
  } else if (route?.kind === 'not_in_zone') {
    body = [h('p', { class: 'em-calm' }, guidance?.not_in_zone ?? route.reason), afterSteps];
  } else {
    body = [h('p', { class: 'em-calm' }, plan ? TSUNAMI_MAP_MISSING : 'No saved plan on this device. Follow official instructions. If the shaking was strong or lasted a long time and you are near the coast, move inland and uphill now.'), afterSteps];
  }
  return h('main', { class: 'em em-after' },
    body,
    plan?.shelters
      ? h('button', { class: 'em-big em-big-outline', onclick: () => { endWatch(); act.go('shelters'); } }, 'Shelters that fit your household')
      : moving ? h('p', { class: 'em-muted' }, 'Shelter data was unavailable when this plan was made. Follow official instructions for where to go.') : null,
    guidance ? h('ul', { class: 'em-disclaimers' }, guidance.disclaimers.map((d) => h('li', null, d))) : null,
    exitLink(act));
}

function shelters({ saved }, act) {
  return h('main', { class: 'em em-shelters' },
    h('h1', { class: 'em-title' }, 'Shelters that fit your household'),
    shelterSection(saved.plan, saved.shelters_error),
    h('button', { class: 'em-big em-big-outline', onclick: () => act.go('back') }, 'Back to the route'),
    exitLink(act));
}

function watch(map, report) {
  if (!('geolocation' in navigator)) { report('Location is not available on this device. The map shows your home and the route.'); return null; }
  const id = navigator.geolocation.watchPosition(
    (p) => {
      const shown = map.showPosition([p.coords.longitude, p.coords.latitude]);
      const acc = `within ${Math.round(p.coords.accuracy)} m`;
      report(shown ? `Live position, ${acc}` : `You are outside this map (${acc}). Head for the route.`);
    },
    () => report('Location is off. The map shows your home and the route.'),
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
  return () => navigator.geolocation.clearWatch(id);
}

const SCREENS = { shaking, after, shelters };

export function renderEmergency(state, act) {
  return h('div', { class: 'em-root' }, SCREENS[state.screen](state.emergency, act));
}
