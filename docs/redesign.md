# SafeZone redesign contract (Nov 4, 12 AM PT)

The user's goal: a demo that feels like a real product. Calm and illustrated until something goes wrong; a quick camera-first setup in one pass; a phone that talks you through an emergency hands-free; and a demo mode that runs the whole story reliably on camera. Deadline Nov 4, 6 PM PT; filming 2 to 4 PM.

This file is the contract four workstreams build against in parallel. Each workstream owns only its files. `web/js/app.js`, `web/js/machine.js`, `web/index.html` and `web/sw.js` belong to the integrator; workstreams do not edit them and instead export what this file names.

## Rules that do not change

- `CLAUDE.md` safety rules hold: never route or instruct movement during shaking; the shaking screen's only way forward is "Shaking has stopped"; no structural claims; model output becomes an instruction only through a code guard; sample, replay and demo data are always labelled.
- Shneiderman's eight golden rules, applied: consistent layout and wording on every screen; shortcuts for repeat users (open straight to standby, one-tap demo); informative feedback for every action and every background job; each flow ends in a clear done state; prevent errors (permissions explained before the prompt, quality meter before the shutter); easy reversal (Back and Skip on every capture step, undo instead of confirm dialogs where possible); the user stays in control (nothing auto-advances without a visible countdown they can cancel, except the emergency voice); reduce memory load (show what is saved, never ask for the same thing twice).
- Accessibility: hit targets at least 48 px, text contrast AA, `prefers-reduced-motion` stops every animation, every live region uses `aria-live`.
- No new npm dependencies. Vanilla ES modules, `h()` and `s()` from `web/js/dom.js`.

## Screens and events (`web/js/machine.js`, integrator)

```
landing      begin -> permissions | demo -> permissions (state.demo = true) | open_places -> places
permissions  done -> capture | back -> landing
capture      done -> review | back -> permissions         (shot list steps live inside capture)
review       save -> places | back -> capture
places       new_place -> permissions | open_place -> place | simulate -> shaking (demo only)
place        back -> places | add_shots -> capture
shaking      stopped -> after
after        shelters -> shelters
shelters     back -> after
any          emergency -> shaking ; exit_emergency -> places if any place else landing
```

`initialScreen`: `?screen=emergency` opens shaking; otherwise `places` if any place is saved, else `landing`.

## State (`web/js/app.js`, integrator)

```js
state = {
  screen, demo: false,
  places: [Place],                 // IndexedDB kv 'places'
  activePlaceId: null,
  session: Session | null,         // the setup in progress; IndexedDB kv 'session'
  guidance, images: {id: objectURL},
  emergency: { place, guidance, images } | null,   // loaded from IndexedDB on entry
  ui: { error: null },
}
Place   = { id, name, kind: 'home'|'work'|'school'|'other', demo: bool, plan: Plan, saved_at }
Session = {
  location: { status: 'idle'|'locating'|'found'|'failed', coords?: [lon, lat], building?: BuildingProfile, error? },
  household: { children, wheelchair, medical, pets },
  shots: [Shot],
  evac: { status, route?, shelters?, shelters_error? },
}
Shot    = { id, kind: 'room'|'exit'|'gobag'|'gas', name, image_id, status: 'queued'|'working'|'done'|'failed'|'skipped',
            result?: RoomScan | GoBagCheck, error? }
```

`Plan` keeps the existing shape (`building, household, rooms, route, shelters, generated_at`) plus `extras: { exit?: image_id, gas?: image_id, gobag?: GoBagCheck }`, so the existing plan page parts keep working.

Actions the integrator provides to every screen (`act`): `go(event)`, `startLocate()`, `setPlaceName(name, kind)`, `toggleNeed(key)`, `addShot(kind, name, blob)` (stores the blob, starts the background job, returns the shot id), `retryShot(id)`, `skipShot(kind)`, `removeShot(id)`, `savePlace()`, `openPlace(id)`, `deletePlace(id)`, `toggleFix(placeId, roomId, fixId)`, `startDemo()`, `exitDemo()`, `simulateQuake()`.

## Workstreams

### A. Look and landing. Owns `web/css/tokens.css`, `web/css/base.css`, `web/css/landing.css`, `web/js/art/neighborhood.js`, `web/js/screens/landing.js`, and rewrites `web/app.css` (the existing screens' styles) to the new tokens.

