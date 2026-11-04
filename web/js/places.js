import { getKV, putKV } from './db.js';
import { haversine } from './geometry.js';

// A Place is a finished setup: { id, name, kind, demo, plan, saved_at }. `plan` keeps the shape the plan page
// and the emergency screens already read, plus `extras` for the non-room photos and the go-bag check.

export const loadPlaces = async () => (await getKV('places')) ?? [];
export const savePlaces = (places) => putKV('places', places);

export const placeCoords = (place) => {
  const b = place?.plan?.building;
  return b && Number.isFinite(b.lon) && Number.isFinite(b.lat) ? [b.lon, b.lat] : null;
};

export function nearestPlace(places, lonlat) {
  let best = null, bestM = Infinity;
  for (const p of places ?? []) {
    const c = placeCoords(p);
    if (!c) continue;
    const m = haversine(c, lonlat);
    if (m < bestM) { best = p; bestM = m; }
  }
  return best ? { place: best, distance_m: bestM } : null;
}

// Hazard flag for the list, on the severity scale. The CGS answer is the only thing that moves it.
export function hazardLevel(place) {
  const area = place?.plan?.building?.hazard_area;
  if (!area) return { sev: 2, text: 'Tsunami map not checked' };
  return area.contains_home ? { sev: 4, text: 'In the tsunami hazard area' } : { sev: 1, text: 'Outside the mapped hazard area' };
}

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`);

export function placeFromSession(session, name, kind, { demo = false, id = newId() } = {}) {
  const done = (k) => session.shots.filter((s) => s.kind === k && s.status === 'done');
  const first = (k) => done(k)[0];
  const extras = {};
  if (first('exit')) extras.exit = first('exit').image_id;
  if (first('gas')) extras.gas = first('gas').image_id;
  if (first('gobag')?.result) extras.gobag = first('gobag').result;
  const evac = session.evac ?? {};
  return {
    id, name: name?.trim() || 'Home', kind: kind ?? 'home', demo: Boolean(demo),
    plan: {
      building: session.location?.building ?? null,
      household: { children: false, wheelchair: false, medical: false, pets: false, ...session.household },
      rooms: done('room').map((s) => ({ ...s.result, name: s.name || s.result.name })),
      route: evac.route ?? null,
      shelters: evac.shelters ?? null,
      shelters_error: evac.shelters_error ?? null,
      generated_at: new Date().toISOString(),
      extras,
    },
    saved_at: new Date().toISOString(),
  };
}
