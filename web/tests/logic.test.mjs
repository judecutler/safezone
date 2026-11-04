import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { test } from 'node:test';
import { fitView, formatDistance, haversine, layoutBalloons, localFrame, niceLength } from '../js/geometry.js';
import { EMERGENCY_SCREENS, TRANSITIONS, initialScreen, next } from '../js/machine.js';

const WEB = new URL('..', import.meta.url).pathname;

test('emergency is reachable from every screen and leaves to the plan only when one exists', () => {
  for (const screen of Object.keys(TRANSITIONS)) assert.equal(next(screen, 'emergency', { hasPlaces: false }), 'shaking');
  assert.equal(next('shelters', 'exit_emergency', { hasPlaces: true }), 'places');
  assert.equal(next('shaking', 'exit_emergency', { hasPlaces: false }), 'landing');
});

test('the shaking screen has exactly one way forward, and it does not route', () => {
  assert.deepEqual(TRANSITIONS.shaking, { stopped: 'after' });
});

test('unknown events throw instead of silently staying put', () => {
  assert.throws(() => next('landing', 'stopped', { hasPlaces: false }));
});

test('every transition target is a real screen', () => {
  const screens = new Set(Object.keys(TRANSITIONS));
  for (const edges of Object.values(TRANSITIONS)) for (const to of Object.values(edges)) assert.ok(screens.has(to), to);
  for (const s of EMERGENCY_SCREENS) assert.ok(screens.has(s));
});

test('the manifest shortcut opens the shaking screen', () => {
  assert.equal(initialScreen('?screen=emergency', { hasPlaces: false }), 'shaking');
  assert.equal(initialScreen('', { hasPlaces: true }), 'places');
  assert.equal(initialScreen('', { hasPlaces: false }), 'landing');
});

test('the local frame agrees with haversine within 0.5% over a few km', () => {
  const a = [-122.51, 37.77], b = [-122.47, 37.79];
  const [x, y] = localFrame(a)(b);
  const d = haversine(a, b);
  assert.ok(Math.abs(Math.hypot(x, y) - d) / d < 0.005);
  assert.ok(x > 0 && y > 0, 'east and north are positive');
});

test('fitView keeps every point inside and holds the aspect', () => {
  const v = fitView({ minX: -50, minY: 0, maxX: 400, maxY: 60 }, { aspect: 1.25 });
  assert.ok(v.minX <= -50 && v.minX + v.w >= 400 && v.minY <= 0 && v.minY + v.h >= 60);
  assert.ok(Math.abs(v.w / v.h - 1.25) < 1e-9);
});

test('scale bar lengths are round numbers', () => {
  assert.equal(niceLength(130), 100);
  assert.equal(niceLength(260), 200);
  assert.equal(niceLength(999), 500);
  assert.equal(formatDistance(343), '340 m');
  assert.equal(formatDistance(1520), '1.5 km');
});

test('callout balloons do not overlap and stay inside the image', () => {
  const r = 40;
  const pos = layoutBalloons([[100, 100], [110, 100], [120, 105], [1590, 5]], 1600, 900, r);
  for (const [x, y] of pos) assert.ok(x >= r && x <= 1600 - r && y >= r && y <= 900 - r);
  for (let i = 0; i < pos.length; i++)
    for (let j = i + 1; j < pos.length; j++)
      assert.ok(Math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]) >= 2 * r);
});

function files(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

test('the service worker precaches every shell file, so the app opens offline', () => {
  const sw = readFileSync(join(WEB, 'sw.js'), 'utf8');
  const list = sw.slice(sw.indexOf('const SHELL = ['), sw.indexOf('];'));
  const shell = new Set([...list.matchAll(/'(\/[^']*)'/g)].map((m) => m[1]));
  const needed = files(WEB).map((p) => '/' + relative(WEB, p)).filter((p) => !p.startsWith('/tests/') && p !== '/sw.js');
  for (const p of needed) assert.ok(shell.has(p), `${p} missing from SHELL in sw.js`);
  for (const p of shell) if (p !== '/') assert.ok(needed.includes(p), `${p} in SHELL but not on disk`);
});
