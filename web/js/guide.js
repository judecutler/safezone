import { haversine, localFrame } from './geometry.js';

// Pure turn-by-turn math over a server route: { path: [[lon, lat]], steps: [{ instruction, distance_m }], destination }.
// Each step's distance_m is the length of the leg that follows its maneuver, so maneuver i sits at the
// cumulative distance of steps 0..i-1 along the path. Nothing here speaks or touches the DOM.

const NEAR_M = 40;
const NOW_M = 12;
const ARRIVE_M = 20;
export const OFF_ROUTE_M = 35;
export const FAR_M = 400;

const roundTen = (m) => Math.max(10, Math.round(m / 10) * 10);

// Spoken wording. Route instructions come from the server as they are; only the connective words live here.
const WORDS = {
  continueThen: (m, instruction) => `Continue ${roundTen(m)} meters, then ${lower(instruction)}.`,
  inMeters: (m, instruction) => `In ${roundTen(m)} meters, ${lower(instruction)}.`,
  now: (instruction) => `${instruction}.`,
  off: (m, compass) => `You are off the route. It is ${roundTen(m)} meters to your ${compass}.`,
  far: 'You are far from this route. Walk inland and uphill, away from the water, and follow tsunami evacuation signs.',
  arrivedOutside: 'You have reached the end of the route, outside the mapped tsunami hazard area. If you can, keep moving inland and uphill.',
  arrivedUnchecked: 'You have reached the end of the route. If you can, keep moving inland and uphill.',
  outside: 'You are outside the mapped tsunami hazard area. Stay there until officials say it is safe. If you can, keep moving inland and uphill.',
};

const lower = (t) => t.charAt(0).toLowerCase() + t.slice(1);

// Path legs with cumulative distance, in a local metric frame so projection is plain geometry.
function legs(route) {
  const project = localFrame(route.origin ?? route.path[0]);
  const pts = route.path.map((ll) => ({ ll, xy: project(ll) }));
  const out = [];
  let acc = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const len = haversine(pts[i].ll, pts[i + 1].ll);
    out.push({ a: pts[i], b: pts[i + 1], startM: acc, lenM: len });
    acc += len;
  }
  return { project, legs: out, totalM: acc };
}

export function pointAlong(route, meters) {
  const { legs: L, totalM } = legs(route);
  const m = Math.min(Math.max(meters, 0), totalM);
  for (const leg of L) {
    if (m <= leg.startM + leg.lenM || leg === L[L.length - 1]) {
      const t = leg.lenM ? Math.min(1, (m - leg.startM) / leg.lenM) : 0;
      const [lon1, lat1] = leg.a.ll, [lon2, lat2] = leg.b.ll;
      return [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t];
    }
  }
  return route.path[route.path.length - 1];
}

export function routeLength(route) {
  return legs(route).totalM;
}

export function stepPoints(route) {
  const steps = route.steps ?? [];
  const { totalM } = legs(route);
  let acc = 0;
  return steps.map((st, index) => {
    const atM = index === steps.length - 1 ? totalM : Math.min(acc, totalM);
    acc += st.distance_m;
    return { index, instruction: st.instruction, atM, at: pointAlong(route, atM) };
  });
}

function compass16(bearingDeg) {
  const names = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'];
  return names[Math.round((((bearingDeg % 360) + 360) % 360) / 45) % 8];
}

// Nearest point on the path to `pos`. With `prev`, legs near the previous along-track distance win when they
// are within the off-route threshold, so a parallel street later on the route cannot steal the position.
function snap(route, pos, prev) {
  const { project, legs: L } = legs(route);
  const [px, py] = project(pos);
  const candidates = L.map((leg) => {
    const [ax, ay] = leg.a.xy, [bx, by] = leg.b.xy;
    const dx = bx - ax, dy = by - ay;
    const d2 = dx * dx + dy * dy;
    const t = d2 ? Math.min(1, Math.max(0, ((px - ax) * dx + (py - ay) * dy) / d2)) : 0;
    const qx = ax + dx * t, qy = ay + dy * t;
    const dist = Math.hypot(px - qx, py - qy);
    const alongM = leg.startM + leg.lenM * t;
    const bearing = (Math.atan2(qx - px, qy - py) * 180) / Math.PI;
    return { dist, alongM, bearing };
  });
  if (prev) {
    const nearby = candidates.filter((c) => c.alongM >= prev.alongM - 50 && c.alongM <= prev.alongM + 150 && c.dist <= OFF_ROUTE_M);
    if (nearby.length) return nearby.reduce((a, b) => (b.dist < a.dist ? b : a));
  }
  return candidates.reduce((a, b) => (b.dist < a.dist ? b : a));
}

