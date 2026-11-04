import { cameraDeclined, openCamera, pickPhoto } from '../camera.js';
import { h, icon, s } from '../dom.js';
import { frameStats, motion, shotQuality, tiltFromOrientation } from '../quality.js';
import { SHOTS, firstOpenStep, stepSummary } from '../shots.js';

// The guided shot list. The live preview and the quality loop outlive app renders: they sit in
// `live` and are moved into each new render's tree, and the meter is updated in place about ten
// times a second. Everything stops once the stage is no longer in the document.

const SAMPLE_MS = 100;
const SAMPLE_SIDE = 160;
const STABLE_FRAMES = 4;
const RING_R = 44;
const RING_C = 2 * Math.PI * RING_R;
const ROOM_NAMES = ['Living room', 'Bedroom', 'Kitchen', "Kid's room"];
const DEMO_PHOTO = '/demo/living_room.jpg';
const DEMO_BANNER = 'DEMO: recorded photo and data for 1000 Great Highway';

let live = null;
let ui = null;
let meter = {};

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

// --- Live stage: preview, analysis loop, orientation ------------------------------------------

function startLive(state) {
  const video = h('video', { class: 'cap-video', muted: true, playsInline: true, autoplay: true, 'aria-hidden': 'true' });
  const still = h('img', { class: 'cap-still', alt: '', hidden: true });
  const fallback = h('div', { class: 'cap-fallback', hidden: true });
  const flash = h('div', { class: 'cap-flash', 'aria-hidden': 'true' });
  const guide = h('div', { class: 'cap-guide', 'aria-hidden': 'true' }, ['tl', 'tr', 'bl', 'br'].map((c) => h('span', { class: `cap-corner cap-${c}` })));
  const stage = h('div', { class: 'cap-stage' }, video, still, guide, fallback, flash);
  const canvas = document.createElement('canvas');
  live = {
    stage, video, still, fallback, flash, guide, canvas, ctx: canvas.getContext('2d', { willReadFrequently: true }),
    demo: Boolean(state.demo), source: 'starting', cam: null, raf: 0, last: 0, prev: null, seen: false,
    tilt: null, smooth: 0, okRun: 0, badRun: 0, ok: false, hint: null, pendingHint: null, hintRun: 0, kind: null,
    onTilt: (e) => { live.tilt = e.beta == null ? null : { beta: e.beta, gamma: e.gamma }; },
  };
  window.addEventListener('deviceorientation', live.onTilt);
  if (live.demo) {
    live.source = 'demo';
    live.still.src = DEMO_PHOTO;
    showSource();
  } else connectCamera(live);
  live.raf = requestAnimationFrame(tick);
}

async function connectCamera(l) {
  try {
    const cam = await openCamera(l.video);
    if (live !== l) return cam.stop();
    l.cam = cam;
    l.source = 'camera';
  } catch (e) {
    if (live !== l) return;
    l.source = e.code === 'denied' ? 'denied' : cameraDeclined() ? 'declined' : 'unavailable';
  }
  showSource();
  repaintMeter();
}

function stopLive() {
  if (!live) return;
  cancelAnimationFrame(live.raf);
  window.removeEventListener('deviceorientation', live.onTilt);
  live.cam?.stop();
  live = null;
  ui = null;
  meter = {};
}

// A new step starts the meter from empty.
function setKind(kind) {
  if (!live || live.kind === kind) return;
  live.kind = kind;
  live.prev = null;
  live.smooth = 0;
  live.okRun = live.badRun = 0;
  live.ok = false;
  live.hint = null;
}

const FALLBACK_TEXT = {
  denied: 'The camera is blocked for this site. Choose a photo instead, or allow the camera in your browser settings.',
  declined: 'Camera is off. Choose a photo from your library or take one with the camera app.',
  unavailable: 'No camera here. Choose a photo instead.',
};

function showSource() {
  const { source, video, still, fallback, guide } = live;
  video.hidden = source !== 'camera' && source !== 'starting';
  still.hidden = source !== 'demo';
  const text = FALLBACK_TEXT[source];
  fallback.hidden = !text;
  live.stage.classList.toggle('is-fallback', Boolean(text));
  if (text) {
    fallback.replaceChildren(
      icon('camera', 'cap-fallback-icon'),
      h('p', null, text),
      h('button', { class: 'btn-ghost cap-pick', onclick: () => ui?.pick?.() }, 'Choose a photo'));
  }
  guide.hidden = Boolean(text);
}

const measurable = () => live && ((live.source === 'camera' && live.video.videoWidth > 0) || (live.source === 'demo' && live.still.complete && live.still.naturalWidth > 0));

