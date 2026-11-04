import { h, icon, localTime, sampleTag } from '../dom.js';
import { formatDistance } from '../geometry.js';
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

export function routeView(route, building, { onMap } = {}) {
  if (route.kind === 'direction_only') {
    return h('div', { class: 'route route-direction' },
      compassArrow(route.bearing_deg),
      h('p', { class: 'route-bearing' }, `Head ${route.compass}`, h('span', { class: 'mono' }, ` ${Math.round(route.bearing_deg)}°`)),
      h('p', { class: 'route-figures mono' }, `${formatDistance(route.straight_m)} in a straight line`),
      h('p', { class: 'route-reason' }, route.reason),
      h('p', { class: 'fine mono' }, `Computed ${localTime(route.computed_at)}`, ' ', sampleTag(route)));
  }
  const map = routeMap(route, building?.hazard_area?.polygons);
  onMap?.(map);
  return h('div', { class: 'route route-walk' },
    h('div', { class: 'route-figures' },
      h('div', null, h('span', { class: 'figure-num' }, walkMinutes(route.walk_min)), h('span', { class: 'figure-label' }, 'walk')),
      h('div', null, h('span', { class: 'figure-num' }, formatDistance(route.distance_m)), h('span', { class: 'figure-label' }, 'to outside the hazard area'))),
    h('figure', { class: 'route-map' }, map.svg,
      h('figcaption', { class: 'map-key' },
        h('span', { class: 'key key-hazard' }, 'Tsunami hazard area'),
        h('span', { class: 'key key-path' }, 'Walking route'),
        h('span', { class: 'key key-pos' }, 'You'))),
    h('ol', { class: 'turns' }, route.steps.map((st) =>
      h('li', null, h('span', { class: 'turn-text' }, st.instruction),
        st.distance_m > 0 ? h('span', { class: 'turn-dist mono' }, formatDistance(st.distance_m)) : null))),
    h('p', { class: 'fine mono' }, `Computed ${localTime(route.computed_at)}`, ' ', sampleTag(route)));
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
    h('p', { class: 'shelter-meta mono' },
      result.replay ? h('span', { class: 'tag-replay' }, 'Replay data') : null,
      `Data from ${localTime(result.fetched_at)}`, ' ', sampleTag(result)));
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
