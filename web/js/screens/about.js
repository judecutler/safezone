import * as api from '../api.js';
import { h, s } from '../dom.js';
import { roomOverlay } from '../overlay.js';

// "How it works": what each Meta model does, what code decides, and the real recorded output of the demo room.
// Judges who only open the link see the pipeline here; the numbers come from /api/demo, so they stay true when
// the demo is recorded again.

const REPO = 'https://github.com/judecutler/safezone';
const RELATION_TEXT = {
  in_tip_zone: 'in a tipping zone',
  under_stored_items: 'under stored items',
  near_glass: 'next to glass',
  blocks_exit: 'could block the way out',
};

let demo = null;

function pipeline() {
  const steps = [
    ['One photo', 'per room'],
    ['SAM 3.1', 'outlines 13 kinds of object'],
    ['Muse Spark', 'reads the room, strict JSON'],
    ['Code guards', 'decide spots and fixes'],
    ['Your plan', 'stored on the phone'],
  ];
  const w = 300, rowH = 50, gap = 14;
  return s('svg', { class: 'about-pipeline', viewBox: `0 0 ${w} ${steps.length * (rowH + gap) - gap}`, role: 'img',
    'aria-label': 'Photo, then SAM 3.1, then Muse Spark, then code guards, then your plan' },
  steps.map(([title, sub], i) => {
    const y = i * (rowH + gap);
    const meta = i === 1 || i === 2;
    return s('g', null,
      s('rect', { x: 1, y: y + 1, width: w - 2, height: rowH - 2, rx: 10, class: meta ? 'ap-box ap-meta' : i === 3 ? 'ap-box ap-code' : 'ap-box' }),
      s('text', { x: 16, y: y + 22, class: i === 3 ? 'ap-title ap-code-text' : 'ap-title' }, title),
      s('text', { x: 16, y: y + 39, class: i === 3 ? 'ap-sub ap-code-text' : 'ap-sub' }, sub),
      i < steps.length - 1 ? s('path', { d: `M${w / 2} ${y + rowH} v${gap}`, class: 'ap-arrow' }) : null);
  }));
}

function demoFigure(root) {
  const room = demo?.plan?.rooms?.[0];
  if (!room) return root.replaceChildren();
  const hazards = room.classified.filter((c) => c.role === 'hazard').length;
  root.replaceChildren(h('figure', { class: 'about-fig' },
    roomOverlay(room, demo.images?.[room.id]),
    h('figcaption', { class: 'fine' },
      `The demo room, recorded. ${room.models.segmenter} outlined ${room.classified.length} objects. ${room.models.classifier} flagged ${hazards} that can tip, fall or swing (numbered) and ${room.relations.length} risks between objects (dashed lines).`)));
}

// The relation quoted as Muse Spark's own words: one about stored items if the room has one.
function relationQuote(root) {
  const rels = demo?.plan?.rooms?.[0]?.relations ?? [];
  const rel = rels.find((r) => r.kind === 'under_stored_items') ?? rels[0];
  root.replaceChildren(rel ? `For example: “${rel.note}”.` : '');
}

function whyBoth() {
  const quote = h('span', { class: 'about-why-quote' });
  const col = (name, does, alone) => h('div', { class: 'about-why-col' },
    h('h3', null, name), h('p', null, does), h('p', { class: 'about-why-alone' }, alone));
  const panel = h('section', { class: 'card stack about-why', 'aria-labelledby': 'about-why-h' },
    h('h2', { id: 'about-why-h' }, 'Why both models'),
    h('div', { class: 'about-why-grid' },
      col('SAM 3.1', 'Returns each object\'s box and pixel outline. The outlines draw the overlay above.',
        'Alone: exact shapes, no judgment about what is dangerous.'),
      col('Muse Spark', h('span', null, 'Names each object\'s role and the risks between objects, and proposes a floor spot. ', quote),
        'Alone: judgment, with no reliable geometry.'),
      col('Together', 'Code tests Muse Spark\'s spot against SAM\'s object boxes: in a doorway, on or inside furniture, in a tall object\'s tip zone, below stored items, or near glass. Fixes come from a fixed table.',
        'So code can check every claim before it reaches the plan.')));
  return { panel, quote };
}

