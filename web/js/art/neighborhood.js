import { s } from '../dom.js';
import { evacMarks } from './signs.js';

// A top-down coastal neighbourhood, drawn procedurally from a fixed seed so it is identical on every load.
// Ocean at left, beach, coast road, a low street grid inside the hazard area, and contoured high ground at right.
// The loop (landing.css): calm, shaking, a tsunami floods the low blocks up to the hazard line, it recedes.

const SHORE = (y) => 58 + 5 * Math.sin(y / 53) + 3 * Math.sin(y / 17);
const COAST = (y) => 92 + 3 * Math.sin(y / 120);
const HAZARD = (y) => 272 + 2 * Math.sin(y / 30);
const FRONT = (y) => 264 - 5 * Math.abs(Math.sin(y / 34)) - 2.5 * Math.sin(y / 11 + 1);
const CLEAR = [262, 282];
const PARK = { x0: 151, y0: 187, x1: 201, y1: 325 };
const FIELD = { x: 334, y: 346, r: 24 };
const HOME = { x: 176, y: 339 };
const GOAL = [334, 340];
const ROUTE = [[176, 334], [176, 328], [258, 328], [290, 320], [316, 300], [328, 318], [334, 334]];
const MARKERS = [[226, 100], [186, 300], [120, 470], [226, 548], [354, 520], [306, 92]];

const range = (a, b, step) => Array.from({ length: Math.floor((b - a) / step) + 1 }, (_, i) => a + i * step);

function random(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Catmull-Rom through the points, returned as a dense polyline. Two points stay a straight segment.
function curve(pts, step = 4) {
  if (pts.length === 2) return pts;
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [p0, p1, p2, p3] = [pts[i - 1] ?? pts[i], pts[i], pts[i + 1], pts[i + 2] ?? pts[i + 1]];
    const n = Math.max(2, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step));
    for (let k = 0; k < n; k++) {
      const t = k / n, t2 = t * t, t3 = t2 * t;
      out.push([0, 1].map((j) => 0.5 * (2 * p1[j] + (p2[j] - p0[j]) * t
        + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (3 * p1[j] - p0[j] - 3 * p2[j] + p3[j]) * t3)));
    }
  }
  out.push(pts.at(-1));
  return out;
}

const f = (n) => Math.round(n * 10) / 10;
const line = (pts) => 'M' + pts.map(([x, y]) => `${f(x)} ${f(y)}`).join('L');
const poly = (pts) => line(pts) + 'Z';
const disc = ([x, y], r) => `M${f(x - r)} ${f(y)}a${f(r)} ${f(r)} 0 1 0 ${f(2 * r)} 0a${f(r)} ${f(r)} 0 1 0 ${f(-2 * r)} 0Z`;

const STREETS = [
  { w: 9, pts: range(-20, 660, 40).map((y) => [COAST(y), y]) },
  ...[148, 204, 258].map((x) => ({ w: 6.5, pts: [[x, -20], [x, 660]] })),
  ...[40, 112, 184, 328, 400, 472, 544, 616].map((y) => ({ w: 5.5, pts: [[COAST(y), y], [258, y]] })),
  { w: 5.5, pts: [[COAST(256), 256], [148, 256]] },
  { w: 5.5, pts: [[204, 256], [258, 256]] },
  { w: 5, pts: [[258, 40], [296, 46], [330, 52]] },
  { w: 5, pts: [[340, -20], [330, 52], [344, 108], [340, 150]] },
  { w: 5, pts: [[258, 184], [290, 178], [316, 160], [340, 150]] },
  { w: 6, pts: [[258, 328], [290, 320], [316, 300], [344, 288], [372, 264], [404, 252]] },
  { w: 5, pts: [[372, 264], [384, 330], [366, 400], [382, 470], [372, 560], [388, 660]] },
  { w: 5, pts: [[366, 400], [340, 412], [316, 406]], end: true },
  { w: 5, pts: [[258, 472], [294, 468], [318, 450], [330, 432]], end: true },
  { w: 5, pts: [[258, 616], [300, 602], [334, 588], [374, 562]] },
].map((st) => ({ ...st, line: curve(st.pts) }));

const OBSTACLES = [...STREETS, { w: 3, line: curve(ROUTE) }];

