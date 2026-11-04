// Standby shake detection. Opens the shaking screen, which tells nobody to move, so a false positive costs a
// tap on "Shaking has stopped"; a missed quake costs nothing the user would not do anyway. The bar is still
// sustained shaking: most samples strong for a whole window, never one jolt.

export const STRONG_MS2 = 4;
export const WINDOW_MS = 2000;
export const MIN_STRONG_FRACTION = 0.6;
const MIN_SAMPLES = 20;

// Pure: feed timestamps and magnitudes, ask whether the last window counts as sustained shaking.
export function shakeDetector({ strong = STRONG_MS2, windowMs = WINDOW_MS, fraction = MIN_STRONG_FRACTION } = {}) {
  const samples = [];
  return {
    push(t, magnitude) {
      samples.push({ t, hit: magnitude >= strong });
      while (samples.length && samples[0].t < t - windowMs) samples.shift();
      if (samples.length < MIN_SAMPLES || t - samples[0].t < windowMs * 0.9) return false;
      const hits = samples.filter((s) => s.hit).length;
      return hits / samples.length >= fraction;
    },
    reset() { samples.length = 0; },
  };
}

const magnitude = (a) => (a && a.x != null ? Math.hypot(a.x, a.y, a.z) : null);

let active = null;

// Listens while `isArmed()` says so (the places screen checks it is still on screen). Fires `onQuake` once,
// then rearms after 30 s so one quake cannot reopen the screen the moment the user leaves it.
export function startStandby({ onQuake, isArmed = () => true }) {
  stopStandby();
  const det = shakeDetector();
  let cooldownUntil = 0;
  const onMotion = (e) => {
    if (!isArmed()) return;
    const m = magnitude(e.acceleration) ?? (e.accelerationIncludingGravity ? Math.abs(magnitude(e.accelerationIncludingGravity) - 9.81) : null);
    if (m == null) return;
    const t = performance.now();
    if (t < cooldownUntil) return;
    if (det.push(t, m)) {
      det.reset();
      cooldownUntil = t + 30000;
      onQuake();
    }
  };
  window.addEventListener('devicemotion', onMotion);
  active = () => window.removeEventListener('devicemotion', onMotion);
  return stopStandby;
}

export function stopStandby() {
  active?.();
  active = null;
}

export const motionAvailable = () => typeof DeviceMotionEvent !== 'undefined';

// Demo: shakes the page with CSS, then fires the same path a real quake would. The label is the caller's job.
export function simulateQuake(fire, { durationMs = 1500 } = {}) {
  const root = document.documentElement;
  root.setAttribute('data-quake', '');
  const done = () => { root.removeAttribute('data-quake'); fire(); };
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  setTimeout(done, reduced ? 300 : durationMs);
}
