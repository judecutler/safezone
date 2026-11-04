import { h, s } from '../dom.js';
import { evacMarks } from './signs.js';

// A top-down coastal neighbourhood, drawn procedurally from a fixed seed so it is identical on every load.
// Ocean at left, beach, coast road, a low street grid inside the hazard area, and contoured high ground at right.
// Drawn like a site plan: hip and gable roof lines over warm grey footprints, the face turned from the light a shade darker.
// The loop (landing.css): calm, shaking with falling debris (debris() below), a tsunami floods the low blocks up to the
// hazard line, it recedes.

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
const BLOCK = { c: [231, 436], u: [0, 1], v: [-1, 0], w: 44, d: 26, kind: 'block' };
const CONTOURS = [288, 306, 326, 350, 378];
const LIGHT = [-0.6, -0.8];
export const LOOP_MS = 15000;
const HOUSE_LAYERS = 4;

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
// The same in relative coordinates, which keeps thousands of small shapes short. Differences of rounded points, so no drift.
function rel(pts, close = true) {
  const r = pts.map(([x, y]) => [f(x), f(y)]);
  return `M${r[0][0]} ${r[0][1]}l` + r.slice(1).map((p, i) => `${f(p[0] - r[i][0])} ${f(p[1] - r[i][1])}`).join(' ') + (close ? 'z' : '');
}

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

// A footprint and its roof: the outline, the faces turned away from the light, and the ridge and hip lines.
function roof({ c, u, v, w, d, kind }) {
  if (d > w) [u, v, w, d] = [v, [-u[0], -u[1]], d, w];
  const at = (a, b) => [c[0] + u[0] * a + v[0] * b, c[1] + u[1] * a + v[1] * b];
  const dark = (a, b) => (u[0] * a + v[0] * b) * LIGHT[0] + (u[1] * a + v[1] * b) * LIGHT[1] < -0.05;
  const [A, B, C, D] = [at(-w / 2, -d / 2), at(w / 2, -d / 2), at(w / 2, d / 2), at(-w / 2, d / 2)];
  const out = { outline: [A, B, C, D], shade: [], lines: [] };
  const face = (pts, a, b) => { if (dark(a, b)) out.shade.push(pts); };
  if (kind === 'hip') {
    const [R1, R2] = [at(-w / 2 + d / 2, 0), at(w / 2 - d / 2, 0)];
    face([A, B, R2, R1], 0, -1); face([B, C, R2], 1, 0); face([C, D, R1, R2], 0, 1); face([D, A, R1], -1, 0);
    out.lines.push([A, R1, D], [B, R2, C], [R1, R2]);
  } else if (kind === 'gable') {
    const [M1, M2] = [at(-w / 2, 0), at(w / 2, 0)];
    face([A, B, M2, M1], 0, -1); face([M1, M2, C, D], 0, 1);
    out.lines.push([M1, M2]);
  } else {
    const k = kind === 'block' ? 1.8 : 1.1;
    out.lines.push([at(-w / 2 + k, -d / 2 + k), at(w / 2 - k, -d / 2 + k), at(w / 2 - k, d / 2 - k), at(-w / 2 + k, d / 2 - k), at(-w / 2 + k, -d / 2 + k)]);
    if (kind === 'block') {
      for (const [a, b, bw, bd] of [[-12, -3, 7, 6], [4, 2, 5, 4], [12, -5, 4, 4]]) {
        const box = [at(a, b), at(a + bw, b), at(a + bw, b + bd), at(a, b + bd)];
        out.shade.push(box);
        out.lines.push([...box, box[0]]);
      }
    }
  }
  return out;
}

