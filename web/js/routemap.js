import { s } from './dom.js';
import { bounds, fitView, formatDistance, localFrame, niceLength } from './geometry.js';

let hatchSeq = 0;

// Offline route drawing: no tiles, just the hazard area, the path and the two ends in a local metric frame.
// Returns the svg and a function that moves the live position dot.
export function routeMap(route, hazardPolygons) {
  const project = localFrame(route.origin);
  const toSvg = (ll) => { const [x, y] = project(ll); return [x, -y]; };
  const keyPoints = [route.origin, route.destination, ...(route.path ?? [])].map(project);
  const view = fitView(bounds(keyPoints));
  const vb = { x: view.minX, y: -(view.minY + view.h), w: view.w, h: view.h };
  const u = vb.w / 100;
  const id = `hatch-${++hatchSeq}`;

  const ringPath = (ring) => 'M' + ring.map((ll) => toSvg(ll).map((n) => n.toFixed(1)).join(',')).join(' L') + ' Z';
  const hazard = (hazardPolygons ?? []).map((poly) =>
    s('path', { d: poly.map(ringPath).join(' '), class: 'rm-hazard', fill: `url(#${id})`, 'fill-rule': 'evenodd' }));

  const pts = (route.path?.length ? route.path : [route.origin, route.destination]).map(toSvg);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const [ox, oy] = toSvg(route.origin), [dx, dy] = toSvg(route.destination);
  const scaleLen = niceLength(vb.w * 0.3);
  // The scale bar takes the bottom corner away from home, so the HOME label stays readable.
  const homeOnLeft = ox < vb.x + vb.w / 2;
  const sx = homeOnLeft ? vb.x + vb.w - 4 * u - scaleLen : vb.x + 4 * u, sy = vb.y + vb.h - 5 * u, sw = scaleLen;
  const nx = vb.x + vb.w - 7 * u, ny = vb.y + 6 * u;

  // Labels sit on the side of their marker that faces the middle of the map, so they never run off the edge.
  const label = (x, y, text) => {
    const right = x < vb.x + vb.w / 2;
    return s('text', { x: x + (right ? 3.4 : -3.4) * u, y, class: 'rm-label', 'font-size': 3.4 * u, 'text-anchor': right ? 'start' : 'end' }, text);
  };

  const pos = s('g', { class: 'rm-pos', visibility: 'hidden' },
    s('circle', { r: 2.6 * u, class: 'rm-pos-halo' }), s('circle', { r: 1.4 * u, class: 'rm-pos-dot' }));

  const svg = s('svg', {
    class: 'routemap', viewBox: `${vb.x} ${vb.y} ${vb.w} ${vb.h}`, role: 'img',
    'aria-label': `Route map: ${formatDistance(route.distance_m ?? route.straight_m)} to outside the hazard area`,
  },
  s('defs', null, s('pattern', { id, width: 2.2 * u, height: 2.2 * u, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' },
    s('line', { x1: 0, y1: 0, x2: 0, y2: 2.2 * u, class: 'rm-hatch' }))),
  s('rect', { x: vb.x, y: vb.y, width: vb.w, height: vb.h, class: 'rm-paper' }),
  hazard,
  s('polyline', { points: line, class: route.kind === 'walking_route' ? 'rm-path' : 'rm-path rm-path-direct' }),
  s('circle', { cx: ox, cy: oy, r: 2.2 * u, class: 'rm-start' }),
  label(ox, oy + 5 * u, 'HOME'),
  s('rect', { x: dx - 2.2 * u, y: dy - 2.2 * u, width: 4.4 * u, height: 4.4 * u, class: 'rm-end' }),
  label(dx, dy - 3.4 * u, 'OUT OF ZONE'),
  s('g', { class: 'rm-north' },
    s('path', { d: `M${nx},${ny - 4 * u} L${nx + 2.4 * u},${ny + 3 * u} L${nx},${ny + 1.6 * u} L${nx - 2.4 * u},${ny + 3 * u} Z` }),
    s('text', { x: nx, y: ny + 8 * u, 'font-size': 3.4 * u, 'text-anchor': 'middle' }, 'N')),
  s('g', { class: 'rm-scale' },
    s('rect', { x: sx - u, y: sy - 5.5 * u, width: sw + 2 * u, height: 7.5 * u, class: 'rm-scale-bg' }),
    s('path', { d: `M${sx},${sy - 1.4 * u} V${sy} H${sx + sw} V${sy - 1.4 * u}` }),
    s('text', { x: sx, y: sy - 2.2 * u, 'font-size': 3 * u }, formatDistance(scaleLen))),
  pos);

  const inView = ([x, y]) => x >= vb.x && x <= vb.x + vb.w && y >= vb.y && y <= vb.y + vb.h;
  function showPosition(lonlat) {
    const p = toSvg(lonlat);
    if (!inView(p)) { pos.setAttribute('visibility', 'hidden'); return false; }
    pos.setAttribute('transform', `translate(${p[0]} ${p[1]})`);
    pos.setAttribute('visibility', 'visible');
    return true;
  }
  return { svg, showPosition };
}

export function compassArrow(bearing) {
  return s('svg', { class: 'compass', viewBox: '-50 -50 100 100', role: 'img', 'aria-label': `Head ${Math.round(bearing)} degrees` },
    s('circle', { r: 46, class: 'compass-ring' }),
    s('text', { x: 0, y: -34, 'text-anchor': 'middle', 'font-size': 11, class: 'compass-n' }, 'N'),
    s('g', { transform: `rotate(${bearing})` },
      s('path', { d: 'M0,-40 L14,-12 L5,-12 L5,32 L-5,32 L-5,-12 L-14,-12 Z', class: 'compass-arrow' })));
}
