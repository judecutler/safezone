import { h, icon, localTime, sampleTag } from '../dom.js';
import { formatDistance } from '../geometry.js';
import { hazardExit, liveMap } from '../livemap.js';
import { compassArrow, routeMap } from '../routemap.js';

export const NEEDS = [
  ['children', 'Young children'],
  ['wheelchair', 'Wheelchair or mobility aid'],
  ['medical', 'Medical needs'],
  ['pets', 'Pets'],
];

export const SPOT_KIND = { cover: 'Under cover', open_floor: 'Open floor', no_cover: 'No cover nearby' };

export const TSUNAMI_MAP_MISSING =
  'The tsunami hazard map was not available when this plan was made. Follow official instructions. ' +
  'If the shaking was strong or lasted a long time, move inland and uphill now.';

export function walkMinutes(min) {
  return min < 1 ? 'under 1 min' : `${Math.round(min)} min`;
}

export function duringSpecials(plan, guidance) {
  const special = guidance?.during_special;
  if (!special) return [];
  return [plan?.household?.wheelchair && special.wheelchair, special.in_bed].filter(Boolean);
}

// `shelters` is plan.shelters (drawn as places), `walker` adds the live position to the legend, `fitTo` frames the map.
export function routeView(route, building, { onMap, shelters = null, walker = false, fitTo = 'all' } = {}) {
  if (route.kind === 'no_checked_route') {
    return h('div', { class: 'route route-direction' },
      h('p', { class: 'route-reason' }, route.reason),
      route.map_url ? h('p', null, h('a', { href: route.map_url, target: '_blank', rel: 'noopener' }, 'Official tsunami hazard map')) : null);
  }
  if (route.kind === 'direction_only') {
    return h('div', { class: 'route route-direction' },
      compassArrow(route.bearing_deg),
      h('p', { class: 'route-bearing' }, `Head ${route.compass}`, h('span', { class: 'mono' }, ` ${Math.round(route.bearing_deg)}°`)),
      h('p', { class: 'route-figures mono' }, `${formatDistance(route.straight_m)} in a straight line`),
      h('p', { class: 'route-reason' }, route.reason),
      h('p', { class: 'fine mono' }, `Computed ${localTime(route.computed_at)}`, ' ', sampleTag(route)));
  }
  const region = regionOf(building);
  const map = mapView(route, building, region, { shelters, walker, fitTo });
  onMap?.(map);
  const site = route.kind === 'site_route' ? route.site : null;
  return h('div', { class: 'route route-walk' },
    h('div', { class: 'route-figures' },
      h('div', null, h('span', { class: 'figure-num' }, walkMinutes(route.walk_min)), h('span', { class: 'figure-label' }, 'walk')),
      h('div', null, h('span', { class: 'figure-num' }, formatDistance(route.distance_m)),
        h('span', { class: 'figure-label' }, site ? 'to a designated evacuation site' : 'to outside the hazard area'))),
    site ? h('div', { class: 'route-site' },
      h('p', { class: 'route-site-name' }, site.name, h('span', { class: 'jp' }, ' 指定緊急避難場所')),
      h('p', null, site.instruction),
      h('p', { class: 'fine mono' }, h('a', { href: site.source_url, target: '_blank', rel: 'noopener' }, site.source_name), ' ', sampleTag(site))) : null,
    h('figure', { class: 'route-map' }, map.element, mapLegend(route, building, region, { shelters, walker })),
    h('ol', { class: 'turns' }, route.steps.map((st) =>
      h('li', null, h('span', { class: 'turn-text' }, st.instruction),
        st.distance_m > 0 ? h('span', { class: 'turn-dist mono' }, formatDistance(st.distance_m)) : null))),
    h('p', { class: 'fine mono' }, `Computed ${localTime(route.computed_at)}`, ' ', sampleTag(route)));
}

const regionOf = (building) => (/gsi\.go\.jp/.test(building?.hazard_area?.source_url ?? '') ? 'jp' : 'us-ca');