function segDist(x, y, [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay;
  const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(x - ax - t * dx, y - ay - t * dy);
}

function clearOfStreets(x, y, pad) {
  for (const st of OBSTACLES) {
    for (let i = 1; i < st.line.length; i++) if (segDist(x, y, st.line[i - 1], st.line[i]) < st.w / 2 + pad) return false;
    if (st.end && Math.hypot(x - st.line.at(-1)[0], y - st.line.at(-1)[1]) < st.w * 1.3 + pad) return false;
  }
  return true;
}

function onLand(x, y, { park = false } = {}) {
  if (x < COAST(y) + 6 || x > 404 || y < -12 || y > 652) return false;
  if (x > CLEAR[0] && x < CLEAR[1]) return false;
  if (!park && x > PARK.x0 - 1 && x < PARK.x1 + 1 && y > PARK.y0 - 1 && y < PARK.y1 + 1) return false;
  return Math.hypot(x - FIELD.x, y - FIELD.y) > FIELD.r + 2;
}

// Walk each street at a jittered spacing, calling place(point, tangent, normal, street).
function alongStreets(rand, spacing, place) {
  for (const st of STREETS) {
    let next = rand() * spacing[0];
    let travelled = 0;
    for (let i = 1; i < st.line.length; i++) {
      const [a, b] = [st.line[i - 1], st.line[i]];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const u = [(b[0] - a[0]) / len, (b[1] - a[1]) / len];
      while (next < travelled + len) {
        const t = (next - travelled) / len;
        place([a[0] + u[0] * len * t, a[1] + u[1] * len * t], u, [-u[1], u[0]], st);
        next += spacing[0] + rand() * spacing[1];
      }
      travelled += len;
    }
  }
}

function layout() {
  const rand = random(20251104);
  const houses = [{ x: HOME.x, y: HOME.y, r: 12 }, { x: HOME.x, y: HOME.y + 18, r: 8 },
    ...MARKERS.map(([x, y]) => ({ x, y, r: 5 }))];
  const built = [];
  const fits = (x, y, r) => houses.every((o) => Math.hypot(o.x - x, o.y - y) > o.r + r);

  alongStreets(rand, [10, 3.5], (p, u, n, st) => {
    for (const side of [-1, 1]) {
      if (rand() > 0.9) continue;
      const w = 6.5 + rand() * 3.5, d = 8 + rand() * 5;
      const back = d / 2 + st.w / 2 + 1.6 + rand() * 2.2;
      const v = [n[0] * side, n[1] * side];
      const c = [p[0] + v[0] * back, p[1] + v[1] * back];
      const wing = rand() < 0.22 ? [w * (0.4 + rand() * 0.2), 3 + rand() * 3, rand() < 0.5 ? 1 : -1] : null;
      const local = wing
        ? [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [w / 2 - wing[0], d / 2], [w / 2 - wing[0], d / 2 + wing[1]],
          [-w / 2, d / 2 + wing[1]], [-w / 2, d / 2]].map(([a, b]) => [a * wing[2], b])
        : [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]];
      const pts = local.map(([a, b]) => [c[0] + u[0] * a + v[0] * b, c[1] + u[1] * a + v[1] * b]);
      const r = (w + d) / 4;
      if (!fits(c[0], c[1], r) || ![c, ...pts].every(([x, y]) => onLand(x, y) && clearOfStreets(x, y, 0.8))) continue;
      houses.push({ x: c[0], y: c[1], r });
      built.push(pts);
    }
  });

  const trees = [];
  const tryTree = (x, y, r, opts) => {
    if (!onLand(x, y, opts) || !clearOfStreets(x, y, r * 0.7)) return;
    if (!houses.every((o) => Math.hypot(o.x - x, o.y - y) > o.r + r * 0.8)) return;
    if (!trees.every((t) => Math.hypot(t.x - x, t.y - y) > (t.r + r) * 0.72)) return;
    trees.push({ x, y, r });
  };
  alongStreets(rand, [9, 6], (p, u, n, st) => {
    for (const side of [-1, 1]) {
      if (rand() > 0.45) continue;
      const r = 2.4 + rand() * 1.2, off = st.w / 2 + 0.8 + r;
      tryTree(p[0] + n[0] * side * off, p[1] + n[1] * side * off, r);
    }
  });
  for (let k = 0; k < 8; k++) {
    const cx = PARK.x0 + 6 + rand() * (PARK.x1 - PARK.x0 - 12), cy = PARK.y0 + 6 + rand() * (PARK.y1 - PARK.y0 - 12);
    for (let j = 0; j < 7; j++) {
      const a = rand() * 6.283, dist = rand() * 9;
      const x = cx + Math.cos(a) * dist, y = cy + Math.sin(a) * dist;
      if (x > PARK.x0 + 3 && x < PARK.x1 - 3 && y > PARK.y0 + 3 && y < PARK.y1 - 3) tryTree(x, y, 2.6 + rand() * 1.8, { park: true });
    }
  }
  for (let k = 0; k < 1400; k++) {
    const hill = k % 3 === 0;
    tryTree(hill ? 282 + rand() * 122 : 100 + rand() * 300, -10 + rand() * 660, 2 + rand() * 1.8);
  }
  return { built, trees };
}