function demoFacts(root) {
  const room = demo?.plan?.rooms?.[0];
  if (!room) return;
  const labels = room.classified.map((c) => c.segment.label);
  const counts = [...new Set(labels)].map((l) => `${labels.filter((x) => x === l).length} ${l}${labels.filter((x) => x === l).length > 1 ? 's' : ''}`);
  const setAside = room.spots?.[0]?.cautions?.find((c) => c.startsWith('Muse Spark suggested'));
  const fixes = new Set(room.fixes.map((f) => f.action)).size;
  root.replaceChildren(
    h('p', { class: 'label' }, room.provenance === 'recorded' ? 'Recorded real output, demo photo' : 'Demo photo'),
    h('dl', { class: 'about-facts' },
      h('dt', null, room.models.segmenter), h('dd', null, `Found ${labels.length} objects: ${counts.join(', ')}.`),
      h('dt', null, room.models.classifier), h('dd', null,
        h('ul', { class: 'about-quotes' }, room.relations.map((r) => h('li', null, `“${r.note}” `, h('span', { class: 'fine' }, `(${RELATION_TEXT[r.kind] ?? r.kind})`))))),
      h('dt', null, 'Code'), h('dd', null, setAside ? `${setAside} ` : '', `${fixes} different fixes, each from a fixed table, never from the model.`)));
}

function section(title, ...body) {
  return h('section', { class: 'card stack' }, h('h2', null, title), ...body);
}

export function renderAbout(state, act) {
  const facts = h('div', { class: 'stack', 'aria-live': 'polite' }, h('p', { class: 'fine' }, 'Loading the demo room...'));
  const figure = h('div', { class: 'about-fig-slot' });
  const why = whyBoth();
  const fill = () => { demoFigure(figure); demoFacts(facts); relationQuote(why.quote); };
  if (demo) fill();
  else api.getDemo().then((d) => { demo = d; fill(); }, () => { facts.replaceChildren(); figure.replaceChildren(); });
  return h('div', { class: 'screen about' },
    h('header', { class: 'review-head' },
      h('button', { class: 'btn-text', onclick: () => act.go('back') }, '‹ Back'),
      h('h1', null, 'How SafeZone works'),
      h('p', null, 'Two Meta models read your home. One rule holds everywhere: the model proposes, code decides.')),
    h('main', { class: 'stack' },
      section('A photo becomes a plan', figure, pipeline(), facts),
      why.panel,
      section('The go bag',
        h('p', null, 'Muse Spark checks one photo of the open bag against Ready.gov\'s 14-item basic kit and marks each item "Seen in the photo" or "Not seen". Code drops anything off the list and removes any note that judges the kit. It never says a kit is complete.')),
      section('Official maps, checked routes',
        h('ul', { class: 'about-list' },
          h('li', null, h('strong', null, 'California: '), 'the California Geological Survey tsunami hazard map and its own mapped land, plus San Francisco\'s soft-story list.'),
          h('li', null, h('strong', null, 'Japan: '), 'the national Hazard Map Portal\'s tsunami inundation tiles and GSI\'s designated tsunami evacuation sites.'),
          h('li', null, 'Walking routes come from OpenStreetMap routing. Code checks each one: it must end on mapped land outside the hazard area, never go deeper into it, and never double back. If none passes, the plan says so.'),
          h('li', null, 'Shelters come from FEMA\'s open-shelter list, filtered for the household and ranked by walking time and room.'))),
      section('When it happens',
        h('ul', { class: 'about-list' },
          h('li', null, 'The plan lives on the phone and works with no signal.'),
          h('li', null, 'During shaking the phone says only Drop, Cover, Hold On and your spot. Nothing tells you to move.'),
          h('li', null, 'After "Shaking has stopped", it talks you out turn by turn with live GPS, and says "Turn around" if you walk back toward the water.'))),
      section('Limits',
        h('ul', { class: 'about-list' },
          h('li', null, 'A planning aid, not an official warning system. Official instructions come first.'),
          h('li', null, 'A web app can\'t wake itself; standby listens only while it is open.'),
          h('li', null, 'No structural assessment from a photo. The hazard map is a minimum: if the shaking is strong or long near the coast, go to high ground anyway.'))),
      h('p', { class: 'fine about-foot' }, 'Open source: ', h('a', { href: REPO, target: '_blank', rel: 'noopener' }, 'github.com/judecutler/safezone'))));
}
