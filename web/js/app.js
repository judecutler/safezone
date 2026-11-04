import * as api from './api.js';
import * as db from './db.js';
import { EMERGENCY_SCREENS, initialScreen, next } from './machine.js';
import { toUploadJpeg } from './photo.js';
import { renderEmergency } from './screens/emergency.js';
import { renderPrepare } from './screens/prepare.js';

// `saved` is the committed plan the emergency screens use: { plan: Plan, shelters_error }.
// `draft` is what the prepare screens edit: { building, household, rooms }. Build commits it.
const state = {
  screen: 'start',
  saved: null,
  draft: null,
  guidance: null,
  images: {},
  emergency: null,
  ui: { busy: null, error: null, scanning: null },
};

const NO_NEEDS = { children: false, wheelchair: false, medical: false, pets: false };

const ERRORS = {
  offline: 'SafeZone could not reach its server. Check your connection and try again.',
  address_not_found: 'No match for that address. Check the street number and city, then try again.',
  decode: 'This photo could not be read. Try a JPEG, or take a new photo with the camera.',
};
const errorText = (e, fallback) => ERRORS[e?.code] ?? fallback;
const EDIT_SCREENS = new Set(['address', 'household', 'rooms']);

const hasPlan = () => Boolean(state.saved?.plan?.generated_at);

async function persist() {
  await db.putKV('saved', state.saved);
  await db.putKV('draft', state.draft);
}

function setUi(patch) {
  Object.assign(state.ui, patch);
  render();
}

async function go(event) {
  const from = state.screen;
  const to = next(from, event, { hasPlan: hasPlan() });
  if (event === 'cancel') { state.draft = null; await persist(); }
  if (EDIT_SCREENS.has(to) && !state.draft) state.draft = draftFromPlan();
  if (EMERGENCY_SCREENS.has(to) && !EMERGENCY_SCREENS.has(from)) await loadEmergency();
  state.screen = to;
  state.ui.error = null;
  history.pushState({ screen: to }, '', to === 'shaking' ? '?screen=emergency' : location.pathname);
  render();
  window.scrollTo(0, 0);
}

function draftFromPlan() {
  const p = state.saved?.plan;
  return p ? { building: p.building, household: p.household, rooms: p.rooms } : { building: null, household: { ...NO_NEEDS }, rooms: [] };
}

// The emergency screens read IndexedDB only, so what they show is exactly what survives offline.
async function loadEmergency() {
  const [saved, guidance] = await Promise.all([db.getKV('saved'), db.getKV('guidance')]);
  const rooms = saved?.plan?.rooms ?? [];
  state.emergency = { saved: saved ?? null, guidance: guidance ?? null, images: await db.loadImageUrls(rooms.map((r) => r.id)) };
}