export function progress(route, pos, prev = null) {
  const points = stepPoints(route);
  const totalM = routeLength(route);
  const s = snap(route, pos, prev);
  const toDestination = haversine(pos, route.destination ?? route.path[route.path.length - 1]);
  const arrived = toDestination <= ARRIVE_M || (s.dist <= OFF_ROUTE_M && totalM - s.alongM <= ARRIVE_M);
  // The next maneuver is the first one still ahead, with a few meters of slack so a turn is not "ahead" forever.
  let stepIndex = points.findIndex((p, i) => i > 0 && p.atM > s.alongM + 3);
  if (stepIndex < 0) stepIndex = Math.max(points.length - 1, 0);
  if (s.alongM <= 3 && points.length) stepIndex = 0;
  const metersToNext = points.length ? Math.max(0, points[stepIndex].atM - s.alongM) : 0;
  return {
    alongM: s.alongM,
    offRouteM: s.dist,
    bearingToRoute: compass16(s.bearing),
    stepIndex,
    metersToNext,
    toDestinationM: toDestination,
    arrived,
  };
}

// Even-odd test over CGS polygons: [[ring, ring...]], each ring [[lon, lat]...]. Matches the map's fill rule.
export function insideHazard(polygons, [lon, lat]) {
  let inside = false;
  for (const poly of polygons ?? []) {
    for (const ring of poly) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
      }
    }
  }
  return inside;
}

// The one line to say for this progress, or null. `lastCue` is the previous cue this function returned.
// Keys name a step and a phase, so the same phase is never spoken twice in a row however often this runs.
// `accuracyM` is the fix's own error radius: a fix that could still be on the route is treated as on it, so a
// poor indoor fix at the start never sends someone the wrong way.
export function cue(route, prog, lastCue, { outsideHazard = null, accuracyM = 0 } = {}) {
  const points = stepPoints(route);
  const off = prog.offRouteM > OFF_ROUTE_M + accuracyM;
  let next;
  // Once the walker is outside the hazard polygons, no cue points back toward the route (which may lie seaward).
  if (prog.arrived || (outsideHazard === true && off)) {
    next = { key: 'arrive', text: outsideHazard === false ? WORDS.arrivedUnchecked : prog.arrived ? WORDS.arrivedOutside : WORDS.outside };
  } else if (off && prog.offRouteM > FAR_M) {
    next = { key: 'far', text: WORDS.far };
  } else if (off) {
    next = { key: `off:${prog.bearingToRoute}`, text: WORDS.off(prog.offRouteM, prog.bearingToRoute) };
  } else if (points.length) {
    const p = points[prog.stepIndex];
    const last = prog.stepIndex === points.length - 1;
    if (prog.metersToNext <= NOW_M && !last) next = { key: `step:${p.index}:now`, text: WORDS.now(p.instruction) };
    else if (prog.metersToNext <= NEAR_M) next = { key: `step:${p.index}:near`, text: WORDS.inMeters(prog.metersToNext, p.instruction) };
    else next = { key: `step:${p.index}:next`, text: WORDS.continueThen(prog.metersToNext, p.instruction) };
  } else {
    return null;
  }
  if (lastCue && lastCue.key === next.key) return null;
  // A step phase already passed is not re-announced when the walker skips a phase between two fixes.
  if (lastCue && sameStep(lastCue.key, next.key) && phaseRank(lastCue.key) >= phaseRank(next.key)) return null;
  return next;
}

const sameStep = (a, b) => a.split(':').slice(0, 2).join(':') === b.split(':').slice(0, 2).join(':') && a.startsWith('step:');
const phaseRank = (key) => ({ next: 0, near: 1, now: 2 })[key.split(':')[2]] ?? 0;
