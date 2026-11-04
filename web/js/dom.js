const SVG_NS = 'http://www.w3.org/2000/svg';

function build(el, props, children) {
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.setAttribute('class', v);
    else if (k in el && !(el instanceof SVGElement)) el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

export const h = (tag, props, ...children) => build(document.createElement(tag), props, children);
export const s = (tag, props, ...children) => build(document.createElementNS(SVG_NS, tag), props, children);

export function sampleTag(obj) {
  return obj?.provenance === 'sample' ? h('span', { class: 'tag-sample', title: 'Hand-made stand-in data, not an official record' }, 'Sample data') : null;
}

const PATHS = {
  children: [
    ['circle', { cx: 16, cy: 9, r: 4 }],
    ['path', { d: 'M10 30 L12 18 H20 L22 30 M12 21 L7 25 M20 21 L25 25' }],
    ['circle', { cx: 30, cy: 17, r: 3 }],
    ['path', { d: 'M26 34 L27 24 H33 L34 34' }],
  ],
  wheelchair: [
    ['circle', { cx: 15, cy: 6, r: 3 }],
    ['path', { d: 'M15 10 V22 H26 L30 32 M15 15 H24' }],
    ['path', { d: 'M10 19 A9 9 0 1 0 24 30' }],
  ],
  medical: [
    ['path', { d: 'M15 4 H25 V15 H36 V25 H25 V36 H15 V25 H4 V15 H15 Z' }],
  ],
  pets: [
    ['ellipse', { cx: 20, cy: 26, rx: 8, ry: 7 }],
    ['circle', { cx: 9, cy: 16, r: 3.5 }],
    ['circle', { cx: 15, cy: 9, r: 3.5 }],
    ['circle', { cx: 25, cy: 9, r: 3.5 }],
    ['circle', { cx: 31, cy: 16, r: 3.5 }],
  ],
  check: [['path', { d: 'M6 21 L16 31 L34 9' }]],
  question: [['path', { d: 'M13 14 A7 7 0 1 1 22 21 Q20 22 20 25 V27 M20 32 V34' }]],
  alert: [['path', { d: 'M20 4 L37 35 H3 Z M20 15 V25 M20 29 V31' }]],
  info: [['path', { d: 'M20 11 V13 M20 18 V30' }], ['rect', { x: 5, y: 5, width: 30, height: 30 }]],
  camera: [['path', { d: 'M4 12 H12 L15 7 H25 L28 12 H36 V33 H4 Z' }], ['circle', { cx: 20, cy: 22, r: 7 }]],
  target: [['circle', { cx: 20, cy: 20, r: 10 }], ['path', { d: 'M20 2 V14 M20 26 V38 M2 20 H14 M26 20 H38' }]],
};

export function icon(name, cls = 'icon') {
  return s('svg', { class: cls, viewBox: '0 0 40 40', 'aria-hidden': 'true' },
    PATHS[name].map(([tag, attrs]) => s(tag, attrs)));
}

const TIME = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
export const localTime = (iso) => TIME.format(new Date(iso));

export function costText([lo, hi]) {
  if (hi === 0) return 'Free';
  return lo === hi ? `$${lo}` : `$${lo}-${hi}`;
}

export const EFFORT_TEXT = { minutes: 'Minutes', hour: 'About an hour', pro: 'Hire a pro' };
