// The one place that talks, buzzes and keeps the screen on. Screens never touch speechSynthesis directly.
// Every line goes through `say`, which also records it in `spoken` so a test or the console can read the
// sequence when speech is unavailable (headless browsers, muted phones).

const RATE = 0.95;
const synth = () => (typeof speechSynthesis === 'undefined' ? null : speechSynthesis);

export const spoken = [];
let muted = false;
const repeats = new Set();
const listeners = new Set();

export function onVoiceChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const isMuted = () => muted;

export function setMuted(value) {
  muted = Boolean(value);
  if (muted) synth()?.cancel();
  for (const fn of listeners) fn(muted);
}

export function say(text, { interrupt = false } = {}) {
  if (!text) return;
  spoken.push({ at: Date.now(), text, muted });
  console.info(`[voice${muted ? ', muted' : ''}] ${text}`);
  const s = synth();
  if (muted || !s) return;
  if (interrupt) s.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = RATE;
  u.lang = 'en-US';
  s.speak(u);
}

// Says `text` now and again every `everyMs` until the returned function runs.
export function repeat(text, everyMs) {
  say(text);
  const id = setInterval(() => say(text), everyMs);
  repeats.add(id);
  return () => { clearInterval(id); repeats.delete(id); };
}

export function stopAll() {
  for (const id of repeats) clearInterval(id);
  repeats.clear();
  synth()?.cancel();
}

export function vibrate(pattern) {
  try { navigator.vibrate?.(pattern); } catch { /* not supported */ }
}

// Wake Lock with a silent fallback. Returns a release function. Reacquires when the tab comes back.
export function keepAwake() {
  let lock = null;
  let released = false;
  async function acquire() {
    if (released || !navigator.wakeLock) return;
    try { lock = await navigator.wakeLock.request('screen'); } catch { lock = null; }
  }
  const onVisible = () => { if (document.visibilityState === 'visible') acquire(); };
  document.addEventListener('visibilitychange', onVisible);
  acquire();
  return () => {
    released = true;
    document.removeEventListener('visibilitychange', onVisible);
    lock?.release?.().catch(() => {});
    lock = null;
  };
}
