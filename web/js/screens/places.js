import { h, icon, localTime, sampleTag } from '../dom.js';
import { evacSign, tsunamiSign } from '../art/signs.js';
import { placeSeal } from '../art/seal.js';
import { formatDistance } from '../geometry.js';
import { hazardLevel, nearestPlace } from '../places.js';
import { motionAvailable, startStandby, stopStandby } from '../standby.js';
import { NEEDS, flagList, routeView, shelterSection } from './parts.js';
import { roomResult } from './prepare.js';

// Standby lives here: while this screen is on the page the phone listens for sustained shaking and, with one
// low-accuracy fix, knows which saved place is nearest. Both only open the shaking screen, which moves nobody.

const KIND_TEXT = { home: 'Home', work: 'Work', school: 'School', other: 'Place' };
const KIND_SEAL = { home: '家', work: '職', school: '校', other: '備' };

let fix = null;
let fixAsked = false;

function askFix(onFix) {
  if (fixAsked || !('geolocation' in navigator)) return;
  fixAsked = true;
  navigator.geolocation.getCurrentPosition(
    (p) => { fix = { lonlat: [p.coords.longitude, p.coords.latitude], at: Date.now() }; onFix(); },
    () => {},
    { enableHighAccuracy: false, maximumAge: 300000, timeout: 15000 });
}

function standbyHeader(state, act) {
  const near = fix ? nearestPlace(state.places, fix.lonlat) : null;
  const first = near?.place ?? state.places[0];
  const line = near
    ? `Nearest: ${first.name}, ${formatDistance(near.distance_m)} away`
    : first ? `${first.name} is mapped` : 'No place mapped yet';
  const sensor = state.demo ? 'Demo: tap Simulate an earthquake below'
    : motionAvailable() ? 'Listening for strong shaking' : 'No motion sensor here; tap Emergency if the ground shakes';
  return h('header', { class: 'standby', 'aria-live': 'polite' },
    h('div', { class: 'standby-row' },
      h('span', { class: 'standby-pulse', 'aria-hidden': 'true' }),
      h('div', { class: 'standby-words' },
        h('p', { class: 'standby-title' }, 'Standing by'),
        h('p', { class: 'standby-line' }, line),
        h('p', { class: 'standby-sensor fine' }, sensor)),
      h('button', { class: 'standby-sos', onclick: () => { stopStandby(); act.go('emergency'); } }, 'Emergency')));
}

function placeRow(place, act) {
  const lvl = hazardLevel(place);
  const plan = place.plan;
  const rooms = plan?.rooms?.length ?? 0;
  const b = plan?.building;
  return h('li', null,
    h('button', { class: `place-row sev-${lvl.sev}`, onclick: () => act.openPlace(place.id) },
      placeSeal(KIND_SEAL[place.kind] ?? KIND_SEAL.other, 'seal place-seal'),
      h('div', { class: 'place-body' },
        h('p', { class: 'place-name' }, place.name, place.demo ? h('span', { class: 'tag-demo' }, 'Demo') : null, sampleTag(b)),
        h('p', { class: 'place-addr fine' }, b?.address ?? 'Address not checked'),
        h('p', { class: `place-flag sev-${lvl.sev}` }, lvl.sev === 4 ? tsunamiSign('sign place-flag-sign') : null, lvl.text),
        h('p', { class: 'place-meta fine mono' },
          `${rooms} room${rooms === 1 ? '' : 's'}`, plan?.route?.kind === 'walking_route' ? `, way out ${Math.round(plan.route.walk_min)} min` : '',
          `, updated ${localTime(place.saved_at ?? plan?.generated_at)}`)),
      h('span', { class: 'place-chevron', 'aria-hidden': 'true' }, '›')));
}

export function renderPlaces(state, act) {
  const root = h('div', { class: 'screen places' });
  const render = () => root.replaceChildren(...[
    state.demo ? h('div', { class: 'demo-banner', role: 'status' }, 'DEMO', h('button', { onclick: () => act.exitDemo() }, 'Exit demo')) : null,
    standbyHeader(state, act),
    h('main', { class: 'stack' },
      h('h1', { class: 'title places-title' }, 'My places'),
      state.places.length
        ? h('ul', { class: 'place-list' }, state.places.map((p) => placeRow(p, act)))
        : h('p', { class: 'lede' }, 'Map a place once. SafeZone then stands by for shaking and talks you through what to do.'),
      h('div', { class: 'places-actions' },
        h('button', { class: 'btn', onclick: () => act.go('new_place') }, 'Map a new place'),
        state.demo && state.places.length
          ? h('button', { class: 'btn-ghost btn-demo', onclick: () => act.simulateQuake() }, h('span', { class: 'tag-demo' }, 'Demo'), 'Simulate an earthquake')
          : null),
      h('p', { class: 'fine' }, 'Standby uses the motion sensor only while this screen is open. A planning aid, not an official warning system.')),
  ].filter(Boolean));
  render();
  askFix(() => { if (root.isConnected) render(); });
  startStandby({ onQuake: () => act.go('emergency'), isArmed: () => root.isConnected });
  return root;
}

function photoCard(title, imageUrl, caption) {
  if (!imageUrl) return null;
  return h('figure', { class: 'card ref-shot' },
    h('img', { src: imageUrl, alt: title }),
    h('figcaption', null, h('strong', null, title), ' ', caption));
}

