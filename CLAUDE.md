# SafeZone: context for any new session

Read this whole file first. Work in poteto mode (`pstack:poteto-mode`). Last updated Nov 3, about 11:25 PM PT.

## Deadline and state

- Meta Global AI Developer Hackathon. Submission deadline: **Nov 4, 9 PM ET = 6 PM PT**. Three-minute demo video, public repo, and a live URL judges use.
- Judging: Impact 30%, Meta AI tooling 25%, Demo 25%, Technical depth 20%. "Simple image analyzers" are an anti-project, so pitch the whole plan, not the photo scan.
- Repo: https://github.com/judecutler/safezone (branch `main`). The user is new to development and works on Windows in PowerShell, Python 3.12, in `C:\Users\roaan\OneDrive\Documents\CodeStuff\safezone\safezone`. The folder is inside OneDrive, which can lock folders: git may ask "Deletion of directory ... failed. Should I try again?"; answer n. Give copy-paste, PowerShell-safe commands. The user allows commits and pushes.
- The cloud sandbox has push access to the repo (attached via add_repo); a working clone may need `git clone https://github.com/judecutler/safezone`.
- There is no API call budget. Ignore any earlier note about `MAX_API_CALLS`.

## What is built (all of it works end to end on saved responses)

- `safezone/`: four pipelines and a Starlette server. FastAPI is not used.
  - `room/`: SAM 3.1 (13 phrases, one request each) feeds one Muse Spark call with a strict JSON schema. The model returns roles, spatial relations (tip zone, under stored items, near glass, blocks exit), a proposed floor spot and an exit note. Deterministic code in `room/score.py` ranks spots, guards the floor spot, and builds fixes from a fixed table in `rules.py`.
  - `building/`: Nominatim, the CGS tsunami hazard layer (hazard polygons plus the map's own "outside" land polygons), DataSF soft-story (San Francisco only), and Overpass.
  - `route/`: OSRM foot routes to candidates on mapped land, with checks in code: the route ends on land, never goes deeper into the zone, doesn't double back, and doesn't wander along the shore. It falls back to a direction toward proven land, then to "no checked route".
  - `shelter/`: FEMA Open Shelters, filtered fail-closed (not open, in the hazard area, failed hazard check, not wheelchair accessible), ranked by walking time, then fullness.
- `safezone/transport.py`: one boundary for every outside call. Live, recording and replay transports. Every value carries provenance (`live`, `recorded`, `sample`), and the UI labels sample data.
- `safezone/rules.py`: every piece of safety wording, with sources (Ready.gov, ShakeOut, CGS, PG&E).
- `web/`: vanilla JS PWA. Line-art white, black and red. Prepare flow, plan page, a two-page print fridge sheet, and a dark emergency mode that reads only IndexedDB. The service worker is versioned in `web/sw.js`; bump `VERSION` when web files change.
- `index.py` and `vercel.json`: the Vercel entry point. `modal_app.py` also exists.
- Tests: `python -m pytest -q` (142), `node --test web/tests/*.test.mjs`, and `node tools/verify_e2e.cjs <outdir> <base-url>` (drives every flow in a phone-sized Chromium against a running server).

## Real API facts (checked against real responses on Nov 3)

- Key env var `MODEL_API_KEY` (`META_API_KEY` also works). Base `https://api.meta.ai/v1`.
- SAM 3.1 is called on `POST /responses` with `stream: true`, one noun phrase, and the image as a data URL. Records look like `<0f>0<|box;x1..y2;w;h;c|><|mask;x=0;y=0;c;data=H,W,~payload|>`. Masks arrive downscaled to at most 1024 px on the long side and are stretched over the box. Lossless masks decode only with the `meta-sam-parser` package (in requirements.txt). Its `decode_mask_to_raster` returns row-major bytes (H x W of 0/1); `segment._raster_array` reshapes them. Any decode failure falls back to the box.
- On the demo photo, real SAM found: wardrobes (one box spans the left and middle wardrobe), both beds, the boxes on the shelf, and several "door" hits that include wardrobe doors. It found no wire shelf ("bookshelf") and no ceiling light.
- Models the key can call: muse-image-1.0, muse-spark-1.1, 1.2, 1.2-contributor, 1.3, 1.3-contributor, muse-voice-transcribe-1.0, muse-wonder-1.0, sam-3.1.
- Muse Spark is called on `POST /chat/completions` with `response_format: json_schema` (strict, nullable fields as `anyOf` with null) and `reasoning_effort: low`. A tiny call took 10 s on `muse-spark-1.3`.
- Overpass's main instance often answers 502 at capacity; `building/osm.py` falls back to `overpass.private.coffee`.
- CGS: 1000 Great Highway (the demo address) is inside the official hazard area. Real CGS polygons near it: 24 hazard polygons (18k vertices) and 19 land polygons (17k vertices); the route checks run on them in about 2 s. DataSF rows can lack a street suffix or carry stray symbols, and San Francisco writes avenues as `AV`. OSRM foot routing works. FEMA is unverified: the user's probe hit a Windows certificate error.
- The cloud sandbox cannot reach any of these services. Live calls run on the user's machine.

## Fixtures

- `fixtures/demo/`: hand-authored SAMPLE responses, built by `python tools/demo.py samples`. `demo/plan.json` is the demo household, built from them.
- `python tools/record_fixtures.py` (on the user's machine, with the key) replaces them with real recorded responses and rebuilds the demo plan. Do this before filming. It records into a fresh `fixtures/demo.recording-<time>/` folder (gitignored), prints every failed call with its status and body, prints the room notes (which include the Muse Spark error if classification failed), falls back to labelled SAMPLE shelters if FEMA fails, and then copies the files into `fixtures/demo/`.
- `fixtures/probe/`: the earlier session's first real SAM and Muse responses (Responses API, non-streaming).

## Still to do (state at handoff)

1. Recording real fixtures. Attempt 1 (commit d955d89) stopped after SAM; Muse Spark, OSRM and FEMA calls failed without saying why. Attempt 2 crashed decoding a real SAM mask (fixed in 0774842) and Overpass returned 502 (mirror added). Attempt 3 was copied before it finished (no 'failed calls' line); the recorder now prints one line per call so a long wait is visible. Attempt 4 is pending. Next: user runs `git pull` then `python tools/record_fixtures.py` and pastes the output. If it shows failed calls, fix each from the printed status and body. Unknowns it will answer: whether the Muse Spark classification call (180 s timeout, strict schema in `room/classify.py`) succeeds, whether OSRM foot routes succeed from the user's machine, and whether FEMA is reachable (it hit a Windows certificate error in the probe; certifi is current).
2. After a clean recording: the user commits and pushes `fixtures/demo` and `demo/plan.json`. Check the demo plan in the browser (`node tools/verify_e2e.cjs`) because real SAM and Muse output will change the room screen, then review the screenshots.
3. Deploy on Vercel: import the repo at vercel.com/new, add `MODEL_API_KEY`. Not yet done.
4. Film from `docs/video_script.md` (2:45, limit 3:00). Update the script lines about the room if the real Muse Spark output differs from the sample. Submit by Nov 4, 6 PM PT.
5. Optional: `room.jpg` at the repo root is the user's dorm photo added by mistake; the demo uses `demo/living_room.jpg`. Offer to remove it.

## Safety rules (never break)

- Never route or instruct anyone to move during shaking. The shaking screen has exactly one exit, "Shaking has stopped".
- No structural claims from a photo. Never "safe route", "guarantees" or "structural".
- Model output never becomes an instruction without a code guard. Fixes come only from `FIX_TABLE`.
- Stale or sample data is always labelled.

## Decision trail

`docs/decisions.tsv` records each fork chosen, why, and the evidence.
