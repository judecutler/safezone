// The fixed shot list for setting up a place, in order. `vision` names the background check the
// integrator runs on the photo; `level` says whether the quality meter should ask for an upright,
// level phone (a go bag and a gas meter are often shot from above).

export const SHOTS = [
  {
    kind: 'room', title: 'Rooms', repeat: true, level: true, vision: 'scan',
    prompt: 'Take one wide photo of the whole room.',
    why: 'SAM 3.1 and Muse Spark find what could fall or tip, and the best spot to drop, cover and hold on.',
  },
  {
    kind: 'exit', title: 'The way out', repeat: false, level: true, vision: null,
    prompt: 'Photograph the way out of the building, or a posted evacuation map.',
    why: 'Your plan shows it next to the walking route, so everyone knows the first steps.',
  },
  {
    kind: 'gobag', title: 'Go bag', repeat: false, level: false, vision: 'gobag',
    prompt: 'Open your go bag and spread it out so the items show.',
    why: "Muse Spark checks it against Ready.gov's basic kit. Items out of view may still be packed.",
  },
  {
    kind: 'gas', title: 'Gas shutoff', repeat: false, level: false, vision: null,
    prompt: 'Photograph the gas meter and its shutoff valve.',
    why: 'So everyone in the household can find it fast after an earthquake.',
  },
];

const STATUS_ORDER = ['failed', 'working', 'queued', 'done', 'skipped'];

// What the step strip shows for one kind: how many photos, and the status that most needs attention.
export function stepSummary(shots, kind) {
  const mine = shots.filter((s) => s.kind === kind);
  const photos = mine.filter((s) => s.status !== 'skipped');
  const status = STATUS_ORDER.find((st) => mine.some((s) => s.status === st)) ?? 'open';
  return { photos, count: photos.length, status, failed: photos.filter((s) => s.status === 'failed') };
}

// Where to start: the first step with nothing taken or skipped; with every step answered (coming
// back from review), the last one.
export function firstOpenStep(shots) {
  const i = SHOTS.findIndex((spec) => !shots.some((s) => s.kind === spec.kind));
  return i === -1 ? SHOTS.length - 1 : i;
}
