import { h, s } from '../dom.js';
import { evacMarks } from './signs.js';

// A coastal neighbourhood seen from above at a gentle tilt, drawn procedurally from a fixed seed so it is identical on
// every load. Ocean at left, beach, coast road, a low street grid inside the hazard area, contoured high ground at right.
// The layout is planned on flat ground coordinates; P() projects every point to the screen, and buildings rise from it as
// prisms. The loop (landing.css, timed by TIMELINE below): a small tremor, a larger one, the strong earthquake with falling
// debris (debris() below), an eerie calm while the sea draws back off the beach, the tsunami floods the low blocks up to the
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
const BLOCK = { c: [231, 436], u: [0, 1], v: [-1, 0], w: 44, d: 26, kind: 'flat', h: 22, rise: 0 };
const CONTOURS = [288, 306, 326, 350, 378, 410, 446];
const LIGHT = [-0.6, -0.8];
// The ground the tilted view needs to fill the 400 x 640 frame, with a margin for buildings rising at the bottom edge.
const Y0 = -150, Y1 = 800, XE = 480;
const BANDS = 6;
// The loop, in ms. landing.css uses the same times as percentages of LOOP_MS; the pill label and level follow TIMELINE.
export const LOOP_MS = 21000;
const TIMELINE = [
  [0, 'Calm', 0], [3000, 'Small tremor', 1], [3600, 'Calm', 0], [5100, 'Tremor', 1], [6100, 'Calm', 0],
  [7100, 'Strong earthquake', 2], [10700, 'Water pulling back: go to high ground', 2], [13200, 'Tsunami', 2],
  [16500, 'Water going back', 1], [18600, 'Calm', 0],
];
// Each shock's jolts and end; debris falls in bursts at the jolts and a trickle in between.
const SHOCKS = [
  { jolts: [3000], end: 3600, dust: 22, bit: 0, chunk: 0, fade: 0.55 },
  { jolts: [5100], end: 6100, dust: 70, bit: 12, chunk: 0, fade: 0.8 },
  { jolts: [7100, 8300, 9500], end: 10700, dust: 380, bit: 110, chunk: 14, fade: 1 },
];
const EBB = 30;

// The projection: a gentle axonometric tilt. Ground x runs slightly downhill to the right, ground y is foreshortened and
// slanted, and height goes straight up the screen. Chosen so the home stays where the flat plan had it.
const [PA, PB, PC] = [0.16, 0.13, 0.78];
const [TX, TY] = [HOME.x - (HOME.x - PA * HOME.y), HOME.y - (PB * HOME.x + PC * HOME.y)];
const P = (x, y, z = 0) => [x - PA * y + TX, PB * x + PC * y + TY - z];
const UP_COAST = (Math.atan2(-PC, PA) * 180) / Math.PI;

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
// Ground polyline or polygon, projected.
const line = (pts) => 'M' + pts.map(([x, y]) => P(x, y).map(f).join(' ')).join('L');
const poly = (pts) => line(pts) + 'Z';
// Screen-space polygon in relative coordinates, which keeps hundreds of small shapes short. Differences of rounded points,
// so no drift.
function rel(pts) {
  const r = pts.map(([x, y]) => [f(x), f(y)]);
  return `M${r[0][0]} ${r[0][1]}l` + r.slice(1).map((p, i) => `${f(p[0] - r[i][0])} ${f(p[1] - r[i][1])}`).join(' ') + 'z';
}
const at = ([x, y], z = 0) => P(x, y, z);
// Only what lands inside the 400 x 640 frame (with a margin for jitter and tall walls) is drawn.
const inFrame = (x, y) => { const [sx, sy] = P(x, y); return sx > -16 && sx < 416 && sy > -12 && sy < 668; };

