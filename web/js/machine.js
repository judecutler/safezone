// Every screen and the events that leave it. An event a screen does not list is a bug, so `next` throws.
export const TRANSITIONS = {
  landing: { begin: 'permissions', demo: 'permissions', open_places: 'places' },
  permissions: { done: 'capture', back: 'landing' },
  capture: { done: 'review', back: 'permissions' },
  review: { save: 'places', back: 'capture' },
  places: { new_place: 'permissions', open_place: 'place', simulate: 'shaking' },
  place: { back: 'places', add_shots: 'capture' },
  shaking: { stopped: 'after' },
  after: { shelters: 'shelters' },
  shelters: { back: 'after' },
};

export const EMERGENCY_SCREENS = new Set(['shaking', 'after', 'shelters']);
export const SETUP_SCREENS = new Set(['permissions', 'capture', 'review']);

export function next(screen, event, { hasPlaces }) {
  if (event === 'emergency') return 'shaking';
  if (event === 'exit_emergency') return hasPlaces ? 'places' : 'landing';
  const to = TRANSITIONS[screen]?.[event];
  if (!to) throw new Error(`no transition from ${screen} on ${event}`);
  return to;
}

export function initialScreen(search, { hasPlaces }) {
  if (new URLSearchParams(search).get('screen') === 'emergency') return 'shaking';
  return hasPlaces ? 'places' : 'landing';
}
