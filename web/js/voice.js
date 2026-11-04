// The one place that talks, buzzes and keeps the screen on. Screens never touch speechSynthesis directly.
// Every line goes through `say`, which also records it in `spoken` and the console, so a test or a headless
// browser can read the sequence when speech is unavailable.
//
// Queue rules: lines play in order. A line marked `replace` is a guidance cue; a newer cue replaces any cue
// still waiting, so a walker never hears a stale turn after a long official line. `interrupt` cuts whatever
// is playing. Muting records lines without playing them.

const RATE = 0.95;
const synth = () => (typeof speechSynthesis === 'undefined' ? null : speechSynthesis);

export const spoken = [];
let muted = false;
let playing = false;
const queue = [];
const repeats = new Set();
const listeners = new Set();

export function onVoiceChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const isMuted = () => muted;

export function setMuted(value) {
  muted = Boolean(value);
  if (muted) { queue.length = 0; playing = false; synth()?.cancel(); }
  for (const fn of listeners) fn(muted);
}

function playNext() {
  const s = synth();
  if (playing || !s || !queue.length) return;
  const item = queue.shift();
  playing = true;
  const u = new SpeechSynthesisUtterance(item.text);
  u.rate = RATE;
  u.lang = 'en-US';
  const done = () => { playing = false; playNext(); };
  u.onend = done;
  u.onerror = done;
  s.speak(u);
  // Some engines never fire onend after cancel(); a timer bounded by reading speed keeps the queue moving.
  setTimeout(() => { if (playing && !s.speaking) done(); }, 1000 + item.text.length * 90);
}

// iOS Safari speaks only if speech first starts inside a tap. The demo and the emergency start talking after a
// timer, so the first tap anywhere speaks one silent, empty line to unlock speech for the rest of the session.
let primed = false;
function prime() {
  const s = synth();
  if (primed || !s) return;
  primed = true;
  const u = new SpeechSynthesisUtterance('');
  u.volume = 0;
  s.speak(u);
  for (const type of PRIME_EVENTS) document.removeEventListener(type, prime, true);
}
const PRIME_EVENTS = ['touchend', 'pointerup', 'keydown'];
if (typeof document !== 'undefined') for (const type of PRIME_EVENTS) document.addEventListener(type, prime, true);

export function say(text, { interrupt = false, replace = false } = {}) {
  if (!text) return;
  spoken.push({ at: Date.now(), text, muted });
  console.info(`[voice${muted ? ', muted' : ''}] ${text}`);
  if (muted || !synth()) return;
  if (interrupt) { queue.length = 0; playing = false; synth().cancel(); }
  if (replace) for (let i = queue.length - 1; i >= 0; i--) if (queue[i].replace) queue.splice(i, 1);
  queue.push({ text, replace });
  playNext();
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
  queue.length = 0;
  playing = false;
  synth()?.cancel();
}

// Browsers refuse vibration before the first tap and log an error, so a cold start from the emergency link skips it.
export function vibrate(pattern) {
  if (navigator.userActivation && !navigator.userActivation.hasBeenActive) return;
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