- Tokens in `tokens.css` as CSS custom properties on `:root` and `[data-mode=emergency]`:
  `--paper #FBF8F1`, `--ink #17150F`, `--muted #6B655A`, `--line #17150F`, `--accent #FFC629` (primary actions, focus, the good-shot state), `--accent-ink #17150F` (text on accent), and a severity scale `--sev-1 #FFD84D` (note), `--sev-2 #FFB020` (caution), `--sev-3 #FF7A1A` (warning), `--sev-4 #E8322B` (danger), plus `--sev-gradient: linear-gradient(90deg, var(--sev-1), var(--sev-2), var(--sev-3), var(--sev-4))`. Emergency mode: `--paper #0E0D0A`, `--ink #FFF8E6`, accent unchanged. Red is only `--sev-4`, never decoration.
- Classes other workstreams use: `.btn` (primary, yellow), `.btn-ghost`, `.btn-text`, `.chip`, `.chip[aria-pressed=true]`, `.card`, `.sev-1`..`.sev-4` (text and border colour), `.tag-sample`, `.tag-demo`, `.demo-banner`, `.stack` (vertical rhythm), `.screen` (full-height mobile screen with safe-area padding), `.dock` (bottom-fixed action area).
- `neighborhood.js` exports `neighborhood({ animate: boolean }) -> SVGElement`: an original line-art coastal street (ocean at left, beach, a row of varied houses and an apartment block, trees, power poles and lines, a hill with a road rising inland at right). Thick black strokes, flat paper fills, yellow windows and sun. Loop about 14 s with CSS keyframes: calm 5 s; shaking 3 s (houses jitter, poles sway, lines bounce); a wave rises from the left and floods the low street 3 s, stopping short of the hill; it recedes 2 s; calm. Respect `prefers-reduced-motion` (static calm frame). No raster images, no external assets, under 25 KB.
- `landing.js` exports `renderLanding(state, act)`: the neighborhood fills the top two thirds; a headline and one line of what SafeZone does; primary `Map my home` (`act.go('begin')`), secondary `Run the demo` (`act.startDemo()`), and `My places` if `state.places.length`.

### B. Camera-first capture. Owns `web/js/camera.js`, `web/js/quality.js`, `web/js/shots.js`, `web/js/screens/permissions.js`, `web/js/screens/capture.js`, `web/css/capture.css`, `web/tests/quality.test.mjs`.

- `permissions.js` exports `renderPermissions(state, act)`: one screen that says why camera and location are needed, then one `Allow camera and location` button that requests the camera (`getUserMedia`), location (`act.startLocate()`), and on iOS `DeviceMotionEvent.requestPermission()` for standby shake detection, then `act.go('done')`. `Not now` continues without them (file picker fallback, typed address in review). Shows the result of each permission.
- `shots.js` exports `SHOTS`: the fixed shot list, in order: `room` (repeatable: "Add another room"), `exit` (the way out of the building, or a posted evacuation map), `gobag` (open the go bag so the items show), `gas` (the gas meter shutoff). Each: `{ kind, title, prompt, why, vision: 'scan'|'gobag'|null }`.
- `quality.js` exports pure functions, unit-tested: `frameStats(imageData) -> { luma, contrast, sharpness }` (sharpness from Laplacian variance on a downscaled grey frame), `motion(prev, cur) -> number`, `shotQuality({ luma, contrast, sharpness, motion, tiltDeg }) -> { score 0..1, ok: bool, hint: string }`. Hints, one at a time, most important first: too dark, hold still, hold the phone upright and level, blurry, then for rooms "Stand in the doorway and fit the whole room in" as a standing tip.
- `camera.js` exports `openCamera(videoEl) -> { stop(), capture() -> Blob }` using the rear camera, and a fallback when the camera is unavailable.
- `capture.js` exports `renderCapture(state, act)`: full-screen live preview; a quality ring that fills and turns yellow as the shot improves; the hint line; the shutter (enabled always, highlighted when ok); Skip and Back on every step; a step strip showing the shot list and each shot's background status (queued, working with a progress shimmer, done, failed with retry); a small status chip for the background location lookup ("Checking tsunami map for your location..."). In demo mode (`state.demo`), the preview shows the demo photo and the shutter uses it, with the `DEMO` banner. Finishing the list calls `act.go('done')`.