function mapPlaces(shelters, route, region) {
  const end = route.destination;
  return (shelters?.matches ?? [])
    .filter(({ shelter: sh }) => sh.lon != null && sh.lat != null)
    // A designated site that is the route's own destination is already labelled there.
    .filter(({ shelter: sh }) => !(route.kind === 'site_route' && Math.abs(sh.lon - end[0]) < 3e-4 && Math.abs(sh.lat - end[1]) < 3e-4))
    .map((m) => ({ lon: m.shelter.lon, lat: m.shelter.lat, label: `${m.shelter.name} · ${walkMinutes(m.walk_min)}`, kind: region === 'jp' ? 'site' : 'shelter' }));
}

// The live map with the offline SVG behind it: the SVG shows when Leaflet cannot load. The returned
// showPosition(lonlat, note) moves the live position on whichever map is up and returns false only when the
// SVG map cannot show that point.
function mapView(route, building, region, { shelters, fitTo }) {
  const fallback = routeMap(route, building?.hazard_area?.polygons);
  const holder = h('div', { class: 'lm-holder', role: 'img', 'aria-label': fallback.svg.getAttribute('aria-label') });
  let live = null, failed = false, last = null;
  const mount = () => liveMap(holder, { region }).then((c) => {
    if (!holder.isConnected) { c.destroy(); return; }
    live = c;
    c.setHazard(building?.hazard_area);
    c.setRoute(route);
    c.setHome(route.origin);
    c.setPlaces(mapPlaces(shelters, route, region));
    c.fit(fitTo);
    if (last) c.setWalker(last.lonlat, { note: last.note });
    const watch = setInterval(() => { if (!holder.isConnected) { clearInterval(watch); c.destroy(); live = null; } }, 3000);
  }).catch(() => {
    failed = true;
    holder.replaceWith(fallback.svg);
    if (last) fallback.showPosition(last.lonlat);
  });
  // Leaflet needs its container in the page with a size, and the caller attaches this view after it returns.
  let tries = 0;
  const wait = () => (holder.isConnected ? mount() : ++tries < 300 ? requestAnimationFrame(wait) : null);
  requestAnimationFrame(wait);
  return {
    element: holder,
    showPosition(lonlat, note = null) {
      last = { lonlat, note };
      if (failed) return fallback.showPosition(lonlat);
      live?.setWalker(lonlat, { note });
      return true;
    },
  };
}

function mapLegend(route, building, region, { shelters, walker }) {
  const area = building?.hazard_area;
  const jp = region === 'jp';
  const site = route.kind === 'site_route' ? route.site : null;
  const exit = hazardExit(route, area);
  const link = (href, text) => (href ? h('a', { href, target: '_blank', rel: 'noopener' }, text) : text);
  const row = (sw, name, src) => h('li', null, h('span', { class: `lm-sw lm-sw-${sw}` }), h('span', null, name), h('span', { class: 'lm-src' }, src));
  const places = mapPlaces(shelters, route, region);
  return h('figcaption', null, h('ul', { class: 'lm-legend' },
    jp ? row('hazard-jp', 'Tsunami inundation, expected depth', ['Hazard Map Portal, GSI (', h('span', { class: 'jp' }, 'ハザードマップポータルサイト'), ')'])
      : row('hazard', 'Tsunami hazard area', link(area?.source_url, 'California Geological Survey')),
    row('route', 'Walking route with numbered turns', ['OSRM on OpenStreetMap streets ', sampleTag(route)]),
    exit ? row('exit', 'Leaving the hazard area', 'Where the route crosses the CGS hazard line') : null,
    row('home', 'Home', building?.address ?? 'Saved place'),
    row('dest', site ? site.name : 'Outside the hazard area', site ? [site.source_name, ' ', sampleTag(site)] : 'End of the route, on mapped land beyond the hazard area'),
    places.length ? row('place', jp ? 'Other designated evacuation sites' : 'Open shelters',
      [jp ? 'GSI designated evacuation sites' : 'FEMA National Shelter System', ' ', sampleTag(shelters)]) : null,
    walker ? row('walker', 'You', 'GPS position, or the demo walker in demo mode') : null));
}