function sample() {
  const src = live.source === 'camera' ? live.video : live.still;
  const sw = src.videoWidth || src.naturalWidth, sh = src.videoHeight || src.naturalHeight;
  const k = SAMPLE_SIDE / Math.max(sw, sh);
  const w = Math.max(8, Math.round(sw * k)), hgt = Math.max(8, Math.round(sh * k));
  if (live.canvas.width !== w || live.canvas.height !== hgt) Object.assign(live.canvas, { width: w, height: hgt });
  live.ctx.drawImage(src, 0, 0, w, hgt);
  return live.ctx.getImageData(0, 0, w, hgt);
}

function tick(now) {
  if (!live) return;
  if (live.stage.isConnected) live.seen = true;
  else if (live.seen) return stopLive();
  live.raf = requestAnimationFrame(tick);
  if (now - live.last < SAMPLE_MS) return;
  // Moving the stage between renders can pause the video in some browsers.
  if (live.source === 'camera' && live.video.paused) live.video.play().catch(() => {});
  if (!measurable()) return;
  live.last = now;
  const frame = sample();
  const spec = SHOTS.find((x) => x.kind === live.kind);
  const tiltDeg = spec?.level && live.tilt ? tiltFromOrientation(live.tilt.beta, live.tilt.gamma) : null;
  const q = shotQuality({ ...frameStats(frame), motion: motion(live.prev, frame), tiltDeg, kind: live.kind });
  live.prev = frame;
  live.smooth += (q.score - live.smooth) * 0.3;
  if (q.ok) { live.okRun++; live.badRun = 0; } else { live.badRun++; live.okRun = 0; }
  if (!live.ok && live.okRun >= 3) live.ok = true;
  if (live.ok && live.badRun >= 3) live.ok = false;
  if (q.hint === live.pendingHint) live.hintRun++;
  else { live.pendingHint = q.hint; live.hintRun = 1; }
  if (live.hint == null || live.hintRun >= STABLE_FRAMES) live.hint = live.pendingHint;
  repaintMeter();
}

function liveHint() {
  if (!live) return '';
  switch (live.source) {
    case 'starting': return 'Starting the camera...';
    case 'camera': case 'demo': return live.hint ?? 'Point the camera at the scene';
    default: return 'Tap the shutter to choose a photo';
  }
}

function repaintMeter() {
  const { ring, hint, shutter, pill } = meter;
  if (!live || !ring?.isConnected) return;
  const measuring = live.source === 'camera' || live.source === 'demo';
  const score = measuring ? live.smooth : 0;
  ring.style.strokeDashoffset = String(RING_C * (1 - score));
  const good = measuring && live.ok;
  shutter.classList.toggle('is-good', good);
  shutter.setAttribute('aria-label', good ? 'Take the photo. The shot looks good.' : 'Take the photo');
  pill.classList.toggle('is-good', good);
  pill.classList.toggle('is-idle', !measuring);
  const text = liveHint();
  if (hint.textContent !== text) hint.textContent = text;
}

// --- Actions ------------------------------------------------------------------------------------

async function demoBlob() {
  const res = await fetch(DEMO_PHOTO);
  if (!res.ok) throw new Error('demo photo missing');
  return res.blob();
}

function flash() {
  if (!live || reducedMotion()) return;
  live.flash.classList.remove('is-on');
  void live.flash.offsetWidth;
  live.flash.classList.add('is-on');
}

async function store(state, act, blob) {
  const spec = SHOTS[ui.step];
  const name = spec.kind === 'room' ? ui.roomName : '';
  for (const skipped of state.session.shots.filter((x) => x.kind === spec.kind && x.status === 'skipped')) await act.removeShot(skipped.id);
  const id = await act.addShot(spec.kind, name, blob);
  if (!ui) return;
  ui.busy = false;
  if (id) {
    ui.justTook = id;
    ui.roomName = '';
  }
  rerender();
}

async function shoot(state, act) {
  if (!ui || ui.busy) return;
  let blob = null;
  if (live?.source === 'camera') {
    flash();
    blob = await live.cam.capture().catch(() => null);
  } else if (live?.source === 'demo') {
    flash();
    blob = await demoBlob().catch(() => null);
  } else {
    blob = await pickPhoto();
  }
  if (!blob || !ui) return;
  ui.busy = true;
  rerender();
  await store(state, act, blob);
}

async function pick(state, act) {
  const file = await pickPhoto();
  if (!file || !ui) return;
  ui.busy = true;
  rerender();
  await store(state, act, file);
}

function finish(act) {
  stopLive();
  act.go('done');
}

function goStep(i) {
  ui.step = i;
  ui.justTook = null;
  ui.roomName = '';
  rerender();
}

function next(act) {
  if (ui.step === SHOTS.length - 1) return finish(act);
  goStep(ui.step + 1);
}

async function skip(state, act) {
  const spec = SHOTS[ui.step];
  if (!state.session.shots.some((x) => x.kind === spec.kind)) await act.skipShot(spec.kind);
  if (ui) next(act);
}