const actions = {
  go,

  async lookupAddress(address) {
    if (!address.trim()) return;
    setUi({ busy: 'address', error: null });
    try {
      const building = await api.getProfile(address.trim());
      state.draft = { ...state.draft, building };
      await persist();
      setUi({ busy: null });
    } catch (e) {
      setUi({ busy: null, error: errorText(e, 'The address lookup did not respond. Try again in a minute.') });
    }
  },

  async toggleNeed(key) {
    state.draft.household = { ...state.draft.household, [key]: !state.draft.household[key] };
    await persist();
    render();
  },

  async scanPhoto(name, file) {
    const roomName = name.trim() || `Room ${state.draft.rooms.length + 1}`;
    let jpeg;
    try {
      jpeg = await toUploadJpeg(file);
    } catch {
      return setUi({ error: ERRORS.decode });
    }
    const preview = URL.createObjectURL(jpeg.blob);
    setUi({ busy: 'scan', error: null, scanning: { name: roomName, preview } });
    try {
      const scan = await api.scanRoom(roomName, jpeg.blob);
      await db.putImage(scan.id, jpeg.blob);
      state.images[scan.id] = preview;
      state.draft.rooms = [...state.draft.rooms.filter((r) => r.id !== scan.id), scan];
      await persist();
      setUi({ busy: null, scanning: null });
      document.getElementById(`room-${scan.id}`)?.scrollIntoView({ block: 'start' });
    } catch (e) {
      URL.revokeObjectURL(preview);
      setUi({ busy: null, scanning: null, error: errorText(e, 'The room scan did not finish. Try the photo again.') });
    }
  },

  async removeRoom(roomId) {
    state.draft.rooms = state.draft.rooms.filter((r) => r.id !== roomId);
    if (!state.saved?.plan?.rooms.some((r) => r.id === roomId)) await db.deleteImage(roomId);
    await persist();
    render();
  },

  async toggleFix(where, roomId, fixId) {
    const target = where === 'plan' ? state.saved.plan : state.draft;
    target.rooms = target.rooms.map((room) => room.id !== roomId ? room : {
      ...room, fixes: room.fixes.map((f) => (f.id === fixId ? { ...f, done: !f.done } : f)),
    });
    await persist();
    render();
  },

  async buildPlan() {
    const { building, household, rooms } = state.draft;
    setUi({ busy: 'build', error: null });
    try {
      const evac = await api.getEvac(building, household);
      state.saved = {
        plan: { building, household, rooms, route: evac.route, shelters: evac.shelters, generated_at: new Date().toISOString() },
        shelters_error: evac.shelters_error,
      };
      state.draft = null;
      await persist();
      state.ui.busy = null;
      await go('built');
    } catch (e) {
      setUi({ busy: null, error: errorText(e, 'The route and shelter lookup did not respond. Try again.') });
    }
  },

  async loadDemo() {
    setUi({ busy: 'demo', error: null });
    try {
      const { plan, images } = await api.getDemo();
      for (const [roomId, url] of Object.entries(images)) {
        const blob = await api.fetchBlob(url);
        await db.putImage(roomId, blob);
        state.images[roomId] = URL.createObjectURL(blob);
      }
      state.saved = { plan, shelters_error: null };
      state.draft = null;
      await persist();
      state.ui.busy = null;
      await go('open_plan');
    } catch (e) {
      setUi({ busy: null, error: errorText(e, 'The demo household did not load. Try again.') });
    }
  },

  async reset() {
    if (!confirm('Delete this plan and its photos from this device?')) return;
    const guidance = state.guidance;
    await db.clearAll();
    if (guidance) await db.putKV('guidance', guidance);
    Object.values(state.images).forEach(URL.revokeObjectURL);
    Object.assign(state, { saved: null, draft: null, images: {} });
    await go('reset');
  },
};

function render() {
  const root = document.getElementById('app');
  const emergency = EMERGENCY_SCREENS.has(state.screen);
  document.documentElement.dataset.mode = emergency ? 'emergency' : 'prepare';
  document.querySelector('meta[name=theme-color]').content = emergency ? '#000000' : '#ffffff';
  root.replaceChildren(emergency ? renderEmergency(state, actions) : renderPrepare(state, actions));
}

async function refreshGuidance() {
  try {
    state.guidance = await api.getGuidance();
    await db.putKV('guidance', state.guidance);
    render();
  } catch {
    // Offline: the stored copy from the last visit stays in use.
  }
}

async function boot() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  const [saved, draft, guidance] = await Promise.all([db.getKV('saved'), db.getKV('draft'), db.getKV('guidance')]);
  Object.assign(state, { saved: saved ?? null, draft: draft ?? null, guidance: guidance ?? null });
  const roomIds = [...(saved?.plan?.rooms ?? []), ...(draft?.rooms ?? [])].map((r) => r.id);
  state.images = await db.loadImageUrls([...new Set(roomIds)]);
  state.screen = initialScreen(location.search, { hasPlan: hasPlan() });
  if (EMERGENCY_SCREENS.has(state.screen)) await loadEmergency();
  history.replaceState({ screen: state.screen }, '');
  render();
  refreshGuidance();
}

window.addEventListener('popstate', async (e) => {
  const screen = e.state?.screen;
  if (!screen) return;
  if (EMERGENCY_SCREENS.has(screen) && !state.emergency) await loadEmergency();
  if (EDIT_SCREENS.has(screen) && !state.draft) state.draft = draftFromPlan();
  state.screen = screen;
  render();
});

boot();
