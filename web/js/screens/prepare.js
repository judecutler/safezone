import { EFFORT_TEXT, costText, h, icon, localTime, s, sampleTag } from '../dom.js';
import { hazardNumbers, roomOverlay } from '../overlay.js';
import {
  NEEDS, SPOT_KIND, TSUNAMI_MAP_MISSING, duringSpecials, flagList, routeView, shelterSection,
} from './parts.js';

const STEPS = [['address', 'Address'], ['household', 'Household'], ['rooms', 'Rooms'], ['plan', 'Plan']];
const RELATION_TEXT = {
  in_tip_zone: 'Tip zone', under_stored_items: 'Under stored items', near_glass: 'Near glass', blocks_exit: 'Blocks the way out',
};

function header(state, act) {
  const idx = STEPS.findIndex(([k]) => k === state.screen);
  return h('header', { class: 'bar' },
    h('div', { class: 'wordmark' }, icon('target', 'wordmark-icon'), 'SafeZone'),
    idx >= 0 ? h('ol', { class: 'steps', 'aria-label': 'Progress' }, STEPS.map(([k, label], i) =>
      h('li', { class: i < idx ? 'done' : i === idx ? 'now' : '', 'aria-current': i === idx ? 'step' : null },
        h('span', { class: 'step-n' }, i + 1), h('span', { class: 'step-label' }, label)))) : null,
    h('button', { class: 'btn-emergency', onclick: () => act.go('emergency') }, 'Emergency'));
}

const errorLine = (state) => state.ui.error ? h('p', { class: 'error', role: 'alert' }, icon('alert', 'icon-inline'), state.ui.error) : null;

function sheet(state, act, ...children) {
  return h('div', { class: 'sheet' }, header(state, act), h('main', { class: 'page' }, children));
}

function cancelLink(state, act) {
  return state.saved?.plan?.generated_at
    ? h('button', { class: 'btn-text', onclick: () => act.go('cancel') }, 'Discard changes and return to plan')
    : null;
}

