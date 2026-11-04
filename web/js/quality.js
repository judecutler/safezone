// Live shot quality from small downscaled frames. Pure: frames are { data, width, height } RGBA,
// the shape of ImageData, so tests can build them by hand.

const LIGHT = { zero: 0.06, one: 0.3, pass: 0.16 };
const CONTRAST = { zero: 0.02, one: 0.12, pass: 0.05 };
const SHARP = { zero: 15, one: 300, pass: 60 };
const MOTION = { one: 0.015, zero: 0.08, pass: 0.035 };
const TILT = { one: 8, zero: 40, pass: 20 };

const ramp = (x, zero, one) => Math.min(1, Math.max(0, (x - zero) / (one - zero)));

function grey({ data, width, height }) {
  const g = new Float32Array(width * height);
  for (let i = 0, p = 0; i < g.length; i++, p += 4) g[i] = 0.299 * data[p] + 0.587 * data[p + 1] + 0.114 * data[p + 2];
  return g;
}

export function frameStats(frame) {
  const { width: w, height: hgt } = frame;
  const g = grey(frame);
  let sum = 0, sq = 0;
  for (const v of g) { sum += v; sq += v * v; }
  const mean = sum / g.length;
  const std = Math.sqrt(Math.max(0, sq / g.length - mean * mean));

  let lsum = 0, lsq = 0, n = 0;
  for (let y = 1; y < hgt - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const lap = g[i - 1] + g[i + 1] + g[i - w] + g[i + w] - 4 * g[i];
      lsum += lap; lsq += lap * lap; n++;
    }
  }
  const lmean = n ? lsum / n : 0;
  return { luma: mean / 255, contrast: std / 255, sharpness: n ? lsq / n - lmean * lmean : 0 };
}

// Mean absolute grey difference between two frames of the same size, 0..1.
export function motion(prev, cur) {
  if (!prev || prev.width !== cur.width || prev.height !== cur.height) return 0;
  const a = grey(prev), b = grey(cur);
  let d = 0;
  for (let i = 0; i < a.length; i++) d += Math.abs(a[i] - b[i]);
  return d / a.length / 255;
}

// Degrees away from a level, upright phone, from deviceorientation beta and gamma. Portrait and
// landscape both count as level; pointing up or down counts as tilt.
export function tiltFromOrientation(beta, gamma) {
  if (beta == null || gamma == null) return null;
  const b = (beta * Math.PI) / 180, g = (gamma * Math.PI) / 180;
  const gx = Math.sin(g) * Math.cos(b), gy = -Math.sin(b), gz = -Math.cos(g) * Math.cos(b);
  const pitch = (Math.asin(Math.min(1, Math.abs(gz))) * 180) / Math.PI;
  const roll = Math.abs((Math.atan2(gx, -gy) * 180) / Math.PI) % 90;
  return Math.max(pitch, Math.min(roll, 90 - roll));
}

const ROOM_TIP = 'Stand in the doorway and fit the whole room in';

// One hint at a time, the most important first. `tiltDeg` null means unknown and costs nothing.
export function shotQuality({ luma, contrast, sharpness, motion: moved = 0, tiltDeg = null, kind = null }) {
  const parts = {
    light: ramp(luma, LIGHT.zero, LIGHT.one),
    still: 1 - ramp(moved, MOTION.one, MOTION.zero),
    level: tiltDeg == null ? 1 : 1 - ramp(tiltDeg, TILT.one, TILT.zero),
    sharp: ramp(sharpness, SHARP.zero, SHARP.one),
    detail: ramp(contrast, CONTRAST.zero, CONTRAST.one),
  };
  const checks = [
    [luma < LIGHT.pass, 'Too dark. Turn on a light or open the curtains'],
    [moved > MOTION.pass, 'Hold still'],
    [tiltDeg != null && tiltDeg > TILT.pass, 'Hold the phone upright and level'],
    [sharpness < SHARP.pass, 'Blurry. Wipe the lens and hold still'],
    [contrast < CONTRAST.pass, 'Point the camera at the scene'],
  ];
  const failed = checks.find(([bad]) => bad);
  const values = Object.values(parts);
  const score = 0.5 * Math.min(...values) + 0.5 * (values.reduce((a, b) => a + b, 0) / values.length);
  const ok = !failed;
  const hint = failed ? failed[1] : kind === 'room' ? ROOM_TIP : 'Looks good. Take the photo';
  return { score: ok ? Math.max(score, 0.75) : Math.min(score, 0.7), ok, hint };
}
