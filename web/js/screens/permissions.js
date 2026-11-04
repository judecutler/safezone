import { declineCamera, requestCamera } from '../camera.js';
import { h, icon } from '../dom.js';

// One screen before the first prompt: why SafeZone wants each permission, one button that asks for
// all of them, and what each answer was. Permission answers live here, not in the session, because
// the browser remembers them and the session should not go stale when the person changes a setting.

const perm = { camera: 'ask', motion: 'ask', asking: false };
let mounted = null;

const motionNeedsAsking = () => typeof window.DeviceMotionEvent?.requestPermission === 'function';

async function requestMotion() {
  if (!motionNeedsAsking()) return 'not_needed';
  try {
    return (await window.DeviceMotionEvent.requestPermission()) === 'granted' ? 'granted' : 'denied';
  } catch {
    return 'denied';
  }
}

function paint() {
  if (!mounted?.root.isConnected) return;
  const next = renderPermissions(mounted.state, mounted.act);
  mounted.root.replaceWith(next);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function allow(state, act) {
  perm.asking = true;
  if (state.demo) {
    perm.camera = 'demo';
    perm.motion = 'demo';
    act.startLocate();
    paint();
    await sleep(600);
    perm.asking = false;
    return act.go('done');
  }
  // iOS only lets the motion prompt open straight from a tap, so it goes first.
  if (motionNeedsAsking()) {
    perm.motion = 'asking';
    paint();
    perm.motion = await requestMotion();
  }
  perm.camera = 'asking';
  paint();
  perm.camera = await requestCamera();
  act.startLocate();
  paint();
  await sleep(perm.camera === 'granted' ? 700 : 0);
  perm.asking = false;
  if (perm.camera === 'granted') return act.go('done');
  paint();
}

function notNow(act) {
  declineCamera();
  perm.camera = perm.camera === 'granted' ? 'granted' : 'declined';
  act.go('done');
}

const CAMERA_TEXT = {
  ask: null,
  asking: 'Waiting for your answer...',
  granted: 'Allowed',
  demo: 'Not needed in the demo. It uses a recorded photo.',
  denied: 'Blocked. You can still choose photos from your library.',
  unavailable: 'No camera found here. You can still choose photos.',
  declined: 'Not now. You can choose photos from your library.',
};
const MOTION_TEXT = {
  ask: null,
  asking: 'Waiting for your answer...',
  granted: 'Allowed',
  demo: 'Not needed in the demo.',
  denied: 'Blocked. SafeZone cannot notice shaking by itself; open it and tap the emergency button.',
  not_needed: 'Allowed',
};

function locationText(state) {
  const loc = state.session?.location;
  if (state.demo && loc?.status !== 'idle') return loc?.status === 'found' ? 'Demo address: 1000 Great Highway, San Francisco' : 'Using the demo address...';
  switch (loc?.status) {
    case 'locating': return 'Finding this place...';
    case 'found': return 'Found';
    case 'failed': return `${loc.error ?? 'Location is off.'} You can type the address at the end.`;
    default: return null;
  }
}

const TONE = { granted: 'ok', found: 'ok', not_needed: 'ok', demo: 'ok', denied: 'off', unavailable: 'off', declined: 'off', failed: 'off', asking: 'busy', locating: 'busy' };
const MARK = { ok: 'check', off: 'info', busy: null };

function row({ id, title, why, status, text }) {
  const tone = TONE[status] ?? 'ask';
  return h('li', { class: `perm-row perm-${tone}`, 'data-perm': id },
    h('span', { class: 'perm-icon' }, icon(id === 'camera' ? 'camera' : id === 'location' ? 'target' : 'alert', 'icon')),
    h('div', { class: 'perm-body' },
      h('p', { class: 'perm-title' }, title),
      h('p', { class: 'perm-why' }, why),
      text ? h('p', { class: 'perm-result', 'aria-live': 'polite' },
        MARK[tone] ? icon(MARK[tone], 'icon-inline') : h('span', { class: 'pulse-dot' }), text) : null));
}

export function renderPermissions(state, act) {
  if (!state.demo && perm.camera === 'demo') Object.assign(perm, { camera: 'ask', motion: 'ask' });
  const loc = state.session?.location?.status ?? 'idle';
  const rows = [
    { id: 'camera', title: 'Camera', status: perm.camera, text: CAMERA_TEXT[perm.camera],
      why: 'To photograph each room, the way out, your go bag and the gas shutoff. Photos stay on this phone; each one is sent once to be checked.' },
    { id: 'location', title: 'Location', status: loc, text: locationText(state),
      why: "To check the official tsunami map and building records for where you are, while you take photos. Or type the address at the end." },
  ];
  if (motionNeedsAsking()) {
    rows.push({ id: 'motion', title: 'Motion', status: perm.motion, text: MOTION_TEXT[perm.motion],
      why: 'So SafeZone can notice strong shaking while it is open and switch to the emergency screen.' });
  }
  const cameraAnswered = !['ask', 'asking'].includes(perm.camera);
  const primary = perm.asking
    ? h('button', { class: 'btn', disabled: true }, 'Asking...')
    : cameraAnswered
      ? h('button', { class: 'btn', onclick: () => act.go('done') }, perm.camera === 'granted' ? 'Start taking photos' : 'Continue with the photo picker')
      : h('button', { class: 'btn', onclick: () => allow(state, act) }, state.demo ? 'Continue' : 'Allow camera and location');

  const root = h('div', { class: 'screen permissions' },
    state.demo ? h('div', { class: 'demo-banner', role: 'status' }, 'DEMO: recorded real data for 1000 Great Highway') : null,
    h('header', { class: 'perm-head' },
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, '‹ Back'),
      h('h1', { class: 'title' }, 'Map this place in a few photos'),
      h('p', { class: 'lede' }, 'SafeZone checks the tsunami map for this address while you take the photos.')),
    h('ul', { class: 'perm-list' }, rows.map(row)),
    h('div', { class: 'perm-actions stack-tight' },
      primary,
      perm.asking || cameraAnswered ? null : h('button', { class: 'btn-text perm-skip', onclick: () => notNow(act) }, 'Not now'),
      h('p', { class: 'fine' }, state.demo
        ? 'The demo asks for no permissions. It uses recorded data, and says so on every screen.'
        : 'Your phone will ask you to confirm each one. You can change them later in your browser settings.')));
  mounted = { root, state, act };
  return root;
}