// Fig. 1: the product in one drawing. Coast, hazard area, the home inside it, the way out uphill.
function heroFigure() {
  return h('figure', { class: 'hero-fig' },
    s('svg', { viewBox: '0 0 360 190', role: 'img', 'aria-label': 'A coastal home inside the tsunami hazard area, with a walking route uphill out of it' },
      s('defs', null, s('pattern', { id: 'hero-hatch', width: 7, height: 7, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' },
        s('line', { x1: 0, y1: 0, x2: 0, y2: 7, class: 'hero-hatch' }))),
      s('path', { d: 'M0 150 H40 L150 140 L230 118 L300 70 L360 52 V190 H0 Z', class: 'hero-ground' }),
      s('path', { d: 'M0 150 H40 L150 140 L196 128 V20 H0 Z', class: 'hero-zone', fill: 'url(#hero-hatch)' }),
      s('path', { d: 'M196 20 V128', class: 'hero-edge' }),
      s('path', { d: 'M0 146 q6 -5 12 0 t12 0 t12 0', class: 'hero-wave' }),
      s('path', { d: 'M0 136 q6 -5 12 0 t12 0 t12 0', class: 'hero-wave' }),
      s('path', { d: 'M104 144 V118 L120 104 L136 118 V142 Z M114 142 V128 H126 V141', class: 'hero-house' }),
      s('path', { d: 'M138 132 C180 126 220 112 262 84', class: 'hero-route' }),
      s('path', { d: 'M262 84 V48 L284 56 L262 64', class: 'hero-flag' }),
      s('text', { x: 8, y: 34, class: 'hero-label' }, 'TSUNAMI HAZARD AREA'),
      s('text', { x: 206, y: 34, class: 'hero-label hero-label-ink' }, 'HIGH GROUND'),
      s('text', { x: 98, y: 166, class: 'hero-label hero-label-ink' }, 'YOUR HOME')),
    h('figcaption', { class: 'mono fine' }, 'Fig. 1. Two jobs: survive the shaking, then walk out of the water’s way.'));
}

function startScreen(state, act) {
  const resuming = state.draft?.building || state.draft?.rooms?.length;
  return sheet(state, act,
    h('section', { class: 'hero' },
      h('h1', { class: 'display' }, 'Get your home ready for the next big earthquake.'),
      h('p', { class: 'lede' }, 'Photograph each room to find the safest spot and what could fall. When the shaking stops, SafeZone shows the way out of the tsunami zone, even with no signal.'),
      heroFigure(),
      h('div', { class: 'actions' },
        h('button', { class: 'btn btn-primary', onclick: () => act.go('begin') }, resuming ? 'Continue my plan' : 'Start my plan'),
        h('button', { class: 'btn', disabled: state.ui.busy === 'demo', onclick: () => act.loadDemo() },
          state.ui.busy === 'demo' ? 'Loading the demo household' : 'Load the demo household')),
      errorLine(state),
      h('p', { class: 'fine' }, 'Your photos and plan stay on this phone. SafeZone is a planning aid, not an official warning system.')));
}

function addressScreen(state, act) {
  const b = state.draft.building;
  const busy = state.ui.busy === 'address';
  const input = h('input', { id: 'address', name: 'address', type: 'text', autocomplete: 'street-address', required: true,
    value: b?.address ?? '', placeholder: 'Street, city, state' });
  return sheet(state, act,
    h('h1', { class: 'title' }, 'Where is your home?'),
    h('p', { class: 'lede' }, 'SafeZone checks official public records for the building: California’s tsunami hazard map, San Francisco’s soft-story list and OpenStreetMap.'),
    h('form', { class: 'address-form', onsubmit: (e) => { e.preventDefault(); act.lookupAddress(input.value); } },
      h('label', { for: 'address', class: 'label' }, 'Home address'),
      h('div', { class: 'input-row' }, input,
        h('button', { class: 'btn btn-primary', type: 'submit', disabled: busy }, busy ? 'Checking' : 'Check address')),
      h('button', { class: 'btn-text', type: 'button', onclick: () => { input.value = '1000 Great Highway, San Francisco, CA 94121'; } },
        'Use the demo address')),
    errorLine(state),
    b ? buildingCard(b) : null,
    h('div', { class: 'actions' },
      b ? h('button', { class: 'btn btn-primary', onclick: () => act.go('found') }, 'Next: household') : null,
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, 'Back'), cancelLink(state, act)));
}

function buildingCard(b) {
  const map = b.hazard_area?.map_url;
  return h('section', { class: 'card building' },
    h('div', { class: 'card-head' }, h('h2', { class: 'label' }, 'Building'), sampleTag(b)),
    h('p', { class: 'building-name' }, b.display_name),
    h('p', { class: 'mono fine' }, `${b.lat.toFixed(5)}, ${b.lon.toFixed(5)}`),
    flagList(b),
    map ? h('p', null, h('a', { href: map, target: '_blank', rel: 'noopener', class: 'link-strong' }, 'Open the official tsunami hazard map')) : null);
}

function householdScreen(state, act) {
  const hh = state.draft.household;
  return sheet(state, act,
    h('h1', { class: 'title' }, 'Who lives here?'),
    h('p', { class: 'lede' }, 'Tap everything that applies. SafeZone uses it for the shaking instructions and to pick shelters, so nobody has to answer questions in an emergency.'),
    h('div', { class: 'needs' }, NEEDS.map(([key, label]) =>
      h('button', { class: 'need', 'aria-pressed': String(hh[key]), onclick: () => act.toggleNeed(key) },
        icon(key, 'need-icon'), h('span', { class: 'need-label' }, label),
        h('span', { class: 'need-check' }, hh[key] ? icon('check', 'icon-inline') : null)))),
    h('div', { class: 'actions' },
      h('button', { class: 'btn btn-primary', onclick: () => act.go('next') }, 'Next: rooms'),
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, 'Back'), cancelLink(state, act)));
}

const ROOM_SUGGESTIONS = ['Living room', 'Bedroom', 'Kids’ room', 'Kitchen'];