function back(act) {
  if (ui.justTook) { ui.justTook = null; return rerender(); }
  if (ui.step > 0) return goStep(ui.step - 1);
  stopLive();
  act.go('back');
}

async function retake(state, act) {
  const id = ui.justTook;
  ui.justTook = null;
  await act.removeShot(id);
  rerender();
}

// Our own UI changes (step, panel) repaint from the last state the app gave us.
function rerender() {
  if (!ui?.root?.isConnected) return;
  ui.root.replaceWith(renderCapture(ui.state, ui.act));
}

// --- View ---------------------------------------------------------------------------------------

const STATUS_TEXT = { open: 'Not taken', skipped: 'Skipped', queued: 'Waiting to be checked', working: 'Being checked', done: 'Checked', failed: 'Could not be checked' };

function stepStrip(shots) {
  return h('ol', { class: 'cap-steps', 'aria-label': 'Photos to take' }, SHOTS.map((spec, i) => {
    const sum = stepSummary(shots, spec.kind);
    const current = i === ui.step;
    const mark = { done: icon('check', 'icon-inline'), failed: icon('alert', 'icon-inline'), skipped: h('span', { class: 'cap-step-dash' }, '-') }[sum.status] ?? null;
    return h('li', null,
      h('button', {
        class: `cap-step is-${sum.status}${current ? ' is-current' : ''}`,
        'aria-current': current ? 'step' : null,
        'aria-label': `${spec.title}: ${sum.count > 1 ? `${sum.count} photos, ` : ''}${STATUS_TEXT[sum.status]}`,
        onclick: () => goStep(i),
      },
      h('span', { class: 'cap-step-title' }, spec.title, spec.repeat && sum.count > 1 ? h('span', { class: 'cap-step-count' }, String(sum.count)) : null),
      mark,
      sum.status === 'working' || sum.status === 'queued' ? h('span', { class: 'cap-shimmer', 'aria-hidden': 'true' }) : null));
  }));
}

function locationChip(state) {
  const loc = state.session.location;
  const flag = loc.building?.flags?.find((f) => f.kind === 'tsunami_zone');
  const where = loc.building?.address?.split(',')[0];
  const [tone, text] = {
    idle: ['idle', 'No location yet. Type the address at the end.'],
    locating: ['busy', 'Checking the tsunami map for this spot...'],
    found: [flag?.tone === 'alert' ? 'alert' : 'ok', flag ? `${where}: ${flag.value}` : `${where}: checked`],
    failed: ['off', 'Location not found. Type the address at the end.'],
  }[loc.status] ?? ['idle', ''];
  return h('p', { class: `cap-loc is-${tone}`, role: 'status', 'aria-live': 'polite' },
    tone === 'busy' ? h('span', { class: 'pulse-dot' }) : h('span', { class: 'cap-loc-dot' }),
    h('span', { class: 'cap-loc-text' }, text));
}

function promptBlock(spec, sum, act) {
  const failed = sum.failed;
  return h('div', { class: 'cap-prompt' },
    h('p', { class: 'cap-count label' }, `Photo ${ui.step + 1} of ${SHOTS.length}${spec.repeat && sum.count ? `, ${sum.count} taken` : ''}`),
    h('h1', { class: 'cap-title' }, spec.prompt),
    h('p', { class: 'cap-why' }, spec.why),
    failed.length && !ui.justTook ? h('p', { class: 'cap-failed', role: 'alert' },
      icon('alert', 'icon-inline'), failed.length === 1 ? 'One photo could not be checked.' : `${failed.length} photos could not be checked.`,
      h('button', { class: 'btn-text', onclick: () => failed.forEach((f) => act.retryShot(f.id)) }, 'Try again')) : null);
}

function roomChips() {
  return h('div', { class: 'cap-names', role: 'group', 'aria-label': 'Name this room (optional)' }, ROOM_NAMES.map((n) =>
    h('button', {
      class: 'chip cap-chip', 'aria-pressed': String(ui.roomName === n),
      onclick: () => { ui.roomName = ui.roomName === n ? '' : n; rerender(); },
    }, n)));
}