// Seigaiha: rows of concentric arcs, each row half a scale lower and offset by one radius. The tile repeats every two rows.
function seigaiha(id, name, r, cls) {
  const scale = (cx, cy) => [r, r * 0.7, r * 0.4].map((k, i) =>
    s('circle', { cx, cy, r: k, class: i ? `${cls} ${cls}-ring` : cls }));
  const rows = [0, 1, 2, 3, 4].flatMap((k) => (k % 2 ? [[r, k * r / 2]] : [[0, k * r / 2], [2 * r, k * r / 2]]));
  return s('pattern', { id: `${name}-${id}`, width: 2 * r, height: r, patternUnits: 'userSpaceOnUse' },
    rows.map(([x, y]) => scale(x, y)));
}

function patterns(id) {
  const pat = (name, size, ...kids) => s('pattern', { id: `${name}-${id}`, width: size, height: size, patternUnits: 'userSpaceOnUse' }, kids);
  const bg = (size, cls = 'nb-pat-bg') => s('rect', { width: size, height: size, class: cls });
  const dot = (cx, cy, r, cls = 'nb-dot') => s('circle', { cx, cy, r, class: cls });
  return s('defs', null,
    pat('roof', 2.4, bg(2.4), dot(0.6, 0.6, 0.38), dot(1.8, 1.8, 0.38)),
    pat('tree', 1.9, bg(1.9, 'nb-pat-tree'), dot(0.5, 0.5, 0.42), dot(1.45, 1.45, 0.42)),
    pat('sand', 7, dot(1, 1.5, 0.42, 'nb-sand'), dot(4.6, 5.2, 0.42, 'nb-sand')),
    pat('field', 6, dot(1.2, 1.2, 0.45, 'nb-sand'), dot(4.2, 4.4, 0.35, 'nb-sand')),
    seigaiha(id, 'sea', 7, 'nb-scale'),
    seigaiha(id, 'flood', 7, 'nb-fscale'));
}

// The tsunami front: scalloped crests bulging inland, each ending in a small curl back toward the sea.
function crestPath(dx) {
  let d = '';
  for (let y = -24; y < 664; y += 22) {
    const x0 = FRONT(y) + dx, x1 = FRONT(y + 22) + dx;
    d += `M${f(x0)} ${f(y)}C${f(x0 + 9)} ${f(y + 2)} ${f(x1 + 9)} ${f(y + 14)} ${f(x1)} ${f(y + 22)}`
      + `M${f(x0 + 6.5)} ${f(y + 5)}c-1.6 3.2-5.6 3.6-7 1.2c-1-1.8 0.4-3.6 2.2-3.2`;
  }
  return d;
}

const seaPath = () => `M-30 -30${line(range(-30, 670, 10).map((y) => [SHORE(y), y])).replace('M', 'L')}L-30 670Z`;
const beachPath = () => `M-30 -30${line(range(-30, 670, 20).map((y) => [COAST(y), y])).replace('M', 'L')}L-30 670Z`;

let instances = 0;

