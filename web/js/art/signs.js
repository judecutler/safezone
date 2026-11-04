import { s } from '../dom.js';

// Original drawings in the style of Japanese public safety signage, on a 40 x 40 grid.

// Tsunami caution: a yellow triangle with a heavy black border and a black breaking wave.
export function tsunamiSign(cls = 'sign') {
  return s('svg', { class: `${cls} sign-tsunami`, viewBox: '0 0 40 40', role: 'img', 'aria-label': 'Tsunami caution sign' },
    s('path', { d: 'M20 3.5 L37.5 34.5 H2.5 Z', class: 'sign-tri' }),
    s('path', { class: 'sign-wave', d: 'M8.5 30.5 C11 24 15.5 19.5 21.5 18.5 C25.5 18 28.5 20.5 28 23.5 C27.6 25.8 25 26.5 23.6 25.2 '
      + 'C22.6 24.2 23.2 22.6 24.6 22.6 C23 21 19.5 21.6 17.5 24 C16 25.8 15.4 28.2 15.6 30.5 Z' }),
    s('path', { class: 'sign-wave', d: 'M17.5 30.5 H31.5 C30 29.2 28.4 28.6 26.5 28.8 C24 29 21.5 29.6 17.5 30.5 Z' }));
}

// The figure and slope of an evacuation site sign, white on the sign's green, for embedding in other drawings.
export function evacMarks() {
  return s('g', { class: 'sign-evac-marks' },
    s('rect', { x: 1.5, y: 1.5, width: 37, height: 37, rx: 5, class: 'sign-green' }),
    s('path', { d: 'M5 35 L35 9 V35 Z', class: 'sign-white' }),
    s('path', { d: 'M5 35 C7 31 9.5 29.5 12.5 30 C11 31 10.6 32.5 11.5 33.5', class: 'sign-wave-line' }),
    s('circle', { cx: 21.5, cy: 8.5, r: 3, class: 'sign-white' }),
    s('path', { d: 'M20.5 12.5 L17 20 L21 23.5 L19 29 M17.6 18.6 L13 21 M20.4 13 L25.5 16.5 M17 20 L12.5 25.5', class: 'sign-figure' }));
}

// Evacuation site: white on green, a figure climbing to higher ground ahead of the water.
export function evacSign(cls = 'sign') {
  return s('svg', { class: `${cls} sign-evac`, viewBox: '0 0 40 40', role: 'img', 'aria-label': 'Evacuation site sign' }, evacMarks());
}
