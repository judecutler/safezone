// Every screen and the events that leave it. An event a screen does not list is a bug, so `next` throws.
export const TRANSITIONS = {
  start: { begin: 'address', open_plan: 'plan' },
  address: { found: 'household', back: 'start', cancel: 'plan' },
  household: { next: 'rooms', back: 'address', cancel: 'plan' },
  rooms: { built: 'plan', back: 'household', cancel: 'plan' },
  plan: { edit_address: 'address', edit_household: 'household', add_room: 'rooms', reset: 'start' },
  shaking: { stopped: 'after' },
  after: { shelters: 'shelters' },
  shelters: { back: 'after' },
};

export const EMERGENCY_SCREENS = new Set(['shaking', 'after', 'shelters']);

export function next(screen, event, { hasPlan }) {
  if (event === 'emergency') return 'shaking';
  if (event === 'exit_emergency') return hasPlan ? 'plan' : 'start';
  const to = TRANSITIONS[screen]?.[event];
  if (!to) throw new Error(`no transition from ${screen} on ${event}`);
  return to;
}

export function initialScreen(search, { hasPlan }) {
  if (new URLSearchParams(search).get('screen') === 'emergency') return 'shaking';
  return hasPlan ? 'plan' : 'start';
}
