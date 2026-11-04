# SafeZone: context for any new session

Read this whole file first. Work in poteto mode (`pstack:poteto-mode`). Last updated Nov 3, about 11 PM PT.

## Deadline and state

- Meta Global AI Developer Hackathon. Submission deadline: **Nov 4, 9 PM ET = 6 PM PT**. Three-minute demo video, public repo, and a live URL judges use.
- Judging: Impact 30%, Meta AI tooling 25%, Demo 25%, Technical depth 20%. "Simple image analyzers" are an anti-project, so pitch the whole plan, not the photo scan.
- Repo: https://github.com/judecutler/safezone (branch `main`). The user is new to development and works on Windows in PowerShell. Give copy-paste, PowerShell-safe commands. The user allows commits and pushes.
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
- SAM 3.1 is called on `POST /responses` with `stream: true`, one noun phrase, and the image as a data URL. Records look like `<0f>0<|box;x1..y2;w;h;c|><|mask;x=0;y=0;c;data=H,W,~payload|>`. Masks arrive downscaled to at most 1024 px on the long side and are stretched over the box. Lossless masks decode only with the `meta-sam-parser` package; without it, scans draw boxes.
- Muse Spark is called on `POST /chat/completions` with `response_format: json_schema` (strict, nullable fields as `anyOf` with null) and `reasoning_effort: low`. A tiny call took 10 s on `muse-spark-1.3`.
- CGS: 1000 Great Highway (the demo address) is inside the official hazard area. DataSF rows can lack a street suffix or carry stray symbols, and San Francisco writes avenues as `AV`. OSRM foot routing works. FEMA is unverified: the user's probe hit a Windows certificate error.
- The cloud sandbox cannot reach any of these services. Live calls run on the user's machine.

## Fixtures

- `fixtures/demo/`: hand-authored SAMPLE responses, built by `python tools/demo.py samples`. `demo/plan.json` is the demo household, built from them.
- `python tools/record_fixtures.py` (on the user's machine, with the key) replaces them with real recorded responses and rebuilds the demo plan. Do this before filming.
- `fixtures/probe/`: the earlier session's first real SAM and Muse responses (Responses API, non-streaming).

## Still to do

1. User: run `tools/record_fixtures.py`, push, deploy on Vercel (`MODEL_API_KEY` in project env vars), and film from `docs/video_script.md`.
2. Optional: verify FEMA against a real response.

## Safety rules (never break)

- Never route or instruct anyone to move during shaking. The shaking screen has exactly one exit, "Shaking has stopped".
- No structural claims from a photo. Never "safe route", "guarantees" or "structural".
- Model output never becomes an instruction without a code guard. Fixes come only from `FIX_TABLE`.
- Stale or sample data is always labelled.

## Decision trail

`docs/decisions.tsv` records each fork chosen, why, and the evidence.