const STREETS = [
  { w: 10, main: true, pts: range(Y0, Y1, 40).map((y) => [COAST(y), y]) },
  ...[148, 204, 258].map((x) => ({ w: 6.5, pts: [[x, Y0], [x, Y1]] })),
  ...[-104, -32, 40, 112, 184, 328, 400, 472, 544, 616, 688, 760].map((y) => ({ w: 4.6, pts: [[COAST(y), y], [258, y]] })),
  { w: 4.6, pts: [[COAST(256), 256], [148, 256]] },
  { w: 4.6, pts: [[204, 256], [258, 256]] },
  { w: 4.6, pts: [[258, 40], [296, 46], [330, 52]] },
  { w: 4.6, pts: [[258, -104], [300, -96], [336, -70], [346, Y0]] },
  { w: 4.6, pts: [[346, Y0], [336, -70], [330, 52], [344, 108], [340, 150]] },
  { w: 4.6, pts: [[258, 184], [290, 178], [316, 160], [340, 150]] },
  { w: 7.5, main: true, pts: [[258, 328], [290, 320], [316, 300], [344, 288], [372, 264], [404, 252], [440, 250], [XE + 20, 236]] },
  { w: 4.6, pts: [[372, 264], [384, 330], [366, 400], [382, 470], [372, 560], [388, 660], [380, Y1]] },
  { w: 4.6, pts: [[366, 400], [340, 412], [316, 406]], end: true },
  { w: 4.6, pts: [[258, 472], [294, 468], [318, 450], [330, 432]], end: true },
  { w: 4.6, pts: [[258, 616], [300, 602], [334, 588], [374, 562]] },
  { w: 4.6, pts: [[258, 688], [310, 700], [350, 690], [386, 680]] },
  { w: 4.6, pts: [[404, 252], [420, 180], [446, 120], [440, 40], [460, -60], [452, Y0]] },
  { w: 4.6, pts: [[382, 470], [420, 480], [452, 520], [XE + 20, 540]] },
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
  if (x < COAST(y) + 6 || x > XE || y < Y0 + 8 || y > Y1 - 8) return false;
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

// A building as a prism on the screen: the walls that face the viewer (two tones, by which way they face) and the roof
// faces (two tones, by the light), each a screen polygon. Gable and hip roofs rise `rise` above the eaves.
function solid({ c, u, v, w, d, kind, h, rise, z0 = 0 }) {
  if (d > w) [u, v, w, d] = [v, [-u[0], -u[1]], d, w];
  const g = (a, b) => [c[0] + u[0] * a + v[0] * b, c[1] + u[1] * a + v[1] * b];
  const foot = [g(-w / 2, -d / 2), g(w / 2, -d / 2), g(w / 2, d / 2), g(-w / 2, d / 2)];
  const mid = at(c, z0);
  const out = { walls: [], roofs: [], depth: mid[1] };
  const top = z0 + h;
  foot.forEach((p, i) => {
    const q = foot[(i + 1) % 4];
    const [a, b] = [at(p, z0), at(q, z0)];
    const n = [b[1] - a[1], a[0] - b[0]];
    const outward = ((a[0] + b[0]) / 2 - mid[0]) * n[0] + ((a[1] + b[1]) / 2 - mid[1]) * n[1] > 0 ? n : [-n[0], -n[1]];
    if (outward[1] <= 0) return;
    const dark = outward[0] > 0;
    out.walls.push({ pts: [a, b, at(q, top), at(p, top)], dark });
    if (kind === 'gable' && i % 2 === 1) {
      const m = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      out.walls.push({ pts: [at(p, top), at(q, top), at(m, top + rise)], dark });
    }
  });
  const shade = (a, b) => (u[0] * a + v[0] * b) * LIGHT[0] + (u[1] * a + v[1] * b) * LIGHT[1] < -0.05;
  const [A, B, C, D] = foot;
  if (kind === 'flat') {
    out.roofs.push({ pts: foot.map((p) => at(p, top)), dark: false });
  } else {
    const k = kind === 'hip' ? d / 2 * 0.9 : 0;
    const [R1, R2] = [g(-w / 2 + k, 0), g(w / 2 - k, 0)];
    const faces = [[[A, B, R2, R1], 0, -1], [[C, D, R1, R2], 0, 1]];
    if (kind === 'hip') faces.push([[B, C, R2], 1, 0], [[D, A, R1], -1, 0]);
    for (const [pts, a, b] of faces) {
      out.roofs.push({ pts: pts.map((p) => at(p, p === R1 || p === R2 ? top + rise : top)), dark: shade(a, b) });
    }
  }
  return out;
}

function layout() {
  const rand = random(20251104);
  const taken = [{ x: HOME.x, y: HOME.y, r: 12 }, { x: HOME.x, y: HOME.y + 18, r: 8 },
    { x: BLOCK.c[0], y: BLOCK.c[1], r: 26 }, ...MARKERS.map(([x, y]) => ({ x, y, r: 5 }))];
  const built = [];
  const fits = (x, y, r) => taken.every((o) => Math.hypot(o.x - x, o.y - y) > o.r + r);
  const nearBlock = (x, y) => Math.abs(x - BLOCK.c[0]) < BLOCK.d / 2 + 3 && Math.abs(y - BLOCK.c[1]) < BLOCK.w / 2 + 3;

  alongStreets(rand, [12, 5], (p, u, n, st) => {
    if (st.main && rand() < 0.3) return;
    for (const side of [-1, 1]) {
      if (rand() > 0.86) continue;
      const big = rand() < 0.2;
      const w = big ? 12 + rand() * 3 : 7 + rand() * 2.5, d = big ? 8.5 + rand() * 2 : 10 + rand() * 3;
      const back = d / 2 + st.w / 2 + 2 + rand() * 2.4;
      const v = [n[0] * side, n[1] * side];
      const c = [p[0] + v[0] * back, p[1] + v[1] * back];
      const r = (w + d) / 4;
      const pick = rand();
      const kind = big && pick < 0.3 ? 'flat' : pick < 0.55 ? 'gable' : 'hip';
      const house = { c, u, v, w, d, kind, h: (big ? 6 : 4) + rand() * 2.5, rise: kind === 'flat' ? 0 : 3 + rand() * 1.5 };
      const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) =>
        [c[0] + u[0] * a * w / 2 + v[0] * b * d / 2, c[1] + u[1] * a * w / 2 + v[1] * b * d / 2]);
      if (!inFrame(c[0], c[1]) || !fits(c[0], c[1], r) || ![c, ...corners].every(([x, y]) => onLand(x, y) && !nearBlock(x, y) && clearOfStreets(x, y, 0.8))) continue;
      taken.push({ x: c[0], y: c[1], r });
      built.push(house);
    }
  });

  const trees = [];
  const tryTree = (x, y, r, opts) => {
    if (!inFrame(x, y) || !onLand(x, y, opts) || nearBlock(x, y) || !clearOfStreets(x, y, r * 0.6)) return;
    if (!taken.every((o) => Math.hypot(o.x - x, o.y - y) > o.r + r * 0.8)) return;
    if (!trees.every((t) => Math.hypot(t.x - x, t.y - y) > (t.r + r) * 0.85)) return;
    trees.push({ x, y, r, seed: rand(), tone: rand() < 0.42 ? 1 : 0 });
  };
  alongStreets(rand, [13, 9], (p, u, n, st) => {
    for (const side of [-1, 1]) {
      if (rand() > 0.38) continue;
      const r = 3 + rand() * 1.4, off = st.w / 2 + 0.6 + r;
      tryTree(p[0] + n[0] * side * off, p[1] + n[1] * side * off, r);
    }
  });
  for (let k = 0; k < 7; k++) {
    const cx = PARK.x0 + 8 + rand() * (PARK.x1 - PARK.x0 - 16), cy = PARK.y0 + 8 + rand() * (PARK.y1 - PARK.y0 - 16);
    for (let j = 0; j < 5; j++) {
      const a = rand() * 6.283, dist = rand() * 9;
      const x = cx + Math.cos(a) * dist, y = cy + Math.sin(a) * dist;
      if (x > PARK.x0 + 4 && x < PARK.x1 - 4 && y > PARK.y0 + 4 && y < PARK.y1 - 4) tryTree(x, y, 4 + rand() * 2.4, { park: true });
    }
  }
  for (let k = 0; k < 650; k++) {
    const hill = k % 2 === 0;
    tryTree(hill ? 284 + rand() * (XE - 284) : 100 + rand() * (XE - 100), Y0 + rand() * (Y1 - Y0), hill ? 3.4 + rand() * 2.8 : 3 + rand() * 1.6);
  }
  return { built, trees };
}