function roomsScreen(state, act) {
  const { rooms } = state.draft;
  const busy = state.ui.busy;
  const nameInput = h('input', { id: 'room-name', type: 'text', placeholder: 'Living room', autocomplete: 'off' });
  const file = h('input', {
    id: 'room-photo', type: 'file', accept: 'image/*', capture: 'environment', class: 'visually-hidden',
    onchange: () => file.files[0] && act.scanPhoto(nameInput.value, file.files[0]),
  });
  return sheet(state, act,
    h('h1', { class: 'title' }, 'Photograph your rooms'),
    h('p', { class: 'lede' }, 'One wide photo per room, taken from the doorway, works best. SafeZone marks what could fall or break and finds the safest place to drop.'),
    rooms.map((room) => roomResult(room, state, act, 'draft')),
    state.ui.scanning ? scanningCard(state.ui.scanning) : null,
    h('section', { class: 'card add-room' },
      h('label', { for: 'room-name', class: 'label' }, rooms.length ? 'Next room' : 'Room name'),
      nameInput,
      h('div', { class: 'chips' }, ROOM_SUGGESTIONS.map((n) =>
        h('button', { class: 'chip', type: 'button', onclick: () => { nameInput.value = n; } }, n))),
      h('label', { for: 'room-photo', class: busy === 'scan' ? 'btn btn-camera is-disabled' : 'btn btn-camera' },
        icon('camera', 'icon-inline'), 'Photograph this room'),
      file),
    errorLine(state),
    h('div', { class: 'actions' },
      h('button', { class: 'btn btn-primary', disabled: !rooms.length || busy, onclick: () => act.buildPlan() },
        busy === 'build' ? 'Building your plan' : 'Build my plan'),
      rooms.length ? null : h('p', { class: 'fine' }, 'Scan at least one room to build the plan.'),
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, 'Back'), cancelLink(state, act)));
}

function scanningCard({ name, preview }) {
  return h('section', { class: 'card scanning', 'aria-live': 'polite' },
    h('h2', { class: 'room-name' }, name),
    h('div', { class: 'scan-frame' }, h('img', { src: preview, alt: '' }), h('div', { class: 'scan-line' })),
    h('p', { class: 'scan-text' }, 'SAM 3.1 is finding objects; Muse Spark is checking them against the safety rules.'),
    h('p', { class: 'fine' }, 'This usually takes 10 to 30 seconds.'));
}

// Mask fallback and raw model errors are for developers. The boxes are already labelled, and the model line
// already says when the hazard check was unavailable.
const DEV_NOTE = /^(Masks not decoded|Muse Spark error:)/;
const userNotes = (room) => room.notes.filter((n) => !DEV_NOTE.test(n));

