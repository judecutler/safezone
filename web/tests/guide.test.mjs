import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { haversine } from '../js/geometry.js';
import { BACK_FIXES, FAR_M, OFF_ROUTE_M, cue, insideHazard, pointAlong, progress, routeLength, stepPoints } from '../js/guide.js';

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

// Collects every cue for a list of fixes, as the emergency screen does.
function run(fixes, opts = {}) {
  const said = [];
  let last = null, prev = null;
  for (const f of fixes) {
    const prog = progress(route, f, prev, opts.accuracyM ?? 0);
    prev = prog;
    const c = cue(route, prog, last, { outsideHazard: opts.outside ? opts.outside(f) : !insideHazard(hazard, f), ...opts });
    if (c) { said.push(c); last = c; }
  }
  return said;
}
const along = (a, b, step = 1.4) => { const out = []; for (let m = a; step > 0 ? m <= b : m >= b; m += step) out.push(pointAlong(route, m)); return out; };

test('walking the route backward, toward the water, says turn around and never reads the passed turns again', () => {
  const said = run([...along(0, 300), ...along(300, 0, -1.4)]);
  const back = said.findIndex((c) => c.key === 'back');
  assert.ok(back > 0, 'a turn-around cue');
  assert.match(said[back].text, /Turn around/);
  assert.deepEqual(said.slice(back + 1), [], 'nothing else is said on the way back');
  const fromEnd = run(along(routeLength(route), 0, -1.4));
  assert.equal(fromEnd[0].key, 'arrive');
  assert.ok(fromEnd.some((c) => c.key === 'back'));
  assert.ok(!fromEnd.some((c) => c.key.endsWith(':now') && c.key !== 'step:5:now'), `no turn re-announced: ${fromEnd.map((c) => c.text).join(' | ')}`);
});

test('GPS noise never says turn around and never announces a passed turn a second time', () => {
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5; };
  for (let trial = 0; trial < 6; trial++) {
    const fixes = along(0, routeLength(route)).map((p) => offset(p, rnd() * 40, rnd() * 40));
    const said = run(fixes);
    assert.ok(!said.some((c) => c.key === 'back'), `trial ${trial}: no turn-around under +-20 m noise`);
    const nows = said.filter((c) => c.key.endsWith(':now')).map((c) => c.key);
    assert.deepEqual(nows, [...new Set(nows)], `trial ${trial}: each turn announced once: ${nows}`);
    for (let i = 1; i < nows.length; i++) assert.ok(nows[i] > nows[i - 1], `trial ${trial}: turns in order`);
  }
  assert.ok(BACK_FIXES >= 3, 'a reversal needs several fixes in a row');
});

test('a fix the map cannot place (no polygons, or beyond them) is never called outside the hazard area', () => {
  const unknown = () => null;
  const beach = offset(route.origin, -300, 0);
  const far = offset(route.origin, -1000, -3000);
  for (const c of run([beach], { outside: unknown })) assert.doesNotMatch(c.text, /outside the mapped/);
  for (const c of run([far], { outside: unknown })) assert.doesNotMatch(c.text, /outside the mapped/);
  assert.match(run([far], { outside: unknown })[0].text, /inland and uphill/);
  const arrived = run([route.destination], { outside: unknown });
  assert.equal(arrived[0].key, 'arrive');
  assert.doesNotMatch(arrived[0].text, /outside the mapped/);
});

test('arrival at a designated site (Japan) says the site instruction, not "outside the hazard area"', () => {
  const site = 'Evacuation building: go to the upper floors.';
  const said = run(along(routeLength(route) - 60, routeLength(route)), { outside: () => null, siteInstruction: site });
  assert.equal(said.at(-1).key, 'arrive');
  assert.equal(said.at(-1).text, `You have reached the end of the route. ${site}`);
});

// Standby: the detector that decides "sustained shaking" is pure, so it is checked here too.
import { markMotionTrigger, motionTriggered, shakeDetector } from '../js/standby.js';

test('a motion-sensor opening is remembered so the shaking screen leaves only through its button', () => {
  assert.equal(motionTriggered(0), false);
  markMotionTrigger(1000);
  assert.equal(motionTriggered(1000 + 60000), true);
  assert.equal(motionTriggered(1000 + 11 * 60 * 1000), false);
});

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