function goBagCard(check) {
  return h('section', { class: 'card stack' },
    h('div', { class: 'card-head' }, h('h2', { class: 'section-title' }, 'Go bag'), sampleTag(check)),
    h('p', { class: 'fine' }, `${check.seen_count} of ${check.total} basic-kit items seen in the photo. Items out of view may still be packed.`),
    h('ul', { class: 'gobag' }, check.items.map((it) =>
      h('li', { class: it.seen ? 'seen' : 'unseen' }, icon(it.seen ? 'check' : 'question', 'icon-inline'),
        h('span', null, it.label), h('span', { class: 'fine' }, it.seen ? ' Seen in the photo' : ' Not seen')))),
    h('p', { class: 'fine mono' }, `Checked by ${check.model}. List from Ready.gov.`));
}

export function renderPlace(state, act) {
  const place = state.places.find((p) => p.id === state.activePlaceId);
  if (!place) {
    return h('div', { class: 'screen place' }, h('p', { class: 'error', role: 'alert' }, 'This place is no longer saved.'),
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, '‹ My places'));
  }
  const plan = place.plan;
  const g = state.guidance;
  const route = plan.route;
  const inZone = route && route.kind !== 'not_in_zone';
  const lvl = hazardLevel(place);
  const needs = NEEDS.filter(([k]) => plan.household?.[k]);
  const extras = plan.extras ?? {};
  return h('div', { class: 'screen place' },
    state.demo || place.demo ? h('div', { class: 'demo-banner', role: 'status' }, 'DEMO: recorded real data for 1000 Great Highway') : null,
    h('header', { class: 'place-head' },
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, '‹ My places'),
      h('div', { class: 'place-head-row' },
        placeSeal(KIND_SEAL[place.kind] ?? KIND_SEAL.other, 'seal place-seal-big'),
        h('div', null,
          h('p', { class: 'label' }, KIND_TEXT[place.kind] ?? 'Place'),
          h('h1', { class: 'title' }, place.name),
          plan.building ? h('p', { class: 'fine' }, plan.building.address) : null)),
      h('p', { class: `place-flag place-flag-big sev-${lvl.sev}` }, lvl.sev === 4 ? tsunamiSign('sign place-flag-sign') : null, lvl.text)),
    h('main', { class: 'stack' },
      h('section', { class: 'card stack' },
        h('h2', { class: 'section-title' }, 'During shaking'),
        h('p', { class: 'dch-words' }, 'Drop. Cover. Hold on.'),
        g ? h('ol', { class: 'steps-list' }, g.during.map((t) => h('li', null, t))) : null,
        plan.rooms.length ? h('ul', { class: 'spot-summary' }, plan.rooms.map((r) =>
          h('li', null, h('strong', null, r.name), h('span', null, r.spots[0]?.instruction)))) : null),
      h('section', { class: 'card stack' },
        h('h2', { class: 'section-title' }, 'When the shaking stops'),
        inZone ? h('p', { class: 'go-now' }, g?.go_now) : null,
        route?.kind === 'not_in_zone' ? h('p', { class: 'calm-strong' }, g?.not_in_zone ?? route.reason) : null,
        !route ? h('p', { class: 'notice' }, 'The tsunami hazard map was not available when this place was saved. Follow official instructions.') : null,
        g ? h('ol', { class: 'steps-list' }, g.after.map((t) => h('li', null, t))) : null),
      inZone ? h('section', { class: 'card stack' },
        h('div', { class: 'card-head' }, evacSign('sign'), h('h2', { class: 'section-title' }, 'Way out of the hazard area')),
        routeView(route, plan.building),
        h('p', { class: 'fine' }, 'In an emergency SafeZone reads these turns aloud as you walk.')) : null,
      inZone || plan.shelters ? h('section', { class: 'card stack' },
        h('h2', { class: 'section-title' }, 'Shelters that fit your household'),
        shelterSection(plan, plan.shelters_error)) : null,
      photoCard('The way out', state.images[extras.exit], 'Saved on this device for offline reference.'),
      photoCard('Gas shutoff', state.images[extras.gas], 'Turn gas off only if you smell gas or hear it hissing.'),
      extras.gobag ? goBagCard(extras.gobag) : null,
      plan.building ? h('section', { class: 'card stack' },
        h('div', { class: 'card-head' }, h('h2', { class: 'section-title' }, 'Building'), sampleTag(plan.building)),
        flagList(plan.building)) : null,
      h('section', { class: 'card stack' },
        h('h2', { class: 'section-title' }, 'Household'),
        needs.length ? h('ul', { class: 'need-chips' }, needs.map(([k, label]) => h('li', null, icon(k, 'icon-inline'), label)))
          : h('p', { class: 'fine' }, 'No special needs selected.')),
      h('section', { class: 'stack' },
        h('h2', { class: 'section-title' }, 'Rooms and fixes'),
        plan.rooms.map((room) => roomResult(room, state, act, place.id))),
      h('div', { class: 'places-actions' },
        h('button', { class: 'btn', onclick: () => act.go('add_shots') }, 'Add photos'),
        h('button', { class: 'btn-ghost', onclick: () => window.print() }, 'Print fridge sheet'),
        h('button', { class: 'btn-text', onclick: () => act.deletePlace(place.id) }, 'Delete this place'))));
}
