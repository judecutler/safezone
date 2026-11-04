import { h, icon } from '../dom.js';
import { debris, neighborhood } from '../art/neighborhood.js';
import { tsunamiSign } from '../art/signs.js';

const SOURCE = 'https://dev.berkeleyca.gov/sites/default/files/documents/2025-04-18%20%202024%20Tsunami%20Warning%20-%20After%20Action%20Report%20and%20Community%20Survey%20Summary.pdf';

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

export function renderLanding(state, act) {
  const places = state.places?.length ?? 0;
  const animate = !reducedMotion();
  const map = neighborhood({ animate });
  const words = h('span', { class: 'landing-phase-words' }, 'Calm');
  const pill = h('div', { class: 'landing-phase', 'aria-hidden': 'true', 'data-level': '0' }, tsunamiSign('sign landing-phase-sign'), words);
  return h('main', { class: 'landing' },
    h('div', { class: 'landing-map' },
      map,
      animate ? debris(map, (label, level) => { words.textContent = label; pill.dataset.level = level; }) : null,
      h('div', { class: 'landing-top' },
        h('div', { class: 'landing-mark' }, icon('mark', 'landing-mark-icon'), 'SafeZone'),
        pill)),
    h('section', { class: 'landing-card card' },
      h('h1', { class: 'display' }, 'Know your way to high ground.', h('span', { class: 'jp', lang: 'ja' }, '地震・津波への備え')),
      h('p', { class: 'lede' }, 'Photograph your home once. SafeZone finds the best place to take cover in each room, then talks you out of the tsunami zone, even with no signal.'),
      h('p', { class: 'landing-fact' },
        'Dec 5, 2024: about 5 million people in Northern California and Oregon got a tsunami warning. A city survey found people didn\'t know if they were in the zone. ',
        h('a', { href: SOURCE, target: '_blank', rel: 'noopener' }, 'Source')),
      h('div', { class: 'landing-actions' },
        h('button', { class: 'btn', onclick: () => act.go('begin') }, 'Map my home'),
        h('button', { class: 'btn-ghost', onclick: () => act.startDemo() }, 'Run the demo'),
        places ? h('button', { class: 'btn-text', onclick: () => act.go('open_places') },
          places === 1 ? 'My places (1)' : `My places (${places})`) : null,
        h('button', { class: 'btn-text', onclick: () => act.go('about') }, 'How it works')),
      h('p', { class: 'landing-built' }, 'Built with ', h('strong', {}, 'Meta SAM 3.1'), ' and ', h('strong', {}, 'Muse Spark'),
        '. The demo takes 2 minutes and asks for no permissions.'),
      h('p', { class: 'fine' }, 'Photos and plans stay on this phone. A planning aid, not an official warning system.')));
}