export function roomResult(room, state, act, where) {
  const guidance = state.guidance;
  const numbers = hazardNumbers(room);
  const hazards = room.classified.filter((c) => c.role === 'hazard');
  const covers = room.classified.filter((c) => c.role === 'cover');
  const neutral = room.classified.filter((c) => c.role === 'neutral');
  const label = (id) => room.classified.find((c) => c.segment.id === id)?.segment.label ?? id;
  const done = room.fixes.filter((f) => f.done).length;
  const imageUrl = state.images[room.id];
  return h('section', { class: 'card room', id: `room-${room.id}` },
    h('div', { class: 'card-head' },
      h('h2', { class: 'room-name' }, room.name), sampleTag(room),
      where === 'draft' ? h('button', { class: 'btn-text btn-small', onclick: () => act.removeRoom(room.id) }, 'Remove') : null),
    h('figure', { class: 'room-fig' },
      roomOverlay(room, imageUrl),
      imageUrl ? null : h('p', { class: 'fine' }, 'The photo for this room is not on this device. The markings are still correct.'),
      h('figcaption', { class: 'mono fine model-line' },
        `Objects: ${room.models.segmenter}. Hazard check: `,
        room.models.classifier && room.models.classifier_ok ? room.models.classifier : 'unavailable, labels only')),
    h('div', { class: 'spot' },
      room.spots.map((spot, i) => h('div', { class: i === 0 ? 'spot-item spot-best' : 'spot-item' },
        h('p', { class: 'spot-kind' }, icon(spot.kind === 'no_cover' ? 'info' : 'target', 'icon-inline'),
          i === 0 ? 'Safe spot' : `Option ${i + 1}`, h('span', { class: 'spot-kind-tag' }, SPOT_KIND[spot.kind])),
        h('p', { class: 'spot-instruction' }, spot.instruction),
        spot.cautions.length ? h('ul', { class: 'cautions' }, spot.cautions.map((c) => h('li', null, c))) : null))),
    hazards.length ? h('div', { class: 'block' },
      h('h3', { class: 'label' }, `What could fall or break (${hazards.length})`),
      h('ol', { class: 'legend' }, hazards.map((c) =>
        h('li', null, h('span', { class: 'balloon' }, numbers.get(c.segment.id)),
          h('div', null,
            h('p', { class: 'legend-title' }, c.segment.label, h('span', { class: 'legend-kind' }, guidance?.hazard_labels?.[c.hazard_kind] ?? '')),
            h('p', { class: 'legend-reason' }, c.reason)))))) : null,
    covers.length ? h('p', { class: 'fine' }, h('strong', null, 'Cover: '), covers.map((c) => c.segment.label).join(', ')) : null,
    neutral.length ? h('p', { class: 'fine' }, 'Also seen: ', neutral.map((c) => c.segment.label).join(', ')) : null,
    room.relations?.length || room.exit_note ? h('div', { class: 'block noticed' },
      h('h3', { class: 'label' }, 'What Muse Spark noticed'),
      room.relations?.length ? h('ul', { class: 'relations' }, room.relations.map((rel) =>
        h('li', null, h('span', { class: 'rel-kind' }, RELATION_TEXT[rel.kind] ?? rel.kind),
          h('span', null, rel.note), h('span', { class: 'fine mono' }, ` ${label(rel.subject_id)} / ${label(rel.hazard_id)}`)))) : null,
      room.exit_note ? h('p', { class: 'exit-note' }, h('strong', null, 'Way to the door: '), room.exit_note) : null) : null,
    room.fixes.length ? h('div', { class: 'block' },
      h('div', { class: 'fix-head' }, h('h3', { class: 'label' }, 'Fix list'),
        h('span', { class: 'mono fine' }, `${done} of ${room.fixes.length} done`)),
      h('div', { class: 'progress', 'aria-hidden': 'true' }, room.fixes.map((f) => h('span', { class: f.done ? 'on' : '' }))),
      h('ul', { class: 'fixes' }, room.fixes.map((f) => fixItem(f, numbers, () => act.toggleFix(where, room.id, f.id))))) : null,
    userNotes(room).length ? h('ul', { class: 'notes fine' }, userNotes(room).map((n) => h('li', null, n))) : null);
}

function fixItem(f, numbers, onToggle) {
  const id = `fix-${f.id}`;
  return h('li', { class: f.done ? 'fix is-done' : 'fix' },
    h('input', { type: 'checkbox', id, checked: f.done, onchange: onToggle }),
    h('label', { for: id },
      h('span', { class: 'fix-box', 'aria-hidden': 'true' }, icon('check', 'icon-inline')),
      h('span', { class: 'fix-body' },
        h('span', { class: 'fix-action' }, f.action),
        h('span', { class: 'fix-target' },
          numbers.has(f.target_id) ? h('span', { class: 'balloon balloon-small' }, numbers.get(f.target_id)) : null, f.target_label),
        h('span', { class: 'fix-meta' },
          h('span', { class: `effort effort-${f.effort}` }, EFFORT_TEXT[f.effort]),
          h('span', { class: 'cost mono' }, costText(f.cost_usd))))));
}

