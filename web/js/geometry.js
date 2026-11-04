const R = 6371008.8;
const RAD = Math.PI / 180;

// Local equirectangular frame in metres east (x) and north (y) of an origin. Accurate to well under 1% over a few km.
export function localFrame([lon0, lat0]) {
  const kx = R * RAD * Math.cos(lat0 * RAD);
  const ky = R * RAD;
  return ([lon, lat]) => [(lon - lon0) * kx, (lat - lat0) * ky];
}

export function bounds(points) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return { minX, minY, maxX, maxY };
}

// Pads the box, enforces a minimum span, and widens it to the target width/height aspect.
export function fitView(b, { pad = 0.2, minSpan = 300, aspect = 1.25 } = {}) {
  const cx = (b.minX + b.maxX) / 2, cy = (b.minY + b.maxY) / 2;
  let w = Math.max((b.maxX - b.minX) * (1 + 2 * pad), minSpan);
  let h = Math.max((b.maxY - b.minY) * (1 + 2 * pad), minSpan / aspect);
  if (w / h < aspect) w = h * aspect; else h = w / aspect;
  return { minX: cx - w / 2, minY: cy - h / 2, w, h };
}

// Largest 1, 2 or 5 x 10^n not above `max`.
export function niceLength(max) {
  const p = 10 ** Math.floor(Math.log10(max));
  for (const m of [5, 2, 1]) if (m * p <= max) return m * p;
  return p;
}

export function formatDistance(m) {
  if (m >= 1000) return `${(m / 1000).toFixed(m >= 10000 ? 0 : 1)} km`;
  return `${Math.round(m / 10) * 10} m`;
}

export function haversine([lon1, lat1], [lon2, lat2]) {
  const dLat = (lat2 - lat1) * RAD, dLon = (lon2 - lon1) * RAD;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// Places one callout balloon per anchor, starting above it, then pushes overlapping balloons apart
// and keeps them inside the image.
export function layoutBalloons(anchors, w, h, r) {
  const pos = anchors.map(([x, y]) => [x, y - 3.2 * r]);
  const clamp = (p) => {
    p[0] = Math.min(Math.max(p[0], r * 1.2), w - r * 1.2);
    p[1] = Math.min(Math.max(p[1], r * 1.2), h - r * 1.2);
  };
  pos.forEach(clamp);
  const gap = r * 2.4;
  for (let iter = 0; iter < 80; iter++) {
    let moved = false;
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const dx = pos[j][0] - pos[i][0], dy = pos[j][1] - pos[i][1];
        const d = Math.hypot(dx, dy);
        if (d >= gap) continue;
        const ux = d ? dx / d : 1, uy = d ? dy / d : 0;
        const push = (gap - d) / 2 + 0.5;
        pos[i][0] -= ux * push; pos[i][1] -= uy * push;
        pos[j][0] += ux * push; pos[j][1] += uy * push;
        clamp(pos[i]); clamp(pos[j]);
        moved = true;
      }
    }
    if (!moved) break;
  }
  return pos;
}
