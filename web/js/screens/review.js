import { h, icon, sampleTag } from '../dom.js';
import { NEEDS, flagList } from './parts.js';
import { roomResult } from './prepare.js';

// The last setup step: what was found about the place, who lives here, what each photo showed, and a name.

const KINDS = [['home', 'Home'], ['work', 'Work'], ['school', 'School'], ['other', 'Other']];
const SHOT_TITLE = { room: 'Room', exit: 'The way out', gobag: 'Go bag', gas: 'Gas shutoff' };

function locationCard(session, act) {
  const loc = session.location;
  if (loc.status === 'found') {
    return h('section', { class: 'card stack' },
      h('p', { class: 'label' }, 'This place'),
      h('h2', { class: 'review-address' }, loc.building.display_name ?? loc.building.address),
      flagList(loc.building));
  }
  const busy = loc.status === 'locating';
  let input;
  return h('section', { class: 'card stack' },
    h('p', { class: 'label' }, 'This place'),
    busy
      ? h('p', { class: 'status-line', 'aria-live': 'polite' }, h('span', { class: 'pulse-dot' }), 'Checking the tsunami map and building records for this place...')
      : h('p', null, loc.status === 'failed' ? (loc.error ?? 'The location lookup did not finish.') : 'Type the address so SafeZone can check the official hazard maps.'),
    busy ? null : h('form', { class: 'address-form', onsubmit: (e) => { e.preventDefault(); act.lookupAddress(input.value); } },
      input = h('input', { class: 'input', type: 'text', name: 'address', autocomplete: 'street-address', placeholder: 'Street address, city', 'aria-label': 'Street address' }),
      h('button', { class: 'btn', type: 'submit' }, 'Look up')));
}

function household(session, act) {
  return h('section', { class: 'card stack' },
    h('p', { class: 'label' }, 'Who lives here'),
    h('p', { class: 'fine' }, 'Tap all that apply. The plan uses this to pick shelters and the right guidance.'),
    h('div', { class: 'chips' }, NEEDS.map(([key, text]) =>
      h('button', { class: 'chip', 'aria-pressed': String(Boolean(session.household[key])), onclick: () => act.toggleNeed(key) }, text))));
}

function goBag(check) {
  return h('section', { class: 'card stack' },
    h('div', { class: 'card-head' }, h('h2', null, 'Go bag'), sampleTag(check)),
    h('p', { class: 'fine' }, `${check.seen_count} of ${check.total} basic-kit items seen in the photo. Items out of view may still be packed.`),
    h('ul', { class: 'gobag' }, check.items.map((it) =>
      h('li', { class: it.seen ? 'seen' : 'unseen' }, icon(it.seen ? 'check' : 'question', 'icon-inline'),
        h('span', null, it.label), h('span', { class: 'fine' }, it.seen ? ' Seen in the photo' : ' Not seen')))),
    h('p', { class: 'fine mono' }, `Checked by ${check.model}. List from Ready.gov.`));
}

function pending(shot, act) {
  const working = shot.status === 'queued' || shot.status === 'working';
  return h('section', { class: 'card shot-pending' },
    h('h2', null, shot.name || SHOT_TITLE[shot.kind]),
    working
      ? h('p', { class: 'status-line', 'aria-live': 'polite' }, h('span', { class: 'pulse-dot' }),
        shot.kind === 'room' ? 'SAM 3.1 and Muse Spark are reading this room...' : 'Muse Spark is checking the photo...')
      : h('p', { class: 'error', role: 'alert' }, shot.error ?? 'This photo could not be checked.',
        ' ', h('button', { class: 'btn-text', onclick: () => act.retryShot(shot.id) }, 'Try again'),
        h('button', { class: 'btn-text', onclick: () => act.removeShot(shot.id) }, 'Remove')));
}

function reference(shot, state) {
  const url = state.images[shot.image_id];
  return h('figure', { class: 'card ref-shot' },
    url ? h('img', { src: url, alt: SHOT_TITLE[shot.kind] }) : null,
    h('figcaption', null, h('strong', null, SHOT_TITLE[shot.kind]), ' Saved on this device for offline reference.'));
}

function shotCard(shot, state, act) {
  if (shot.status === 'skipped') return null;
  if (shot.status !== 'done') return pending(shot, act);
  if (shot.kind === 'room') return roomResult(shot.result, state, act, 'draft');
  if (shot.kind === 'gobag') return goBag(shot.result);
  return reference(shot, state);
}

function nameCard(session, act) {
  return h('section', { class: 'card stack' },
    h('p', { class: 'label' }, 'Save it as'),
    h('div', { class: 'chips' }, KINDS.map(([kind, text]) =>
      h('button', { class: 'chip', 'aria-pressed': String(session.kind === kind), onclick: () => act.setPlaceName(session.name || text, kind) }, text))),
    h('input', { class: 'input', type: 'text', value: session.name ?? '', placeholder: 'Name, like Home or Grandma\'s', 'aria-label': 'Place name',
      onchange: (e) => act.setPlaceName(e.target.value, session.kind ?? 'other') }));
}

export function renderReview(state, act) {
  const session = state.session;
  const ready = session.location.status === 'found';
  const working = session.shots.some((s) => s.status === 'queued' || s.status === 'working');
  const blocker = !ready ? 'Add the address to save this place.' : working ? 'You can save now; photos still being read are added when they finish.' : null;
  return h('div', { class: 'screen review' },
    state.demo ? h('div', { class: 'demo-banner', role: 'status' }, 'DEMO: recorded real data for 1000 Great Highway') : null,
    h('header', { class: 'review-head' },
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, '‹ Back to photos'),
      h('h1', null, 'Your plan for this place')),
    h('main', { class: 'stack' },
      locationCard(session, act),
      household(session, act),
      session.shots.map((shot) => shotCard(shot, state, act)),
      nameCard(session, act)),
    h('div', { class: 'dock' },
      state.ui.error ? h('p', { class: 'error', role: 'alert' }, state.ui.error) : null,
      blocker ? h('p', { class: 'fine', 'aria-live': 'polite' }, blocker) : null,
      h('button', { class: 'btn btn-wide', disabled: !ready || state.ui.busy === 'save', onclick: () => act.savePlace() },
        state.ui.busy === 'save' ? 'Finding the way out and shelters...' : 'Save this place')));
}
