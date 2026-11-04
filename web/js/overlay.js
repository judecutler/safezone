import { s } from './dom.js';
import { layoutBalloons } from './geometry.js';

export function hazardNumbers(scan) {
  const numbers = new Map();
  for (const c of scan.classified) if (c.role === 'hazard') numbers.set(c.segment.id, numbers.size + 1);
  return numbers;
}

function segmentShape(seg, cls) {
  if (seg.outline) return s('path', { d: seg.outline, class: cls });
  const [l, t, r, b] = seg.bbox;
  return s('rect', { x: l, y: t, width: r - l, height: b - t, class: cls });
}

export function spotPoint(spot, byId) {
  if (spot.kind === 'open_floor') return spot.point;
  if (spot.kind === 'cover') {
    const seg = byId.get(spot.anchor_id)?.segment;
    if (!seg) return null;
    const [l, t, r, b] = seg.bbox;
    return [(l + r) / 2, (t + b) / 2];
  }
  return null;
}

// Line art over the photo: hazards in red with numbered balloons, cover thick black, neutral thin dashed grey,
// Muse Spark's relations as red dashed connectors, and a crosshair at each located spot to drop.
export function roomOverlay(scan, imageUrl) {
  const [w, h] = scan.image_size;
  const u = w / 100;
  const r = Math.max(2.6 * u, h * 0.035);
  const byId = new Map(scan.classified.map((c) => [c.segment.id, c]));
  const numbers = hazardNumbers(scan);
  const hazards = scan.classified.filter((c) => c.role === 'hazard');

  const layers = { neutral: [], cover: [], hazard: [], relations: [], callouts: [], spots: [] };
  for (const c of scan.classified) {
    if (c.role === 'neutral') layers.neutral.push(segmentShape(c.segment, 'ov-neutral'));
    if (c.role === 'cover') layers.cover.push(segmentShape(c.segment, 'ov-halo'), segmentShape(c.segment, 'ov-cover'));
    if (c.role === 'hazard') layers.hazard.push(segmentShape(c.segment, 'ov-halo'), segmentShape(c.segment, 'ov-hazard'));
  }

  for (const rel of scan.relations ?? []) {
    const a = byId.get(rel.subject_id)?.segment, b = byId.get(rel.hazard_id)?.segment;
    if (!a || !b) continue;
    // Centroids, not box edges: a bed and the wardrobe that can fall on it often have overlapping boxes.
    const [[x1, y1], [x2, y2]] = [a.centroid, b.centroid];
    layers.relations.push(
      s('line', { x1, y1, x2, y2, class: 'ov-halo-thin' }),
      s('line', { x1, y1, x2, y2, class: 'ov-relation' }),
      s('circle', { cx: x1, cy: y1, r: u * 0.6, class: 'ov-relation-end' }),
      s('circle', { cx: x2, cy: y2, r: u * 0.6, class: 'ov-relation-end' }));
  }

  const anchors = hazards.map((c) => {
    const [l, t, rr] = c.segment.bbox;
    return [(l + rr) / 2, Math.max(t, 0) + Math.min(c.segment.bbox[3] - t, 6 * u) / 2];
  });
  const balloons = layoutBalloons(anchors, w, h, r);
  hazards.forEach((c, i) => {
    const [ax, ay] = anchors[i], [bx, by] = balloons[i];
    const d = Math.hypot(bx - ax, by - ay) || 1;
    const ex = bx - ((bx - ax) / d) * r, ey = by - ((by - ay) / d) * r;
    layers.callouts.push(
      s('line', { x1: ax, y1: ay, x2: ex, y2: ey, class: 'ov-leader' }),
      s('circle', { cx: ax, cy: ay, r: u * 0.55, class: 'ov-leader-dot' }),
      s('circle', { cx: bx, cy: by, r, class: 'ov-balloon' }),
      s('text', { x: bx, y: by, class: 'ov-balloon-text', 'font-size': r * 1.15, dy: '0.36em' },
        String(numbers.get(c.segment.id))));
  });

  scan.spots.forEach((spot, i) => {
    const p = spotPoint(spot, byId);
    if (!p) return;
    const [x, y] = p, R = 3.4 * u;
    const ticks = `M${x - 2 * R},${y} H${x - R * 0.45} M${x + R * 0.45},${y} H${x + 2 * R} ` +
      `M${x},${y - 2 * R} V${y - R * 0.45} M${x},${y + R * 0.45} V${y + 2 * R}`;
    layers.spots.push(s('g', { class: i === 0 ? 'ov-spot' : 'ov-spot ov-spot-alt' },
      s('circle', { cx: x, cy: y, r: R, class: 'ov-halo' }),
      s('path', { d: ticks, class: 'ov-halo' }),
      s('circle', { cx: x, cy: y, r: R, class: 'ov-spot-ring' }),
      s('path', { d: ticks, class: 'ov-spot-ring' }),
      s('circle', { cx: x, cy: y, r: u * 0.7, class: 'ov-spot-dot' }),
      s('text', { x: x + R * 1.25, y: y - R * 1.25, class: 'ov-spot-label', 'font-size': 2.6 * u },
        i === 0 ? 'DROP HERE' : `OPTION ${i + 1}`)));
  });

  return s('svg', {
    class: 'overlay', viewBox: `0 0 ${w} ${h}`, role: 'img',
    'aria-label': `${scan.name}: ${hazards.length} hazards marked`,
  },
  s('image', { href: imageUrl, x: 0, y: 0, width: w, height: h, class: 'ov-photo', preserveAspectRatio: 'none' }),
  s('rect', { x: 0, y: 0, width: w, height: h, class: 'ov-wash' }),
  layers.neutral, layers.cover, layers.relations, layers.hazard, layers.callouts, layers.spots);
}
