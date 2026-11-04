import assert from 'node:assert/strict';
import { test } from 'node:test';
import { frameStats, motion, shotQuality, tiltFromOrientation } from '../js/quality.js';

const W = 160, H = 120;

function frame(fn) {
  const data = new Uint8ClampedArray(W * H * 4);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const v = fn(x, y), p = (y * W + x) * 4;
    data[p] = data[p + 1] = data[p + 2] = v;
    data[p + 3] = 255;
  }
  return { data, width: W, height: H };
}

// A room-like scene: large flat areas with hard edges and a little fine texture.
const scene = (dx = 0) => (x, y) => {
  const X = x + dx;
  const block = ((Math.floor(X / 12) + Math.floor(y / 10)) % 2) ? 200 : 60;
  return block + ((X * 7 + y * 13) % 5) * 6;
};

function blur(f, passes) {
  let cur = f;
  for (let k = 0; k < passes; k++) {
    const out = new Uint8ClampedArray(cur.data);
    for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
      let s = 0;
      for (let j = -1; j <= 1; j++) for (let i = -1; i <= 1; i++) s += cur.data[((y + j) * W + x + i) * 4];
      const p = (y * W + x) * 4;
      out[p] = out[p + 1] = out[p + 2] = s / 9;
    }
    cur = { data: out, width: W, height: H };
  }
  return cur;
}

const quality = (f, extra = {}) => shotQuality({ ...frameStats(f), ...extra });

test('a sharp, steady, well-lit room passes with the doorway tip', () => {
  const q = quality(frame(scene()), { motion: 0.005, tiltDeg: 3, kind: 'room' });
  assert.equal(q.ok, true);
  assert.ok(q.score >= 0.75, String(q.score));
  assert.equal(q.hint, 'Stand in the doorway and fit the whole room in');
});

test('other shots that pass ask for the photo', () => {
  const q = quality(frame(scene()), { kind: 'gobag' });
  assert.equal(q.ok, true);
  assert.equal(q.hint, 'Looks good. Take the photo');
});

test('a dark frame says too dark first, even when it also shakes', () => {
  const dark = frame((x, y) => scene()(x, y) * 0.08);
  const q = quality(dark, { motion: 0.2, tiltDeg: 50 });
  assert.equal(q.ok, false);
  assert.match(q.hint, /^Too dark/);
  assert.ok(q.score < 0.4, String(q.score));
});

test('a blurred frame says blurry and scores lower than the sharp one', () => {
  const sharp = quality(frame(scene()));
  const soft = quality(blur(frame(scene()), 10));
  assert.equal(soft.ok, false);
  assert.match(soft.hint, /^Blurry/);
  assert.ok(soft.score < sharp.score);
  assert.ok(frameStats(blur(frame(scene()), 10)).sharpness < frameStats(frame(scene())).sharpness / 10);
});

test('moving frames say hold still before blur or tilt', () => {
  const a = frame(scene(0)), b = frame(scene(9));
  const moved = motion(a, b);
  assert.ok(moved > 0.08, String(moved));
  assert.equal(motion(a, a), 0);
  const q = quality(blur(b, 6), { motion: moved, tiltDeg: 45 });
  assert.equal(q.hint, 'Hold still');
});

test('a tilted phone asks for upright and level; unknown tilt costs nothing', () => {
  const f = frame(scene());
  assert.equal(quality(f, { tiltDeg: 35 }).hint, 'Hold the phone upright and level');
  assert.equal(quality(f, { tiltDeg: 35 }).ok, false);
  assert.equal(quality(f, { tiltDeg: null }).ok, true);
});

test('the score rises as each problem clears', () => {
  const sharp = frame(scene());
  const steps = [
    quality(frame((x, y) => scene()(x, y) * 0.1)),
    quality(blur(sharp, 10), { motion: 0.05 }),
    quality(blur(sharp, 2)),
    quality(sharp, { motion: 0.004, tiltDeg: 2 }),
  ];
  for (let i = 1; i < steps.length; i++) assert.ok(steps[i].score > steps[i - 1].score, steps.map((s) => s.score.toFixed(2)).join(' '));
});

test('a blank wall asks for the scene', () => {
  const q = quality(frame(() => 180));
  assert.equal(q.ok, false);
  assert.match(q.hint, /^(Blurry|Point)/);
});

test('tilt from orientation: upright portrait and landscape are level, pointing down and rolled are not', () => {
  assert.ok(tiltFromOrientation(90, 0) < 1);
  assert.ok(tiltFromOrientation(0, 90) < 1, 'landscape held level');
  assert.ok(tiltFromOrientation(60, 0) > 25, 'pointing down');
  assert.ok(tiltFromOrientation(80, 30) < 15, 'turning left or right while upright is not tilt');
  const rolled = tiltFromOrientation(60, 90);
  assert.ok(Math.abs(rolled - 30) < 1, `rolled 30 degrees in the screen plane: ${rolled}`);
  assert.equal(tiltFromOrientation(null, null), null);
});