function planScreen(state, act) {
  const { plan, shelters_error } = state.saved;
  const g = state.guidance;
  const route = plan.route;
  const inZone = route && route.kind !== 'not_in_zone';
  const needs = NEEDS.filter(([k]) => plan.household[k]);
  return h('div', { class: 'sheet' }, header(state, act), h('main', { class: 'page plan' },
    h('section', { class: 'titleblock' },
      h('div', { class: 'tb-main' },
        h('p', { class: 'label' }, 'Household earthquake and tsunami plan'),
        h('h1', { class: 'title' }, plan.building.address)),
      h('dl', { class: 'tb-grid mono' },
        h('div', null, h('dt', null, 'Made'), h('dd', null, localTime(plan.generated_at))),
        h('div', null, h('dt', null, 'Rooms'), h('dd', null, plan.rooms.length)),
        h('div', null, h('dt', null, 'Tsunami area'), h('dd', null, !route ? 'Unknown' : inZone ? 'Inside' : 'Outside')),
        h('div', null, h('dt', null, 'Saved'), h('dd', null, 'On this device')))),

    h('section', { class: 'plan-section dch' },
      h('h2', { class: 'section-title' }, 'During shaking'),
      h('p', { class: 'dch-words' }, 'Drop. Cover. Hold on.'),
      g ? h('ol', { class: 'steps-list' }, g.during.map((t) => h('li', null, t))) : null,
      h('ul', { class: 'spot-summary' }, plan.rooms.map((r) =>
        h('li', null, h('strong', null, r.name), h('span', null, r.spots[0]?.instruction)))),
      duringSpecials(plan, g).map((t) => h('p', { class: 'special' }, t))),

    h('section', { class: 'plan-section' },
      h('h2', { class: 'section-title' }, 'When the shaking stops'),
      inZone ? h('p', { class: 'go-now' }, g?.go_now) : null,
      route?.kind === 'not_in_zone' ? h('p', { class: 'calm-strong' }, g?.not_in_zone ?? route.reason) : null,
      !route ? h('p', { class: 'calm-strong' }, TSUNAMI_MAP_MISSING) : null,
      g ? h('ol', { class: 'steps-list' }, g.after.map((t) => h('li', null, t))) : null,
      inZone && g ? h('p', { class: 'fine' }, g.stay_away) : null),

    inZone ? h('section', { class: 'plan-section' },
      h('h2', { class: 'section-title' }, 'Way out of the hazard area'),
      routeView(route, plan.building)) : null,

    inZone || plan.shelters ? h('section', { class: 'plan-section print-shelters' },
      h('h2', { class: 'section-title' }, 'Shelters that fit your household'),
      shelterSection(plan, shelters_error)) : null,

    h('section', { class: 'plan-section' },
      h('h2', { class: 'section-title' }, 'Building'),
      buildingCard(plan.building)),

    h('section', { class: 'plan-section' },
      h('h2', { class: 'section-title' }, 'Household'),
      needs.length ? h('ul', { class: 'need-chips' }, needs.map(([k, label]) => h('li', null, icon(k, 'icon-inline'), label)))
        : h('p', { class: 'fine' }, 'No special needs selected.')),

    h('section', { class: 'plan-section rooms-section' },
      h('h2', { class: 'section-title' }, 'Rooms and fixes'),
      plan.rooms.map((room) => roomResult(room, state, act, 'plan'))),

    h('section', { class: 'plan-section no-print' },
      h('div', { class: 'actions' },
        h('button', { class: 'btn btn-primary', onclick: () => window.print() }, 'Print fridge sheet'),
        h('button', { class: 'btn', onclick: () => act.go('add_room') }, 'Add or change rooms'),
        h('button', { class: 'btn', onclick: () => act.go('edit_household') }, 'Change household'),
        h('button', { class: 'btn', onclick: () => act.go('edit_address') }, 'Change address'),
        h('button', { class: 'btn-text', onclick: () => act.reset() }, 'Delete this plan'))),

    footerNotes(g)));
}

export function footerNotes(g) {
  if (!g) return null;
  return h('footer', { class: 'plan-section footnotes' },
    h('h2', { class: 'section-title' }, 'Limits of this plan'),
    h('ul', { class: 'disclaimers' }, g.disclaimers.map((d) => h('li', null, d))),
    h('h2', { class: 'section-title sources-title' }, 'Sources'),
    h('ul', { class: 'sources mono' }, Object.values(g.sources).map(([name, url]) =>
      h('li', null, h('a', { href: url, target: '_blank', rel: 'noopener' }, name)))));
}

const SCREENS = { start: startScreen, address: addressScreen, household: householdScreen, rooms: roomsScreen, plan: planScreen };

export function renderPrepare(state, act) {
  return SCREENS[state.screen](state, act);
}
