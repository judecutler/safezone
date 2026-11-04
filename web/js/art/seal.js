import { s } from '../dom.js';

// A hanko-style seal for a saved, mapped place: a rounded square with a thin border and its text set vertically.
// Up to three characters read top to bottom; longer text is cut, so pass a short mark such as 備 or 済.
export function placeSeal(text, cls = 'seal') {
  const chars = [...text].slice(0, 3);
  const size = chars.length === 1 ? 22 : chars.length === 2 ? 15 : 10.5;
  const top = 20 - (size * 1.08 * (chars.length - 1)) / 2;
  return s('svg', { class: cls, viewBox: '0 0 40 40', role: 'img', 'aria-label': `Seal: ${text}` },
    s('rect', { x: 2, y: 2, width: 36, height: 36, rx: 7, class: 'seal-outer' }),
    s('rect', { x: 5, y: 5, width: 30, height: 30, rx: 4.5, class: 'seal-inner' }),
    s('text', { class: 'seal-text', 'font-size': size, 'text-anchor': 'middle', lang: 'ja' },
      chars.map((c, i) => s('tspan', { x: 20, y: top + i * size * 1.08, dy: '0.36em' }, c))));
}