function controls(state, act, spec, sum) {
  const last = ui.step === SHOTS.length - 1;
  const ring = s('circle', { class: 'cap-ring-fill', cx: 50, cy: 50, r: RING_R, 'stroke-dasharray': RING_C.toFixed(2), 'stroke-dashoffset': RING_C.toFixed(2) });
  const shutter = h('button', { class: 'cap-shutter', disabled: ui.busy, onclick: () => shoot(state, act) },
    s('svg', { class: 'cap-ring', viewBox: '0 0 100 100', 'aria-hidden': 'true' },
      s('circle', { class: 'cap-ring-track', cx: 50, cy: 50, r: RING_R }), ring),
    h('span', { class: 'cap-shutter-core' }));
  const hint = h('span', { class: 'cap-hint-text' });
  const pill = h('p', { class: 'cap-hint', 'aria-live': 'polite' }, h('span', { class: 'cap-hint-dot', 'aria-hidden': 'true' }), hint);
  meter = { ring, hint, shutter, pill };
  const forward = sum.count
    ? h('button', { class: 'cap-side cap-next', onclick: () => next(act) }, last ? 'Finish' : 'Next', h('span', { 'aria-hidden': 'true' }, ' ›'))
    : h('button', { class: 'cap-side cap-skip', onclick: () => skip(state, act) }, 'Skip');
  const canPick = live && (live.source === 'camera' || live.source === 'demo');
  return h('div', { class: 'cap-bottom' },
    pill,
    spec.kind === 'room' ? roomChips() : null,
    h('div', { class: 'cap-controls' },
      canPick ? h('button', { class: 'cap-side cap-library', onclick: () => pick(state, act) }, 'Library') : h('span', { class: 'cap-side' }),
      shutter,
      forward));
}

function shotStatusLine(shot, act) {
  if (!shot) return null;
  if (shot.status === 'failed') {
    return h('p', { class: 'cap-took-status is-failed', role: 'alert' }, shot.error ?? 'This photo could not be checked.',
      ' ', h('button', { class: 'btn-text', onclick: () => act.retryShot(shot.id) }, 'Try again'));
  }
  const spec = SHOTS.find((x) => x.kind === shot.kind);
  const text = shot.status === 'done'
    ? (spec.vision ? 'Checked. The results are on the next screen.' : 'Saved to your plan.')
    : spec.vision === 'scan' ? 'SAM 3.1 and Muse Spark are reading it. Keep going.' : 'Muse Spark is checking it. Keep going.';
  return h('p', { class: `cap-took-status is-${shot.status}`, 'aria-live': 'polite' },
    shot.status === 'done' ? icon('check', 'icon-inline') : h('span', { class: 'pulse-dot' }), text);
}

function tookPanel(state, act, spec) {
  const shot = state.session.shots.find((x) => x.id === ui.justTook);
  const last = ui.step === SHOTS.length - 1;
  const nextTitle = last ? 'Finish' : `Next: ${SHOTS[ui.step + 1].title}`;
  const url = shot && state.images?.[shot.image_id];
  return h('section', { class: 'cap-took card', 'aria-label': 'Photo saved' },
    h('div', { class: 'cap-took-head' },
      url ? h('img', { class: 'cap-thumb', src: url, alt: '' }) : h('span', { class: 'cap-thumb' }),
      h('div', { class: 'stack-tight' },
        h('p', { class: 'cap-took-title' }, `${shot?.kind === 'room' ? shot.name : spec.title} ${shot?.status === 'failed' ? 'not checked' : 'saved'}`),
        shotStatusLine(shot, act))),
    h('div', { class: 'cap-took-actions' },
      h('button', { class: 'btn-text', onclick: () => retake(state, act) }, 'Retake'),
      spec.repeat ? h('button', { class: 'btn-ghost', onclick: () => goStep(ui.step) }, 'Add another room') : null,
      h('button', { class: 'btn', onclick: () => next(act) }, nextTitle)));
}

export function renderCapture(state, act) {
  if (live && live.demo !== Boolean(state.demo)) stopLive();
  if (!live) startLive(state);
  if (!ui) ui = { step: firstOpenStep(state.session.shots), roomName: '', justTook: null, busy: false };
  ui.state = state;
  ui.act = act;
  ui.pick = () => pick(state, act);
  if (ui.justTook && !state.session.shots.some((x) => x.id === ui.justTook)) ui.justTook = null;

  const spec = SHOTS[ui.step];
  const sum = stepSummary(state.session.shots, spec.kind);
  setKind(spec.kind);

  const root = h('div', { class: `capture${state.demo ? ' is-demo' : ''}` },
    state.demo ? h('div', { class: 'demo-banner', role: 'status' }, DEMO_BANNER) : null,
    h('header', { class: 'cap-top' },
      h('div', { class: 'cap-nav' },
        h('button', { class: 'cap-back', 'aria-label': ui.step > 0 && !ui.justTook ? `Back to ${SHOTS[ui.step - 1].title}` : 'Back', onclick: () => back(act) }, '‹'),
        stepStrip(state.session.shots)),
      locationChip(state),
      promptBlock(spec, sum, act)),
    live.stage,
    state.ui?.error ? h('p', { class: 'cap-error', role: 'alert' }, state.ui.error) : null,
    ui.justTook ? tookPanel(state, act, spec) : controls(state, act, spec, sum));
  ui.root = root;
  queueMicrotask(repaintMeter);
  return root;
}