### C. Server and API. Owns `safezone/` (Python), `tests/`, `tools/` except `tools/verify_e2e.cjs`, and `web/js/api.js`.

- Speed: run all SAM phrase requests at once (`max_workers=len(PHRASES)`). Do not change `MAX_SIDE` or the image bytes sent: recorded fixtures are keyed by request body.
- `/api/profile?lat=..&lon=..`: Nominatim reverse geocode, then the existing profile. Same response shape. Respect Nominatim's 1 request per second.
- `/api/gobag` (POST image/jpeg): one Muse Spark call with a strict JSON schema over a fixed checklist in `rules.py` (`GO_BAG`, from Ready.gov's basic kit, each item with an id, a label and its source). The model returns, per item id, `seen: bool` and a short note; code drops unknown ids, keeps the fixed order, and the response says "Seen in the photo" or "Not seen"; it never says the kit is complete. Response `GoBagCheck = { items: [{id, label, seen, note}], seen_count, total, model, provenance }`. Tests with a sample responder; add a sample to `tools/samples` and a `--gobag <photo>` option to `tools/record_fixtures.py` so the user can record a real one.
- `/api/demo` also returns `gobag` (the sample check, labelled sample) and `extras` image urls if any.
- `api.js` adds `getProfileAt(lon, lat)` and `checkGoBag(jpeg)`.

### D. Places, standby and voice. Owns `web/js/places.js`, `web/js/voice.js`, `web/js/guide.js`, `web/js/standby.js`, `web/js/screens/places.js`, `web/js/screens/emergency.js` (rewrite), `web/css/emergency.css`, `web/tests/guide.test.mjs`.

- `places.js`: pure helpers `nearestPlace(places, [lon, lat])`, `placeFromSession(session, name, kind)`, and IndexedDB wrappers over `db.js` (`loadPlaces`, `savePlaces`).
- `voice.js`: `say(text, { interrupt })`, `repeat(text, everyMs) -> stop`, `stopAll()`; uses `speechSynthesis` with a calm rate; `vibrate(pattern)`; `keepAwake()` via the Wake Lock API with a silent fallback.
- `guide.js`: pure, unit-tested. `stepPoints(route)` places each step on the path by cumulative distance; `progress(route, [lon, lat]) -> { stepIndex, metersToNext, offRouteM, arrived }`; `cue(progress, lastCue) -> string | null` returns the next spoken line ("In 40 metres, turn right", "You are off the route. Head back toward it.", "You are outside the hazard area. Stay there until officials say it is safe.") without repeating itself.
- `standby.js`: while the places screen is open, listen to `devicemotion`; sustained strong shaking (for example 2 s above a threshold) calls `act.go('emergency')`. A demo `simulateQuake()` triggers the same path and shakes the screen with CSS.
- `screens/places.js` exports `renderPlaces(state, act)` and `renderPlace(state, act)`: a standby header ("Standing by" with a calm pulse, the nearest place, last updated), the list of mapped places with their tsunami flag colour on the severity scale, `Map a new place`, and in demo mode `Simulate an earthquake`. `renderPlace` reuses `roomResult`, `flagList`, `routeView`, `shelterSection` from the existing `prepare.js` and `parts.js` and shows the extra photos and the go bag check.
- `screens/emergency.js` exports `renderEmergency(state, act)`: shaking says aloud, and repeats every 15 s, "Drop, cover and hold on" with the nearest place's first safe-spot instruction; the whole screen is the "Shaking has stopped" button; screen stays awake. After: speaks the go-now line once when in the zone, then spoken turn-by-turn from `guide.js` with live GPS; in demo mode a simulated walker moves along the route at 1.4 m/s. A visible mute toggle. Shelters screen as before.

## Integration (after A to D)

The integrator rewrites `app.js` and `machine.js`, links the CSS files in `index.html`, bumps `sw.js` `VERSION` and its precache list, migrates a saved single plan into `places`, rewrites `tools/verify_e2e.cjs` for the new flow, and runs every test plus the browser check.
