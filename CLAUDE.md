# SafeZone: context for any new session

Read this whole file first. Work in poteto mode (`pstack:poteto-mode`). Last updated Nov 4, about 3:45 PM PT. Credit name: Jude Cutler (in README).

## Deadline and state

- Meta Global AI Developer Hackathon. Submission deadline: **Nov 4, 9 PM ET = 6 PM PT**. Three-minute demo video, public repo, and a live URL judges use. The user films around 2 PM PT.
- Judging: Impact 30%, Meta AI tooling 25%, Demo 25%, Technical depth 20%. "Simple image analyzers" are an anti-project, so pitch the whole plan, not the photo scan.
- Repo: https://github.com/judecutler/safezone. The user is new to development and works on Windows in PowerShell, Python 3.12, in `C:\Users\roaan\OneDrive\Documents\CodeStuff\safezone\safezone`. The folder is inside OneDrive, which can lock folders: git may ask "Deletion of directory ... failed. Should I try again?"; answer n. Give short copy-paste, PowerShell-safe commands. The user allows commits and pushes.
- Branches: `main` is the live app (Vercel redeploys on every push to main: https://safezone-alpha-one.vercel.app/, `MODEL_API_KEY` set). `redesign` holds the new app built overnight. The user approved merging `redesign` into `main` once every test, the full browser check and the independent safety review pass. In this sandbox the clone is shallow; `git config --add remote.origin.fetch '+refs/heads/redesign:refs/remotes/origin/redesign'` lets `git status` track it.
- The cloud sandbox cannot reach the Meta API, any data service or the Vercel URL. Live calls and recordings run on the user's machine. The user's Chrome (Claude in Chrome) can drive the live site; never play the emergency voice there without asking, it speaks out loud on their computer.

## What the app is (redesign branch)

- Landing: a top-down line-art coastal neighborhood (seeded, procedural SVG) that loops calm, shaking, tsunami, recede. Yellow accent, a yellow-to-red severity scale (red only for danger and the hanko seal), restrained Japanese elements (seigaiha water, JIS-style tsunami and evacuation-site signs, small bilingual labels). Laptop widths show a phone-width column over the art.
- Setup, camera first: one permissions screen (camera, location, iOS motion), then a guided shot list: room (repeatable), the way out, go bag, gas shutoff. Live quality meter (light, sharpness, steadiness, level). Skip and Back everywhere. The location lookup (GPS, then typed address as fallback) and every photo check run in the background. Review screen, then save as a mapped place.
- Vision: rooms use SAM 3.1 (13 phrases, all at once) then one Muse Spark call with a strict JSON schema; code in `room/score.py` decides spots and fixes. The go bag uses one Muse Spark call over Ready.gov's fixed 14-item list; it reports "Seen in the photo" or "Not seen" and never judges the kit. Way-out and gas photos are saved for offline reference, no model call.
- Places and standby: saved places, nearest one by GPS, standby listens for sustained shaking (devicemotion) while the app is open.
- Emergency, voice led: shaking says only "Drop, cover and hold on" plus the saved spot, repeated every 15 s; taps in the first 3 s are ignored; the only way forward is "Shaking has stopped". After: the go-now line, then spoken turn-by-turn from GPS (`web/js/guide.js`), with wake lock and a mute toggle. Demo mode says "This is a demo" and simulates the walker.
- Regions (`safezone/regions.py`): `us-ca` (the original pipelines: Nominatim, CGS tsunami hazard and land polygons, DataSF soft-story, Overpass, OSRM, FEMA shelters) and `jp` (Hazard Map Portal tsunami inundation tiles, GSI designated tsunami evacuation sites, Cabinet Office and JMA guidance quoted in Japanese with English). A point outside both gets `no_coverage`. Add a city per `docs/regions.md`.
- Real map (`web/js/livemap.js`, contract `docs/livemap.md`): Leaflet 1.9.4 vendored in `web/vendor/leaflet/`, OpenStreetMap tiles greyed with CSS and cached by the service worker as viewed (CARTO's free tiles now stamp "API key required"), CGS hazard polygons (US) or the Hazard Map Portal raster (Japan), numbered turns, a "Leaving the hazard area" marker, walker callout, legend with sources. Overlays draw with no tiles, so the emergency map works offline. Used on saved places, review, the emergency after screen, and the desktop setup panel.
- Desktop setup (1024 px and up): live map on the left reveals findings as the background jobs finish (`web/js/screens/setupmap.js`); the form is on the right. The demo shows a visible "Finding your location…" step and offers "Use my real location instead".
- "How it works" (`web/js/screens/about.js`): the Meta model pipeline with the demo room's recorded output, for judges.
- Demo: "Run the demo" on the landing page. It walks the real setup on `demo/living_room.jpg` with recorded data, saves "Demo: Ocean Beach" and adds "Demo: Kamakura", then "Simulate an earthquake" runs the voice-led emergency. "Exit demo" removes the demo places.

## Real API facts (checked against real responses on Nov 3)

- Key env var `MODEL_API_KEY` (`META_API_KEY` also works). Base `https://api.meta.ai/v1`.
- SAM 3.1 is called on `POST /responses` with `stream: true`, one noun phrase, and the image as a data URL. Records look like `<0f>0<|box;x1..y2;w;h;c|><|mask;x=0;y=0;c;data=H,W,~payload|>`. Masks arrive downscaled to at most 1024 px on the long side. Lossless masks decode only with the `meta-sam-parser` package (in requirements.txt). Any decode failure falls back to the box. A scan where SAM never answers is a 502, not an empty room.
- On the demo photo, real SAM found the wardrobes, both beds, the boxes on the shelf, and "door" hits that are wardrobe doors (named "cabinet door" in the UI).
- Models the key can call: muse-image-1.0, muse-spark-1.1, 1.2, 1.2-contributor, 1.3, 1.3-contributor, muse-voice-transcribe-1.0, muse-wonder-1.0, sam-3.1.
- Muse Spark is called on `POST /chat/completions` with `response_format: json_schema` (strict, nullable fields as `anyOf` with null) and `reasoning_effort: low`.
- Overpass often answers 502 or times out; `building/osm.py` tries three instances within one 10 s budget (180 s in the recorders).
- CGS: 1000 Great Highway (the demo address) is inside the hazard area. FEMA listed 0 open shelters on Nov 3, so the demo shows labelled SAMPLE shelters.
- Japan: Tokyo's own inundation study maps only its islands, so the 23 wards have no mapped tsunami inundation. The Japan demo place is Kamakura City Hall. Tile URL, zoom and legend colours are verified; GSI site field names are not (the recording will show them).

## Live site facts (checked in the user's Chrome, Nov 4, 9:30 AM)

- `main` is live with the redesign. A real room scan through Vercel (SAM 3.1 and Muse Spark with the user's key) took 49 s, decoded real mask outlines, and returned the same relations as the recording. A real route matched the recording, including "Walk to the nearby path". FEMA still lists 0 open shelters.
- The address lookup took 56 s because Overpass timed out on every instance from Vercel. Overpass now has one 10 s budget across instances (recorders raise it to 180 s), and the lookup takes 13 s.
- iOS Safari speaks only after speech starts inside a tap; `voice.js` speaks one silent line on the first tap.
- To test a real scan in the user's Chrome without the native file dialog, patch `HTMLInputElement.prototype.click` in the page to set `files` from `/demo/living_room.jpg` (see the session log of Nov 4).
- Merging to `main` from a clean worktree (`git worktree add /tmp/claude-0/wt <commit>`) keeps other agents' uncommitted edits out; run the browser check there first.

## Route facts (independent review, Nov 4)

- The demo route is 602 m, 10 min. It exits the zone 290 m from home, never goes more than 40 m deeper than home, and ends 100 m clear on mapped land. The two shorter eastward routes were correctly rejected (70 m seaward first).
- OSRM's opening loop around the start now reads "Walk to the nearby path" (`fold_start_loop` in `route/osrm.py`), not "Head west".
- Route checks count "off mapped land" as inside the zone and measure depth to mapped land, so walking toward the water reads as deeper.

## Fixtures and recording

- `fixtures/demo/`: real US responses recorded Nov 3 (attempt 3), plus labelled SAMPLE shelters and outside-zone address (`python tools/demo.py fill-samples`), plus Japan samples. Recorders merge into this folder; they never empty it.
- `demo/plan.json` (Ocean Beach) can only be rebuilt where `meta-sam-parser` installs (the user's machine); `tools/demo.py` refuses otherwise. `demo/gobag.json` is RECORDED (Nov 4, muse-spark-1.3, 2 of 14 seen: first aid kit, food) from `demo/gobag.jpg`. `demo/plan_jp.json` (Kamakura) is RECORDED (Nov 4) at 35.3108, 139.5426 (Yuigahama, inundation 1 m to 3 m). City Hall (35.3192, 139.5466) read `not_in_zone`, so `tools/probe_jp_zone.py` moved the point. With 12 sites checked the route is still `no_checked_route`: GSI's skhb05 tiles list zero sites in 鎌倉市 (checked in both recorded tiles); the nearest designated sites are in Zushi (1.7 km+) and every route there failed `check_route`. The card honestly says no checked route and lists the 10 nearest sites outside the inundation area (38 to 64 min). Moving the point to Zushi would give a site route; that is a new recording and was not done.
- Tests pin the recorded state: `test_the_shipped_jp_demo_matches_a_replay_of_its_recording` rebuilds `plan_jp.json` from `fixtures/demo` and compares.
- Windows: all JSON reads and writes are UTF-8 now (the Japanese text crashed `write_plan_jp` under cp1252 and left a half-written file; `git checkout -- demo/plan_jp.json` restores it).
- Go-bag photo: `demo/gobag_input.jpg` (from the project's GoBag.jpg, the handwritten phone number on the backpack painted over, EXIF removed). Record with `python tools/record_fixtures.py --gobag demo/gobag_input.jpg`; delete `demo/gobag_input.jpg` afterwards if wanted. The project also holds Bathroom.jpg, CommonRoom.jpg and room.jpg (not used; no way-out or gas-meter photo exists, so those steps stay skip-able reference steps). Never commit a photo with a visible phone number, address or face.
- On the user's machine: `python tools/record_japan.py` (no key; rebuilds `demo/plan_jp.json` when every call succeeded) and `python tools/record_fixtures.py --gobag <photo.jpg>` (writes `demo/gobag.json`). `python tools/record_fixtures.py` rerecords the US household.

## Tests

- `python -m pytest -q` (237), `node --test web/tests/*.test.mjs` (37). `test_no_app_screen_says_safest_safe_route_or_guarantee` scans every `web/js` file.
- The app reloads once when a new service worker takes over, but only on landing, places or about.
- `node tools/verify_e2e.cjs <outdir> <base-url>` (150 checks: landing, demo flow with voice log, real flow and offline, no places, migration). In the sandbox: `NODE_PATH=/opt/node22/lib/node_modules`, and run the server with `SAFEZONE_FIXTURES=fixtures/demo MODEL_API_KEY=x python -m uvicorn safezone.app:create_app --factory --port 8000`.
- After any web change run `python tools/sw_shell.py`: it rewrites the service worker's offline file list and bumps its version.

## Submission materials

- `README.md`, `docs/devpost.md`, `docs/judge_quickstart.md`: final. TODO blocks filled Nov 4 (recorded go bag and Kamakura, 237/37/150 test counts, live URL, credit Jude Cutler). The Devpost video link is the only item left, and it goes in Devpost's own field.
- `docs/story.md`: verified disaster facts with sources (Dec 5, 2024 warning was 10:44 to 11:54 AM, not at night; Berkeley after-action survey; Kamaishi; furniture injuries; preparedness). Use only facts from it.
- Demo video: the user asked for a mostly animated video instead of filming the old script. `docs/video_script.md` is now the scene and narration table of that video, with the source of every number. Build code is in `video/` (`video/README.md`): Kokoro TTS (`af_heart`, model from the kokoro-onnx GitHub release; PyPI and Hugging Face are blocked in the sandbox, so `video/tts.py` phonemizes from misaki's dictionaries), an HTML stage rendered frame by frame with Playwright, and a numpy soundtrack. The two phone clips (Jude's reaction, and the live app on his phone) are not committed: they show his face. Decided with the user: no victim photos or names, no invented benefit percentages, Meta named in text without its logo.

## Still to do (Nov 4)

1. DONE: recordings reviewed, gate rerun on a clean worktree (237 pytest, 37 node, 150/150 browser), merged to `main` (062ef68 and after), submission TODOs filled, video script Act 2 rechecked.
2. User: check the live link on a phone with sound on, film from `docs/video_script.md`, submit by 6 PM PT.
3. Not done, offered only: a map (hazard raster and site markers, no line) on the no-checked-route card; a Zushi recording that would give Japan a site route.

## Safety rules (never break)

- Never route or instruct anyone to move during shaking. The shaking screen has exactly one way forward, "Shaking has stopped".
- No structural claims from a photo. Never "safe route", "safest", "guarantees" or "structural". "Safe" appears only in the official "until officials say it is safe".
- Model output never becomes an instruction without a code guard. Room fixes come only from `FIX_TABLE`; go-bag output never judges the kit.
- Stale, sample, replay and demo data are always labelled.
- Spoken directions never point a person back toward the water: no off-route pointer once outside the hazard area, and walking the route backward gets "Turn around".

## Decision trail

`docs/decisions.tsv` records each fork chosen, why, and the evidence. `docs/redesign.md` is the contract the overnight rebuild followed.