// A soft, slightly lumpy crown around a screen point: smoothed through the midpoints of a wobbly ring.
function blob([x, y], r, seed) {
  const n = 6;
  const pts = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * 6.283 + seed * 3, k = r * (0.86 + 0.28 * ((Math.sin(seed * 97 + i * 2.3) + 1) / 2));
    return [x + Math.cos(a) * k, y + Math.sin(a) * k * 0.92];
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
const ellipse = ([x, y], rx, ry) => `M${f(x - rx)} ${f(y)}a${f(rx)} ${f(ry)} 0 1 0 ${f(2 * rx)} 0a${f(rx)} ${f(ry)} 0 1 0 ${f(-2 * rx)} 0Z`;

// Seigaiha: rows of concentric arcs, each row half a scale lower and offset by one radius, laid on the tilted ground.
function seigaiha(id, name, r, cls) {
  const scale = (cx, cy) => [r, r * 0.7, r * 0.4].map((k, i) =>
    s('circle', { cx, cy, r: k, class: i ? `${cls} ${cls}-ring` : cls }));
  const rows = [0, 1, 2, 3, 4].flatMap((k) => (k % 2 ? [[r, k * r / 2]] : [[0, k * r / 2], [2 * r, k * r / 2]]));
  return s('pattern', { id: `${name}-${id}`, width: 2 * r, height: r, patternUnits: 'userSpaceOnUse', patternTransform: `matrix(1 ${PB} ${-PA} ${PC} 0 0)` },
    rows.map(([x, y]) => scale(x, y)));
}

// The tsunami front: scalloped crests bulging inland, each ending in a small curl back toward the sea.
function crestPath(dx) {
  const p = (x, y) => P(x, y).map(f).join(' ');
  let d = '';
  for (let y = Y0 - 4; y < Y1 + 4; y += 22) {
    const x0 = FRONT(y) + dx, x1 = FRONT(y + 22) + dx;
    d += `M${p(x0, y)}C${p(x0 + 9, y + 2)} ${p(x1 + 9, y + 14)} ${p(x1, y + 22)}`
      + `M${p(x0 + 6.5, y + 5)}C${p(x0 + 4.9, y + 8.2)} ${p(x0 + 0.9, y + 8.6)} ${p(x0 - 0.5, y + 6.2)}`;
  }
  return d;
}

// The sand the sea uncovers when it draws back before the wave: darker wet sand, tide ripples and a few rocks.
function wetSand() {
  const rand = random(777);
  const rocks = range(Y0, Y1, 26).flatMap((y) => (rand() < 0.55 ? [] : [[SHORE(y) - 6 - rand() * (EBB - 10), y + rand() * 20, 1.2 + rand() * 1.8]]))
    .map(([x, y, r]) => ellipse(at([x, y]), r, r * 0.6)).join('');
  return [
    s('path', { d: poly([...range(Y0 - 10, Y1 + 10, 10).map((y) => [SHORE(y) + 1, y]), ...range(Y1 + 10, Y0 - 10, -10).map((y) => [SHORE(y) - EBB - 8, y])]), class: 'nb-wet' }),
    [10, 19].map((k) => s('path', { d: line(range(Y0 - 10, Y1 + 10, 10).map((y) => [SHORE(y) - k + 1.5 * Math.sin(y / 15 + k), y])), class: 'nb-wet-line' })),
    s('path', { d: rocks, class: 'nb-rock' }),
  ];
}

const seaPath = () => poly([[-120, Y0 - 10], ...range(Y0 - 10, Y1 + 10, 10).map((y) => [SHORE(y), y]), [-120, Y1 + 10]]);
const beachPath = () => poly([[-120, Y0 - 10], ...range(Y0 - 10, Y1 + 10, 20).map((y) => [COAST(y), y]), [-120, Y1 + 10]]);
const contour = (c) => curve(range(Y0 - 10, Y1 + 10, 40).map((y) => [c + 3 * Math.sin(y / 41 + c) + 2 * Math.sin(y / 19 + c * 0.3), y]), 10);

// Power lines on poles beside two streets. The wires sit in their own group so they can swing while the poles stay put.
function powerLines() {
  const runs = [range(Y0, Y1, 34).map((y) => [COAST(y) + 7, y]), range(Y0, Y1, 34).map((y) => [204 - 5.4, y])];
  const H = 11;
  const poles = runs.flat().map((p) => {
    const [b, t] = [at(p), at(p, H)];
    return `M${f(b[0])} ${f(b[1])}V${f(t[1])}M${f(t[0] - 1.8)} ${f(t[1] + 0.4)}l3.6 -0.8`;
  }).join('');
  const wires = runs.flatMap((pts) => [-1.4, 1.4].map((o) => 'M' + pts.map((p) => {
    const t = at(p, H);
    return `${f(t[0] + o)} ${f(t[1] - o * 0.22)}`;
  }).join('L'))).join('');
  return { poles: s('path', { d: poles, class: 'nb-pole' }), wires: s('g', { class: 'nb-wires' }, s('path', { d: wires, class: 'nb-wire' })) };
}

function solidPaths(parts, cls, extra = '') {
  const of = (list, dark) => list.filter((x) => x.dark === dark).map((x) => rel(x.pts)).join('');
  return [
    s('path', { class: `${cls}-wall ${extra}`, d: of(parts.flatMap((p) => p.walls), false) }),
    s('path', { class: `${cls}-wall ${cls}-wall-dark ${extra}`, d: of(parts.flatMap((p) => p.walls), true) }),
    s('path', { class: `${cls}-roof ${extra}`, d: of(parts.flatMap((p) => p.roofs), false) }),
    s('path', { class: `${cls}-roof ${cls}-roof-dark ${extra}`, d: of(parts.flatMap((p) => p.roofs), true) }),
  ];
}

let instances = 0;

export function neighborhood({ animate }) {
  const id = `nb${++instances}`;
  const url = (name) => `url(#${name}-${id})`;
  const { built, trees } = layout();
  const band = (y) => Math.max(0, Math.min(BANDS - 1, Math.floor((y + 40) / (720 / BANDS))));

  // Back to front: each band is drawn after the bands behind it, so nearer buildings cover farther ones.
  const solids = built.map((b) => ({ ...solid(b), b })).sort((a, z) => a.depth - z.depth);
  const crowns = trees.map((t) => ({ ...t, base: at([t.x, t.y]) })).sort((a, z) => a.base[1] - z.base[1]);
  const block = solid(BLOCK);
  const roofKit = [[-12, -3, 7, 6], [4, 2, 5, 4], [12, -5, 4, 4]].map(([a, b, bw, bd]) => solid({
    c: [BLOCK.c[0] + BLOCK.v[0] * (b + bd / 2) + BLOCK.u[0] * (a + bw / 2), BLOCK.c[1] + BLOCK.v[1] * (b + bd / 2) + BLOCK.u[1] * (a + bw / 2)],
    u: BLOCK.u, v: BLOCK.v, w: bw, d: bd, kind: 'flat', h: 2.5, rise: 0, z0: BLOCK.h,
  }));
  const blockBand = band(block.depth);
  const bandGroup = (k) => {
    const mine = solids.filter((x) => band(x.depth) === k);
    const greens = crowns.filter((t) => band(t.base[1]) === k);
    const shadow = mine.map(({ b }) => {
      const off = b.h * 0.5;
      return rel([[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, c]) =>
        at([b.c[0] + (b.u[0] * a * b.w + b.v[0] * c * b.d) / 2 + off * 0.5, b.c[1] + (b.u[1] * a * b.w + b.v[1] * c * b.d) / 2 + off * 0.7])));
    }).join('');
    return s('g', { class: animate ? 'nb-band' : `nb-band nb-band-${k}` },
      s('path', { class: 'nb-tree-shadow', d: greens.map((t) => ellipse([t.base[0] + 1.2, t.base[1] + 0.6], t.r * 1.05, t.r * 0.55)).join('') }),
      s('path', { class: 'nb-cast', d: shadow }),
      solidPaths(mine, 'nb-house'),
      k === blockBand ? [solidPaths([block], 'nb-house', 'nb-block'), solidPaths(roofKit, 'nb-house')] : null,
      [0, 1].map((tone) => s('path', {
        class: `nb-tree nb-tree-${tone}`,
        d: greens.filter((t) => t.tone === tone).map((t) => blob([t.base[0], t.base[1] - t.r * 1.1], t.r, t.seed)).join(''),
      })));
  };
  const ripple = ([x, y], r) => { const p = at([x, y]); return s('circle', { cx: f(p[0]), cy: f(p[1]), r, class: 'nb-ripple' }); };
  const front = range(Y0 - 10, Y1 + 10, 8).map((y) => [FRONT(y), y]);
  const shifted = (dx) => line(front.map(([x, y]) => [x + dx, y]));
  const flood = poly([[-420, Y0 - 10], ...front, [-420, Y1 + 10]]);
  const label = (text, [x, y], rot, cls = 'nb-label') => {
    const p = at([x, y]).map(f);
    return s('text', { x: p[0], y: p[1], class: cls, 'text-anchor': 'middle', transform: rot ? `rotate(${f(UP_COAST)} ${p[0]} ${p[1]})` : null }, text);
  };
  const home = solid({ c: [HOME.x, HOME.y], u: [1, 0], v: [0, 1], w: 12, d: 10, kind: 'gable', h: 6, rise: 4.5 });
  const field = range(0, 23, 1).map((i) => [FIELD.x + Math.cos(i / 24 * 6.283) * FIELD.r, FIELD.y + Math.sin(i / 24 * 6.283) * FIELD.r * 0.86]);
  const goal = at(GOAL);
  const homeAt = at([HOME.x, HOME.y]);

  const ground = [
    s('rect', { x: -60, y: -60, width: 520, height: 760, class: 'nb-paper' }),
    CONTOURS.map((c) => s('path', { class: 'nb-hill', d: poly([...contour(c), [XE + 80, Y1 + 10], [XE + 80, Y0 - 10]]) })),
    s('path', { d: beachPath(), class: 'nb-sand' }),
    s('path', { d: line(range(Y0 - 10, Y1 + 10, 10).map((y) => [SHORE(y) + 10 + 2 * Math.sin(y / 23), y])), class: 'nb-wrack' }),
    wetSand(),
    CONTOURS.map((c, i) => s('path', { class: i % 2 ? 'nb-contour nb-contour-major' : 'nb-contour', d: line(contour(c)) })),
    s('path', { d: poly([[PARK.x0, PARK.y0], [PARK.x1, PARK.y0], [PARK.x1, PARK.y1], [PARK.x0, PARK.y1]]), class: 'nb-park' }),
    s('path', { d: line(curve([[PARK.x0, 228], [166, 236], [184, 262], [190, 290], [PARK.x1, 312]])), class: 'nb-trail' }),
    s('path', { d: poly(field), class: 'nb-park nb-field' }),
    STREETS.map((st) => s('path', { d: line(st.line), class: st.main ? 'nb-casing nb-main' : 'nb-casing', 'stroke-width': st.w + 1.6 })),
    STREETS.filter((st) => st.end).map((st) => { const p = at(st.line.at(-1)); return s('ellipse', { cx: f(p[0]), cy: f(p[1]), rx: st.w * 1.3 + 0.8, ry: st.w * 1.05 + 0.8, class: 'nb-casing-end' }); }),
    STREETS.map((st) => s('path', { d: line(st.line), class: st.main ? 'nb-road nb-main' : 'nb-road', 'stroke-width': st.w })),
    STREETS.filter((st) => st.end).map((st) => { const p = at(st.line.at(-1)); return s('ellipse', { cx: f(p[0]), cy: f(p[1]), rx: st.w * 1.3, ry: st.w * 1.05, class: 'nb-road-end' }); }),
    s('g', { class: 'nb-flood' }, s('path', { d: flood, class: 'nb-flood-base' })),
  ];
  // The sea is its own layer so it can draw back off the beach as one compositor transform.
  const sea = [
    s('path', { d: seaPath(), class: 'nb-sea-base' }),
    s('path', { d: seaPath(), class: 'nb-sea', fill: url('sea') }),
    s('path', { d: line(range(Y0 - 10, Y1 + 10, 10).map((y) => [SHORE(y) - 4, y])), class: 'nb-surf' }),
    s('path', { d: line(range(Y0 - 10, Y1 + 10, 10).map((y) => [SHORE(y), y])), class: 'nb-shore' }),
  ];
  const power = powerLines();
  const top = [
    power.poles,
    MARKERS.map((m) => { const p = at(m); return s('circle', { cx: f(p[0]), cy: f(p[1]), r: 2.6, class: 'nb-marker' }); }),
    label('PACIFIC OCEAN', [24, 300], true, 'nb-label nb-label-sea'),
    s('g', { class: 'nb-flood' },
      s('path', { d: flood, class: 'nb-flood-water', fill: url('flood') }),
      s('path', { d: shifted(-9), class: 'nb-edge nb-edge-1' }),
      s('path', { d: shifted(-4.5), class: 'nb-edge nb-edge-3' }),
      s('path', { d: crestPath(-8), class: 'nb-crest' })),
    s('path', { d: line(range(Y0, Y1, 8).map((y) => [HAZARD(y), y])), class: 'nb-hazard' }),
    label('TSUNAMI HAZARD LINE', [279, 150], true, 'nb-label nb-label-small'),
    label('HIGH GROUND', [FIELD.x + 4, FIELD.y + FIELD.r + 14]),
  ];
  // The small pieces that animate all the time, kept apart so their repaints stay small.
  const live = [
    MARKERS.map((m) => ripple(m, 2.6)),
    s('path', { d: line(curve(ROUTE, 3)), class: 'nb-route-case' }),
    s('path', { d: line(curve(ROUTE, 3)), class: 'nb-route' }),
    ripple([HOME.x, HOME.y], 11),
    s('ellipse', { cx: f(homeAt[0]), cy: f(homeAt[1]), rx: 12, ry: 9.4, class: 'nb-home-ring' }),
    solidPaths([home], 'nb-home'),
    label('HOME', [HOME.x - 2, HOME.y + 19], false, 'nb-label nb-label-strong'),
    ripple(GOAL, 9),
    s('path', { d: `M${f(goal[0])} ${f(goal[1])}v-9`, class: 'nb-post' }),
    s('g', { transform: `translate(${f(goal[0] - 8)} ${f(goal[1] - 25)}) scale(${16 / 40})` }, evacMarks()),
  ];
  const bands = range(0, BANDS - 1, 1).map(bandGroup);
  const defs = s('defs', null, seigaiha(id, 'sea', 7, 'nb-scale'), seigaiha(id, 'flood', 7, 'nb-fscale'));
  const frame = (cls, ...kids) => s('svg', { class: cls, viewBox: '0 0 400 640', preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true' }, ...kids);
  const summary = 'Map of a coastal neighbourhood. Two small tremors, then a strong earthquake shakes the ground and debris falls. '
    + 'The sea draws back off the beach, a tsunami floods the low streets up to the hazard line, then the water goes back out. A dashed yellow route leads from a highlighted home uphill to high ground.';

  if (!animate) {
    const one = frame('nb', defs, ground, sea, bands, power.wires, top, live);
    one.removeAttribute('aria-hidden');
    one.setAttribute('role', 'img');
    one.setAttribute('aria-label', summary);
    return one;
  }
  // Animated, the drawing is a stack of same-sized layers, so the shake and each band's jitter are compositor transforms
  // on whole layers and never repaint the drawing. Only the flood, route and ripples repaint, in their own layers.
  return h('div', { class: 'nb-stack', role: 'img', 'aria-label': summary },
    frame('nb nb-animate', defs, ground),
    frame('nb-layer nb-sea-layer', sea),
    bands.map((g, k) => frame(`nb-layer nb-band-${k}`, g)),
    frame('nb-layer nb-wire-layer', power.wires),
    frame('nb-layer nb-top', top),
    frame('nb-layer nb-live', live),
    h('div', { class: 'nb-hush' }),
    h('div', { class: 'nb-flash' }));
}

// Falling debris during the shocks, drawn on a canvas over the map. Every particle is a pure function of the loop
// time read from the map's own CSS animation, so the two never drift apart and a paused or seeked animation shows a
// matching frame. The same clock drives the phase pill through onPhase(label, level). One requestAnimationFrame loop; it
// idles while the tab is hidden and ends once the map leaves the page.
const FIRST = SHOCKS[0].jolts[0], LAST = SHOCKS.at(-1).end;
const DUST = ['#A79E8E', '#C2B9A8', '#C9A24E', '#B07F2E', '#8F877A'];

function particles() {
  const rand = random(4041);
  const list = [];
  const add = (kind, shock, spread) => {
    const { jolts, end, fade } = shock;
    spread = Math.min(spread, end - jolts[0]);
    for (let i = 0; i < shock[kind]; i++) {
      const burst = rand() < 0.75;
      const t0 = burst ? jolts[Math.floor(rand() * jolts.length)] + rand() * spread : jolts[0] + rand() * (end - jolts[0]);
      list.push({
        kind, t0, fade, x: rand(), y: -0.04 + rand() * (kind === 'chunk' ? 0.05 : 0.3),
        life: kind === 'chunk' ? 1400 + rand() * 500 : 1600 + rand() * 1200,
        vx: (rand() - 0.5) * (kind === 'dust' ? 0.05 : 0.08), vy: rand() * 0.05,
        g: kind === 'chunk' ? 0.62 + rand() * 0.2 : kind === 'bit' ? 0.42 + rand() * 0.18 : 0.14 + rand() * 0.14,
        size: kind === 'chunk' ? 5 + rand() * 4 : kind === 'bit' ? 2.2 + rand() * 2.4 : 1.1 + rand() * 1.5,
        spin: (rand() - 0.5) * 9, angle: rand() * 6.283, sway: rand() * 6.283,
        color: kind === 'chunk' ? '#DCD8CF' : DUST[Math.floor(rand() * DUST.length)],
        shape: Array.from({ length: 5 }, (_, k) => [k / 5 * 6.283, 0.7 + rand() * 0.45]),
      });
    }
  };
  for (const shock of SHOCKS) { add('dust', shock, 1000); add('bit', shock, 800); add('chunk', shock, 400); }
  return list;
}

export function debris(svg, onPhase = () => {}) {
  const canvas = h('canvas', { class: 'nb-debris', 'aria-hidden': 'true' });
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  const list = particles();
  let raf = 0, seen = false, size = '', drawn = false, phase = 0;

  const clock = () => {
    const anim = svg.getAnimations()[0];
    return anim && anim.currentTime != null ? Number(anim.currentTime) % LOOP_MS : null;
  };
  const draw = (t) => {
    const w = canvas.clientWidth, ht = canvas.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
    if (`${w}x${ht}x${dpr}` !== size) {
      size = `${w}x${ht}x${dpr}`;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(ht * dpr);
      drawn = false;
    }
    const active = t != null && t >= FIRST && t <= LAST + 3000;
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
      ctx.globalAlpha = (p.kind === 'dust' ? a * 0.9 : a) * p.fade;
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
      if (p.kind === 'chunk') { ctx.lineWidth = 1; ctx.strokeStyle = '#34302A'; ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
  };
  const frame = () => {
    raf = 0;
    if (!canvas.isConnected) {
      if (seen) { document.removeEventListener('visibilitychange', wake); return; }
    } else {
      seen = true;
      const t = clock();
      draw(t);
      // Before the first mark (a negative clock right after start) the phase is the first one, not -1.
      const now = t == null ? 0 : Math.max(0, TIMELINE.findLastIndex(([at]) => t >= at));
      if (now !== phase) { phase = now; onPhase(TIMELINE[now][1], TIMELINE[now][2]); }
    }
    if (!document.hidden) raf = requestAnimationFrame(frame);
  };
  const wake = () => { if (!document.hidden && !raf) raf = requestAnimationFrame(frame); };
  document.addEventListener('visibilitychange', wake);
  raf = requestAnimationFrame(frame);
  return canvas;
}