function layout() {
  const rand = random(20251104);
  const houses = [{ x: HOME.x, y: HOME.y, r: 12 }, { x: HOME.x, y: HOME.y + 18, r: 8 },
    { x: BLOCK.c[0], y: BLOCK.c[1], r: 26 }, ...MARKERS.map(([x, y]) => ({ x, y, r: 5 }))];
  const built = [{ ...BLOCK, layer: 0 }];
  const fits = (x, y, r) => houses.every((o) => Math.hypot(o.x - x, o.y - y) > o.r + r);
  const nearBlock = (x, y) => Math.abs(x - BLOCK.c[0]) < BLOCK.d / 2 + 3 && Math.abs(y - BLOCK.c[1]) < BLOCK.w / 2 + 3;

  alongStreets(rand, [11, 4], (p, u, n, st) => {
    for (const side of [-1, 1]) {
      if (rand() > 0.88) continue;
      const big = rand() < 0.2;
      const w = big ? 13 + rand() * 3 : 7 + rand() * 2.5, d = big ? 8.5 + rand() * 2 : 11 + rand() * 3.5;
      const back = d / 2 + st.w / 2 + 1.8 + rand() * 2.4;
      const v = [n[0] * side, n[1] * side];
      const c = [p[0] + v[0] * back, p[1] + v[1] * back];
      const r = (w + d) / 4;
      const pick = rand();
      const house = { c, u, v, w, d, kind: big && pick < 0.35 ? 'flat' : pick < 0.62 ? 'hip' : 'gable', layer: built.length % HOUSE_LAYERS };
      const corners = roof(house).outline;
      if (!fits(c[0], c[1], r) || ![c, ...corners].every(([x, y]) => onLand(x, y) && !nearBlock(x, y) && clearOfStreets(x, y, 0.8))) continue;
      houses.push({ x: c[0], y: c[1], r });
      built.push(house);
    }
  });

  const trees = [];
  const tryTree = (x, y, r, opts) => {
    if (!onLand(x, y, opts) || nearBlock(x, y) || !clearOfStreets(x, y, r * 0.6)) return;
    if (!houses.every((o) => Math.hypot(o.x - x, o.y - y) > o.r + r * 0.7)) return;
    if (!trees.every((t) => Math.hypot(t.x - x, t.y - y) > (t.r + r) * 0.8)) return;
    trees.push({ x, y, r, seed: rand(), tone: rand() < 0.42 ? 1 : 0 });
  };
  alongStreets(rand, [12, 8], (p, u, n, st) => {
    for (const side of [-1, 1]) {
      if (rand() > 0.4) continue;
      const r = 3.2 + rand() * 1.6, off = st.w / 2 + 0.6 + r;
      tryTree(p[0] + n[0] * side * off, p[1] + n[1] * side * off, r);
    }
  });
  for (let k = 0; k < 7; k++) {
    const cx = PARK.x0 + 8 + rand() * (PARK.x1 - PARK.x0 - 16), cy = PARK.y0 + 8 + rand() * (PARK.y1 - PARK.y0 - 16);
    for (let j = 0; j < 5; j++) {
      const a = rand() * 6.283, dist = rand() * 9;
      const x = cx + Math.cos(a) * dist, y = cy + Math.sin(a) * dist;
      if (x > PARK.x0 + 4 && x < PARK.x1 - 4 && y > PARK.y0 + 4 && y < PARK.y1 - 4) tryTree(x, y, 4 + rand() * 2.6, { park: true });
    }
  }
  for (let k = 0; k < 520; k++) {
    const hill = k % 2 === 0;
    tryTree(hill ? 284 + rand() * 120 : 100 + rand() * 300, -10 + rand() * 660, hill ? 3.4 + rand() * 3 : 3 + rand() * 1.8);
  }
  return { built, trees };
}

// A soft, slightly lumpy crown: smoothed through the midpoints of a wobbly ring, in relative coordinates to keep it short.
function blob({ x, y, r, seed }) {
  const n = 6;
  const pts = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * 6.283 + seed * 3, k = r * (0.84 + 0.32 * ((Math.sin(seed * 97 + i * 2.3) + 1) / 2));
    return [x + Math.cos(a) * k, y + Math.sin(a) * k];
  });
  const mid = (i) => { const [p, q] = [pts[i % n], pts[(i + 1) % n]]; return [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2]; };
  let [cx, cy] = mid(0);
  let d = `M${f(cx)} ${f(cy)}`;
  for (let i = 1; i <= n; i++) {
    const [px, py] = pts[i % n], [mx, my] = mid(i);
    d += `q${f(px - cx)} ${f(py - cy)} ${f(mx - cx)} ${f(my - cy)}`;
    [cx, cy] = [mx, my];
  }
  return d + 'Z';
}

