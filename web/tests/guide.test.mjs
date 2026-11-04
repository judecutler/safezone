import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { haversine } from '../js/geometry.js';
import { FAR_M, OFF_ROUTE_M, cue, insideHazard, pointAlong, progress, routeLength, stepPoints } from '../js/guide.js';

const plan = JSON.parse(readFileSync(new URL('../../demo/plan.json', import.meta.url))).plan;
const route = plan.route;
const hazard = plan.building.hazard_area.polygons;

// Moves a point by metres east and north, for off-route positions.
function offset([lon, lat], eastM, northM) {
  const kLat = 1 / 111195;
  return [lon + (eastM * kLat) / Math.cos((lat * Math.PI) / 180), lat + northM * kLat];
}

// Walks the real route at 1.4 m/s with one GPS fix a second and collects every cue, as the emergency screen does.
function walk(fromM = 0, toM = routeLength(route), stepM = 1.4) {
  const said = [];
  let last = null, prev = null;
  for (let m = fromM; m <= toM + stepM; m += stepM) {
    const prog = progress(route, pointAlong(route, Math.min(m, toM)), prev);
    prev = prog;
    const c = cue(route, prog, last, { outsideHazard: !insideHazard(hazard, pointAlong(route, Math.min(m, toM))) });
    if (c) { said.push({ m: Math.round(m), ...c }); last = c; }
  }
  return said;
}

test('every step lands on the path at its cumulative distance and the last one is the end', () => {
  const pts = stepPoints(route);
  assert.equal(pts.length, route.steps.length);
  assert.equal(pts[0].atM, 0);
  for (let i = 1; i < pts.length; i++) assert.ok(pts[i].atM > pts[i - 1].atM, `step ${i} is after step ${i - 1}`);
  assert.ok(Math.abs(pts.at(-1).atM - routeLength(route)) < 1, 'Arrive sits at the end of the path');
  assert.ok(haversine(pts.at(-1).at, route.destination) < 1, 'Arrive is at the destination');
  assert.ok(Math.abs(routeLength(route) - route.distance_m) < 2, 'path length matches OSRM distance');
});

test('on the route: the first cue is the first maneuver and the heading-out distance is right', () => {
  const prog = progress(route, pointAlong(route, 0));
  assert.ok(prog.offRouteM < 1);
  assert.equal(prog.stepIndex, 0);
  const first = cue(route, prog, null);
  assert.equal(first.text, `${route.steps[0].instruction}.`);
  const after10 = progress(route, pointAlong(route, 10), prog);
  assert.equal(after10.stepIndex, 1);
  assert.ok(Math.abs(after10.metersToNext - (route.steps[0].distance_m - 10)) < 1);
  const pastFirst = route.steps[0].distance_m + 10;
  assert.equal(progress(route, pointAlong(route, pastFirst), after10).stepIndex, 2, 'past the first turn');
});

test('approaching a turn: far, near and now phases in order, each once', () => {
  const said = walk(0, route.steps[0].distance_m + 60);
  const texts = said.map((s) => s.text);
  const next = route.steps[1].instruction.toLowerCase();
  assert.equal(texts[0], `${route.steps[0].instruction}.`);
  const near = texts.findIndex((t) => /^In \d+ meters, /.test(t) && t.endsWith(`${next}.`));
  const now = texts.indexOf(`${route.steps[1].instruction}.`);
  assert.ok(near > 0 && now > near, `near then now for "${next}": ${texts.join(' | ')}`);
});

test('a full walk says every maneuver once, never repeats a cue, and ends with arrival outside the hazard area', () => {
  const said = walk();
  const keys = said.map((s) => s.key);
  assert.equal(new Set(keys).size, keys.length, 'no cue key repeats');
  for (let i = 1; i < said.length; i++) assert.notEqual(said[i].text, said[i - 1].text);
  const nowCues = said.filter((s) => s.key.endsWith(':now')).map((s) => s.text);
  assert.deepEqual(nowCues, route.steps.slice(0, -1).map((s) => `${s.instruction}.`));
  assert.equal(said.at(-1).key, 'arrive');
  assert.match(said.at(-1).text, /outside the mapped tsunami hazard area/);
  assert.ok(!insideHazard(hazard, route.destination), 'the destination is outside the CGS hazard polygons');
  assert.ok(insideHazard(hazard, route.origin), 'the origin is inside them');
  for (const s of said) assert.doesNotMatch(s.text.replace('officials say it is safe', ''), /\bsafe\b/i, 'SafeZone never calls anything safe itself');
});