export function shelterSection(plan, sheltersError) {
  const result = plan.shelters;
  if (sheltersError || !result) {
    return h('p', { class: 'notice' }, 'Shelter data was unavailable when this plan was made. ',
      sheltersError ? h('span', { class: 'fine' }, sheltersError) : null);
  }
  const excluded = Object.entries(result.excluded ?? {}).filter(([, n]) => n > 0);
  const EXCLUDE_TEXT = {
    not_open: 'not open', in_hazard_area: 'inside the hazard area',
    hazard_check_failed: 'could not be checked against the hazard map', not_wheelchair_accessible: 'not wheelchair accessible',
  };
  return h('div', { class: 'shelters' },
    h('p', { class: 'call-ahead' }, 'Call ahead and confirm with local officials before you go. Shelter status changes fast.'),
    result.ranking ? h('p', { class: 'fine' }, result.ranking) : null,
    result.matches.length === 0
      ? h('p', { class: 'notice' }, 'No open shelter in the data fits this household. Follow official instructions for where to go.')
      : h('ol', { class: 'shelter-list' }, result.matches.map((m) => shelterCard(m, result))),
    excluded.length ? h('p', { class: 'fine' }, 'Left out: ',
      excluded.map(([k, n]) => `${n} ${EXCLUDE_TEXT[k] ?? k}`).join('; '), '.') : null);
}

function shelterCard(m, result) {
  const sh = m.shelter;
  const pct = m.fill_ratio == null ? null : Math.round(m.fill_ratio * 100);
  return h('li', { class: 'shelter' },
    h('div', { class: 'shelter-head' },
      h('h4', null, sh.name),
      h('span', { class: 'shelter-walk' }, walkMinutes(m.walk_min), m.walk_method === 'estimate' ? h('span', { class: 'est' }, 'estimate') : null)),
    h('p', { class: 'shelter-addr' }, sh.address),
    h('div', { class: 'fill' },
      pct == null
        ? h('span', { class: 'fill-label' }, 'Occupancy not reported')
        : [h('div', { class: 'fill-bar', role: 'meter', 'aria-valuenow': pct, 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-label': 'How full' },
            h('div', { class: pct >= 80 ? 'fill-in fill-high' : 'fill-in', style: `width:${Math.min(pct, 100)}%` })),
          h('span', { class: 'fill-label mono' }, `${pct}% full (${sh.residents} of ${sh.capacity})`)]),
    m.notes.length ? h('ul', { class: 'shelter-notes' }, m.notes.map((n) => h('li', null, n))) : null,
    // Sample shelters are made up, so a fetch time or a replay tag would read as a real record.
    h('p', { class: 'shelter-meta mono' }, result.provenance === 'sample' ? sampleTag(result) : [
      result.replay ? h('span', { class: 'tag-replay' }, 'Replay data') : null,
      `Data from ${localTime(result.fetched_at)}`]));
}

const TONE_ICON = { alert: 'alert', ok: 'check', unknown: 'question', info: 'info' };

export function flagList(building) {
  return h('ul', { class: 'flags' }, building.flags.map((f) =>
    h('li', { class: `flag tone-${f.tone}` },
      icon(TONE_ICON[f.tone], 'flag-icon'),
      h('div', { class: 'flag-body' },
        h('p', { class: 'flag-value' }, f.value),
        h('p', { class: 'flag-detail' }, f.detail),
        f.status ? h('p', { class: 'flag-status mono' }, `Status: ${f.status}`) : null,
        h('p', { class: 'flag-source mono' },
          h('a', { href: f.source_url, target: '_blank', rel: 'noopener' }, f.source_name), ' ', sampleTag(f))))));
}
