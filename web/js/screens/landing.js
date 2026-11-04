import { h, icon } from '../dom.js';
import { neighborhood } from '../art/neighborhood.js';
import { tsunamiSign } from '../art/signs.js';

const PHASES = ['Calm', 'Shaking', 'Tsunami', 'Water going back'];

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

export function renderLanding(state, act) {
  const places = state.places?.length ?? 0;
  return h('main', { class: 'landing' },
    h('div', { class: 'landing-map' },
      neighborhood({ animate: !reducedMotion() }),
      h('div', { class: 'landing-top' },
        h('div', { class: 'landing-mark' }, icon('target', 'landing-mark-icon'), 'SafeZone'),
        h('div', { class: 'landing-phase', 'aria-hidden': 'true' },
          tsunamiSign('sign landing-phase-sign'),
          h('span', { class: 'landing-phase-words' }, PHASES.map((p, i) => h('span', { class: `landing-phase-${i}` }, p)))))),
    h('section', { class: 'landing-card card' },
      h('h1', { class: 'display' }, 'Know your way to high ground.', h('span', { class: 'jp', lang: 'ja' }, '地震・津波への備え')),
      h('p', { class: 'lede' }, 'Photograph your home once. SafeZone finds the best place to take cover in each room, then talks you out of the tsunami zone, even with no signal.'),
      h('div', { class: 'landing-actions' },
        h('button', { class: 'btn', onclick: () => act.go('begin') }, 'Map my home'),
        h('button', { class: 'btn-ghost', onclick: () => act.startDemo() }, 'Run the demo'),
        places ? h('button', { class: 'btn-text', onclick: () => act.go('open_places') },
          places === 1 ? 'My places (1)' : `My places (${places})`) : null),
      h('p', { class: 'fine' }, 'Photos and plans stay on this phone. A planning aid, not an official warning system.')));
}