test('standing still on the route produces one cue, not a cue every second', () => {
  const pos = pointAlong(route, 100);
  let last = null, prev = null, count = 0;
  for (let i = 0; i < 30; i++) {
    const prog = progress(route, pos, prev);
    prev = prog;
    const c = cue(route, prog, last);
    if (c) { count++; last = c; }
  }
  assert.equal(count, 1);
});

test('off route: says which way the route is, once, then resumes turn cues when back on it', () => {
  const on = pointAlong(route, 150);
  const prevProg = progress(route, on);
  const away = offset(on, 80, 0);
  const prog = progress(route, away, prevProg);
  assert.ok(prog.offRouteM > OFF_ROUTE_M && prog.offRouteM < FAR_M, `off by ${prog.offRouteM}`);
  assert.equal(prog.bearingToRoute, 'west');
  const c = cue(route, prog, null);
  assert.equal(c.text, 'You are off the route. It is 80 meters to your west.');
  assert.equal(cue(route, progress(route, away, prog), c), null, 'not repeated while still off');
  const back = cue(route, progress(route, on, prog), c);
  assert.ok(back && back.key.startsWith('step:'), 'turn cues resume');
});

test('off route but already outside the hazard polygons: never pointed back toward the route', () => {
  const outsideSpot = offset(route.destination, 120, 60);
  assert.ok(!insideHazard(hazard, outsideSpot));
  const prog = progress(route, outsideSpot);
  assert.ok(prog.offRouteM > OFF_ROUTE_M && !prog.arrived);
  const c = cue(route, prog, null, { outsideHazard: true });
  assert.equal(c.key, 'arrive');
  assert.match(c.text, /outside the mapped tsunami hazard area/);
  assert.doesNotMatch(c.text, /to your/);
});

test('a fix whose error radius still covers the route is treated as on the route', () => {
  const on = pointAlong(route, 150);
  const prog = progress(route, offset(on, 60, 0), progress(route, on));
  assert.ok(prog.offRouteM > OFF_ROUTE_M);
  assert.equal(cue(route, prog, null, { accuracyM: 50 }).key.startsWith('step:'), true);
  assert.equal(cue(route, prog, null, { accuracyM: 10 }).key.startsWith('off:'), true);
});

test('far off route falls back to the fixed inland-and-uphill line', () => {
  const far = offset(route.origin, 0, -600);
  const c = cue(route, progress(route, far), null);
  assert.equal(c.key, 'far');
  assert.match(c.text, /inland and uphill/);
});

test('arrival near the destination fires even when the fix is a few metres past the path end', () => {
  const past = offset(route.destination, 10, 10);
  const prog = progress(route, past);
  assert.ok(prog.arrived);
  assert.equal(cue(route, prog, null).key, 'arrive');
});

test('a route with no steps gives no cue instead of throwing', () => {
  const bare = { ...route, steps: [] };
  assert.equal(cue(bare, progress(bare, route.origin), null), null);
});

// Standby: the detector that decides "sustained shaking" is pure, so it is checked here too.
import { shakeDetector } from '../js/standby.js';

test('standby ignores a single jolt and fires on two seconds of strong shaking', () => {
  const det = shakeDetector();
  let fired = false;
  for (let t = 0; t < 3000; t += 20) fired = det.push(t, t === 1000 ? 25 : 0.3) || fired;
  assert.equal(fired, false, 'one jolt');
  det.reset();
  fired = false;
  for (let t = 0; t < 1500; t += 20) fired = det.push(t, 9) || fired;
  assert.equal(fired, false, 'strong but under two seconds');
  for (let t = 1500; t < 2400; t += 20) fired = det.push(t, 9) || fired;
  assert.equal(fired, true, 'strong for two seconds');
});
