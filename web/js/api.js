export class ApiError extends Error {
  constructor(status, code) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

async function call(path, init) {
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, 'offline');
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.error ?? `http_${res.status}`);
  return body;
}

const ROUTE_KINDS = new Set(['walking_route', 'site_route', 'direction_only', 'no_checked_route', 'not_in_zone']);

export const getGuidance = (region) => call(region ? `/api/guidance?region=${encodeURIComponent(region)}` : '/api/guidance');
export const getDemo = (region) => call(region ? `/api/demo?region=${encodeURIComponent(region)}` : '/api/demo');

// A place outside every mapped region is an answer, not an error; the caller shows its reason.
async function profile(path) {
  const body = await call(path);
  if (body.kind === 'no_coverage') {
    const e = new ApiError(200, 'no_coverage');
    e.reason = body.reason;
    throw e;
  }
  return body;
}

export const getProfile = (address) => profile(`/api/profile?address=${encodeURIComponent(address)}`);

export const getProfileAt = (lon, lat) =>
  profile(`/api/profile?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);

export const checkGoBag = (jpeg) =>
  call('/api/gobag', { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: jpeg });

export const scanRoom = (name, jpeg) =>
  call(`/api/scan?name=${encodeURIComponent(name)}`, {
    method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: jpeg,
  });

export async function getEvac(building, household) {
  const body = await call('/api/evac', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ building, household }),
  });
  if (body.route && !ROUTE_KINDS.has(body.route.kind)) throw new ApiError(200, `unknown_route_kind_${body.route.kind}`);
  return { route: body.route ?? null, shelters: body.shelters ?? null, shelters_error: body.shelters_error ?? null };
}

export async function fetchBlob(url) {
  const res = await fetch(url);
  if (!res.ok) throw new ApiError(res.status, 'image_unavailable');
  return res.blob();
}