// Seigaiha: rows of concentric arcs, each row half a scale lower and offset by one radius. The tile repeats every two rows.
function seigaiha(id, name, r, cls) {
  const scale = (cx, cy) => [r, r * 0.7, r * 0.4].map((k, i) =>
    s('circle', { cx, cy, r: k, class: i ? `${cls} ${cls}-ring` : cls }));
  const rows = [0, 1, 2, 3, 4].flatMap((k) => (k % 2 ? [[r, k * r / 2]] : [[0, k * r / 2], [2 * r, k * r / 2]]));
  return s('pattern', { id: `${name}-${id}`, width: 2 * r, height: r, patternUnits: 'userSpaceOnUse' },
    rows.map(([x, y]) => scale(x, y)));
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
const contour = (c) => curve(range(-20, 660, 40).map((y) => [c + 3 * Math.sin(y / 41 + c) + 2 * Math.sin(y / 19 + c * 0.3), y]), 6);

// Power lines on poles beside two streets: the wires sit in their own group so they can swing while the poles stay put.
function powerLines(side) {
  const runs = [range(-20, 660, 34).map((y) => [COAST(y) + side, y]), range(-20, 660, 34).map((y) => [204 - 5.2, y])];
  const poles = runs.flat().map(([x, y]) => `M${f(x - 1.6)} ${f(y)}h3.2`).join('');
  const wires = runs.map((pts) => [-0.7, 0.7].map((o) => line(pts.map(([x, y]) => [x + o, y]))).join('')).join('');
  return [s('path', { d: poles, class: 'nb-pole' }), s('g', { class: 'nb-wires' }, s('path', { d: wires, class: 'nb-wire' }))];
}

let instances = 0;

export function neighborhood({ animate }) {
  const id = `nb${++instances}`;
  const url = (name) => `url(#${name}-${id})`;
  const { built, trees } = layout();
  const roofs = built.map((b) => ({ ...roof(b), layer: b.layer }));
  const roads = (cls, extra) => STREETS.map((st) => s('path', { d: line(st.line), class: cls, 'stroke-width': st.w + extra }));
  const ends = (cls, extra) => STREETS.filter((st) => st.end).map((st) => s('circle', { cx: st.line.at(-1)[0], cy: st.line.at(-1)[1], r: st.w * 1.3 + extra / 2, class: cls }));
  const houseLayer = (k) => {
    const mine = roofs.filter((r) => r.layer === k);
    return s('g', { class: `nb-houses nb-houses-${k}` },
      s('use', { href: `#${id}-hb${k}`, class: 'nb-cast', transform: 'translate(1.5 1.9)' }),
      s('path', { id: `${id}-hb${k}`, class: 'nb-house', d: mine.map((r) => rel(r.outline)).join('') }),
      s('path', { class: 'nb-house-shade', d: mine.flatMap((r) => r.shade.map((x) => rel(x))).join('') }),
      s('use', { href: `#${id}-hb${k}`, class: 'nb-house-outline' }),
      s('path', { class: 'nb-house-line', d: mine.flatMap((r) => r.lines.map((x) => rel(x, false))).join('') }));
  };
  const treeLayer = (k) => {
    const mine = trees.filter((_, i) => i % 2 === k);
    const tone = (t) => s('path', { id: `${id}-t${k}${t}`, class: `nb-tree nb-tree-${t}`, d: mine.filter((x) => x.tone === t).map(blob).join('') });
    const shadow = (t) => s('use', { href: `#${id}-t${k}${t}`, class: 'nb-tree-shadow', transform: 'translate(1.2 1.6)' });
    return s('g', { class: `nb-trees nb-trees-${k}` }, shadow(0), shadow(1), tone(0), tone(1));
  };
  const ripple = ([x, y], r) => s('circle', { cx: x, cy: y, r, class: 'nb-ripple' });
  const front = range(-20, 660, 8).map((y) => [FRONT(y), y]);
  const shifted = (dx) => line(front.map(([x, y]) => [x + dx, y]));
  const flood = `M-330 -20${shifted(0).replace('M', 'L')}L-330 660Z`;
  const label = (text, x, y, rot, cls = 'nb-label') =>
    s('text', { x, y, class: cls, 'text-anchor': 'middle', transform: rot ? `rotate(-90 ${x} ${y})` : null }, text);
  const home = [[HOME.x - 5.5, HOME.y - 5], [HOME.x + 5.5, HOME.y - 5], [HOME.x + 5.5, HOME.y + 5], [HOME.x - 5.5, HOME.y + 5]];
  const homeRoof = roof({ c: [HOME.x, HOME.y], u: [1, 0], v: [0, 1], w: 11, d: 10, kind: 'gable' });

  return s('svg', {
    class: animate ? 'nb nb-animate' : 'nb', viewBox: '0 0 400 640', preserveAspectRatio: 'xMidYMid slice', role: 'img',
    'aria-label': 'Map of a coastal neighbourhood. The ground shakes and debris falls, a tsunami floods the low streets up to '
      + 'the hazard line, then the water goes back out. A dashed yellow route leads from a highlighted home uphill to high ground.',
  },
  s('defs', null, seigaiha(id, 'sea', 7, 'nb-scale'), seigaiha(id, 'flood', 7, 'nb-fscale')),
  s('g', { class: 'nb-quake' },
    s('rect', { x: -30, y: -30, width: 460, height: 700, class: 'nb-paper' }),
    CONTOURS.map((c) => s('path', { class: 'nb-hill', d: `${line(contour(c))}L440 660L440 -20Z` })),
    s('path', { d: beachPath(), class: 'nb-sand' }),
    s('path', { d: line(range(-30, 670, 10).map((y) => [SHORE(y) + 9 + 2 * Math.sin(y / 23), y])), class: 'nb-wrack' }),
    s('path', { d: seaPath(), class: 'nb-sea-base' }),
    s('path', { d: seaPath(), class: 'nb-sea', fill: url('sea') }),
    s('path', { d: line(range(-30, 670, 10).map((y) => [SHORE(y) - 4, y])), class: 'nb-surf' }),
    s('path', { d: line(range(-30, 670, 10).map((y) => [SHORE(y), y])), class: 'nb-shore' }),
    CONTOURS.map((c, i) => s('path', { class: i % 2 ? 'nb-contour nb-contour-major' : 'nb-contour', d: line(contour(c)) })),
    s('rect', { x: PARK.x0, y: PARK.y0, width: PARK.x1 - PARK.x0, height: PARK.y1 - PARK.y0, rx: 3, class: 'nb-park' }),
    s('path', { d: line(curve([[PARK.x0, 228], [166, 236], [184, 262], [190, 290], [PARK.x1, 312]])), class: 'nb-trail' }),
    s('ellipse', { cx: FIELD.x, cy: FIELD.y, rx: FIELD.r, ry: FIELD.r * 0.86, class: 'nb-park nb-field' }),
    roads('nb-casing', 1.1), ends('nb-casing-end', 1.1),
    roads('nb-road', 0), ends('nb-road-end', 0),
    range(0, HOUSE_LAYERS - 1, 1).map(houseLayer),
    [0, 1].map(treeLayer),
    powerLines(6.2),
    MARKERS.map((m) => [ripple(m, 2.6), s('circle', { cx: m[0], cy: m[1], r: 2.6, class: 'nb-marker' })]),
    label('PACIFIC OCEAN', 30, 300, true, 'nb-label nb-label-sea'),
    s('g', { class: 'nb-flood' },
      s('path', { d: flood, class: 'nb-flood-base' }),
      s('path', { d: flood, class: 'nb-flood-water', fill: url('flood') }),
      s('path', { d: shifted(-9), class: 'nb-edge nb-edge-1' }),
      s('path', { d: shifted(-4.5), class: 'nb-edge nb-edge-3' }),
      s('path', { d: crestPath(-8), class: 'nb-crest' })),
    s('path', { d: line(range(-20, 660, 8).map((y) => [HAZARD(y), y])), class: 'nb-hazard' }),
    label('TSUNAMI HAZARD LINE', 279, 132, true, 'nb-label nb-label-small'),
    label('HIGH GROUND', FIELD.x, FIELD.y + FIELD.r + 12),
    s('path', { d: line(curve(ROUTE, 3)), class: 'nb-route-case' }),
    s('path', { d: line(curve(ROUTE, 3)), class: 'nb-route' }),
    ripple([HOME.x, HOME.y], 10),
    s('circle', { cx: HOME.x, cy: HOME.y, r: 10, class: 'nb-home-ring' }),
    s('path', { d: poly(home.map(([x, y]) => [x + 1.5, y + 1.9])), class: 'nb-cast' }),
    s('path', { d: poly(home), class: 'nb-home' }),
    s('path', { d: homeRoof.shade.map(poly).join(''), class: 'nb-home-shade' }),
    s('path', { d: homeRoof.lines.map(line).join(''), class: 'nb-home-line' }),
    label('HOME', HOME.x, HOME.y + 21, false, 'nb-label nb-label-strong'),
    ripple(GOAL, 9),
    s('g', { transform: `translate(${GOAL[0] - 8} ${GOAL[1] - 8}) scale(${16 / 40})` }, evacMarks())),
  s('rect', { x: -30, y: -30, width: 460, height: 700, class: 'nb-flash' }));
}

// Falling debris during the shaking phase, drawn on a canvas over the map. Every particle is a pure function of the loop
// time read from the map's own CSS animation, so the two never drift apart and a paused or seeked animation shows a
// matching frame. One requestAnimationFrame loop; it idles while the tab is hidden and ends once the map leaves the page.
const JOLTS = [0.30, 0.38, 0.46].map((p) => p * LOOP_MS);
const SHAKE_END = 0.53 * LOOP_MS;
const DUST = ['#BDB6A8', '#D3CCBE', '#C9A45A', '#B48A3C', '#A9A193'];

function particles() {
  const rand = random(4041);
  const list = [];
  const add = (kind, n, spread) => {
    for (let i = 0; i < n; i++) {
      const burst = rand() < 0.72;
      const t0 = burst ? JOLTS[Math.floor(rand() * 3)] + rand() * spread : JOLTS[0] + rand() * (SHAKE_END - JOLTS[0]);
      list.push({
        kind, t0, x: rand(), y: -0.04 + rand() * (kind === 'dust' ? 0.16 : 0.06),
        life: kind === 'chunk' ? 1300 + rand() * 500 : 1500 + rand() * 1100,
        vx: (rand() - 0.5) * (kind === 'dust' ? 0.05 : 0.08), vy: rand() * 0.05,
        g: kind === 'chunk' ? 0.62 + rand() * 0.2 : kind === 'bit' ? 0.42 + rand() * 0.18 : 0.13 + rand() * 0.12,
        size: kind === 'chunk' ? 4.5 + rand() * 3.5 : kind === 'bit' ? 1.6 + rand() * 2 : 0.6 + rand() * 1.1,
        spin: (rand() - 0.5) * 9, angle: rand() * 6.283, sway: rand() * 6.283,
        color: kind === 'chunk' ? '#DAD5CA' : DUST[Math.floor(rand() * DUST.length)],
        shape: Array.from({ length: 5 }, (_, k) => [k / 5 * 6.283, 0.7 + rand() * 0.45]),
      });
    }
  };
  add('dust', 150, 900); add('bit', 46, 700); add('chunk', 9, 300);
  return list;
}

export function debris(svg) {
  const canvas = h('canvas', { class: 'nb-debris', 'aria-hidden': 'true' });
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  const list = particles();
  let raf = 0, seen = false, size = '', drawn = false;

  const clock = () => {
    const anim = svg.querySelector('.nb-quake')?.getAnimations()[0];
    return anim && anim.currentTime != null ? Number(anim.currentTime) % LOOP_MS : null;
  };
  const draw = (t) => {
    const w = canvas.clientWidth, ht = canvas.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
    if (`${w}x${ht}x${dpr}` !== size) {
      size = `${w}x${ht}x${dpr}`;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(ht * dpr);
    }
    const active = t != null && t >= JOLTS[0] && t <= SHAKE_END + 3000;
    if (!active && !drawn) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, ht);
    drawn = active;
    if (!active) return;
    const unit = Math.max(1, Math.min(w, ht * 0.75) / 390);
    for (const p of list) {
      const age = t - p.t0;
      if (age < 0 || age > p.life) continue;
      const sec = age / 1000;
      const y = (p.y + p.vy * sec + 0.5 * p.g * sec * sec) * ht;
      const x = (p.x + p.vx * sec) * w + Math.sin(p.sway + sec * 3) * (p.kind === 'dust' ? 6 : 2) * unit;
      const a = Math.min(1, age / 120) * (1 - (age / p.life) ** 2);
      if (a <= 0 || y > ht + 10) continue;
      ctx.globalAlpha = p.kind === 'dust' ? a * 0.85 : a;
      const r = p.size * unit;
      if (p.kind === 'dust') {
        ctx.fillStyle = p.color;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill();
        continue;
      }
      const ang = p.angle + p.spin * sec;
      ctx.beginPath();
      p.shape.forEach(([th, k], i) => {
        const px = x + Math.cos(th + ang) * r * k, py = y + Math.sin(th + ang) * r * k;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      });
      ctx.closePath();
      ctx.fillStyle = p.color; ctx.fill();
      if (p.kind === 'chunk') { ctx.lineWidth = 0.9; ctx.strokeStyle = '#34302A'; ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
  };
  const frame = () => {
    raf = 0;
    if (!canvas.isConnected) {
      if (seen) { document.removeEventListener('visibilitychange', wake); return; }
    } else {
      seen = true;
      draw(clock());
    }
    if (!document.hidden) raf = requestAnimationFrame(frame);
  };
  const wake = () => { if (!document.hidden && !raf) raf = requestAnimationFrame(frame); };
  document.addEventListener('visibilitychange', wake);
  raf = requestAnimationFrame(frame);
  return canvas;
}