export function neighborhood({ animate }) {
  const id = `nb${++instances}`;
  const url = (name) => `url(#${name}-${id})`;
  const { built, trees } = layout();
  const roads = (cls, extra) => STREETS.map((st) => s('path', { d: line(st.line), class: cls, 'stroke-width': st.w + extra }));
  const ends = (cls, extra) => STREETS.filter((st) => st.end).map((st) => s('circle', { cx: st.line.at(-1)[0], cy: st.line.at(-1)[1], r: st.w * 1.3 + extra / 2, class: cls }));
  const houseLayer = (k) => s('g', { class: `nb-houses nb-houses-${k}` },
    s('path', { class: 'nb-side', d: built.filter((_, i) => i % 3 === k).map((p) => poly(p.map(([x, y]) => [x + 1, y + 1.2]))).join('') }),
    s('path', { class: 'nb-roof', fill: url('roof'), d: built.filter((_, i) => i % 3 === k).map(poly).join('') }));
  const ripple = ([x, y], r) => s('circle', { cx: x, cy: y, r, class: 'nb-ripple' });
  const front = range(-20, 660, 8).map((y) => [FRONT(y), y]);
  const shifted = (dx) => line(front.map(([x, y]) => [x + dx, y]));
  const flood = `M-330 -20${shifted(0).replace('M', 'L')}L-330 660Z`;
  const label = (text, x, y, rot, cls = 'nb-label') =>
    s('text', { x, y, class: cls, 'text-anchor': 'middle', transform: rot ? `rotate(-90 ${x} ${y})` : null }, text);
  const home = [[HOME.x - 5.5, HOME.y - 5], [HOME.x + 5.5, HOME.y - 5], [HOME.x + 5.5, HOME.y + 5], [HOME.x - 5.5, HOME.y + 5]];

  return s('svg', {
    class: animate ? 'nb nb-animate' : 'nb', viewBox: '0 0 400 640', preserveAspectRatio: 'xMidYMid slice', role: 'img',
    'aria-label': 'Map of a coastal neighbourhood. The ground shakes, a tsunami floods the low streets up to the hazard line, '
      + 'then the water goes back out. A dashed yellow route leads from a highlighted home uphill to high ground.',
  },
  patterns(id),
  s('g', { class: 'nb-quake' },
    s('rect', { x: -30, y: -30, width: 460, height: 700, class: 'nb-paper' }),
    s('path', { d: beachPath(), fill: url('sand') }),
    s('path', { d: seaPath(), class: 'nb-sea', fill: url('sea') }),
    s('path', { d: line(range(-30, 670, 10).map((y) => [SHORE(y) - 4, y])), class: 'nb-surf' }),
    s('path', { d: line(range(-30, 670, 10).map((y) => [SHORE(y), y])), class: 'nb-shore' }),
    [288, 306, 326, 350, 378].map((c, i) => s('path', {
      class: i % 2 ? 'nb-contour nb-contour-major' : 'nb-contour',
      d: line(curve(range(-20, 660, 40).map((y) => [c + 3 * Math.sin(y / 41 + c) + 2 * Math.sin(y / 19 + c * 0.3), y]), 6)),
    })),
    s('rect', { x: PARK.x0, y: PARK.y0, width: PARK.x1 - PARK.x0, height: PARK.y1 - PARK.y0, rx: 3, class: 'nb-park', fill: url('field') }),
    s('path', { d: line(curve([[PARK.x0, 228], [166, 236], [184, 262], [190, 290], [PARK.x1, 312]])), class: 'nb-trail' }),
    s('ellipse', { cx: FIELD.x, cy: FIELD.y, rx: FIELD.r, ry: FIELD.r * 0.86, class: 'nb-park', fill: url('field') }),
    roads('nb-casing', 1.6), ends('nb-casing-end', 1.6),
    roads('nb-road', 0), ends('nb-road-end', 0),
    [0, 1, 2].map(houseLayer),
    s('path', { class: 'nb-tree', fill: url('tree'), d: trees.map((t) => disc([t.x, t.y], t.r)).join('') }),
    MARKERS.map((m) => [ripple(m, 2.6), s('circle', { cx: m[0], cy: m[1], r: 2.6, class: 'nb-marker' })]),
    label('PACIFIC OCEAN', 30, 300, true),
    s('g', { class: 'nb-flood' },
      s('path', { d: flood, class: 'nb-flood-water', fill: url('flood') }),
      s('path', { d: shifted(-9), class: 'nb-edge nb-edge-1' }),
      s('path', { d: shifted(-4.5), class: 'nb-edge nb-edge-3' }),
      s('path', { d: crestPath(0), class: 'nb-crest' })),
    s('path', { d: line(range(-20, 660, 8).map((y) => [HAZARD(y), y])), class: 'nb-hazard' }),
    label('TSUNAMI HAZARD LINE', 279, 132, true, 'nb-label nb-label-small'),
    label('HIGH GROUND', FIELD.x, FIELD.y + FIELD.r + 12),
    s('path', { d: line(curve(ROUTE, 3)), class: 'nb-route-case' }),
    s('path', { d: line(curve(ROUTE, 3)), class: 'nb-route' }),
    ripple([HOME.x, HOME.y], 10),
    s('circle', { cx: HOME.x, cy: HOME.y, r: 10, class: 'nb-home-ring' }),
    s('path', { d: poly(home.map(([x, y]) => [x + 1, y + 1.2])), class: 'nb-side' }),
    s('path', { d: poly(home), class: 'nb-home' }),
    label('HOME', HOME.x, HOME.y + 21, false, 'nb-label nb-label-strong'),
    ripple(GOAL, 9),
    s('g', { transform: `translate(${GOAL[0] - 8} ${GOAL[1] - 8}) scale(${16 / 40})` }, evacMarks())));
}

