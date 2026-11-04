# SafeZone: context for any new session

Read this whole file first. It is the handoff from the planning session. Work in poteto mode (`pstack:poteto-mode`).

## Deadline and state

- Meta Global AI Developer Hackathon. Submission deadline: **Nov 4, 9 PM ET = 6 PM PT**. Planning ended about 8:55 PM PT on Nov 3, so roughly 21 hours remain. Plan for a working demo and a recorded video well before the deadline.
- Judging: Impact 30%, Meta AI tooling 25%, Demo 25%, Technical depth 20%.
- Full plan (architecture, 9 build phases, demo script, risks, Opus/Fable split): Claude Doc "SafeZone: Hackathon Project Plan", https://claude.ai/artifact/8wgiT9rKVhsTxirachBhrJ. A PDF copy is in the Claude Project "Meta Global Developer Hackathon". Read it for detail; this file is the summary.
- Repo: https://github.com/judecutler/safezone (branch `main`). The user is new to development and works on Windows in the VS Code terminal (PowerShell) in `C:\Users\roaan\OneDrive\Documents\CodeStuff\safezone\safezone`. Give copy-paste commands, PowerShell-safe. The user has "full permission to commit" and push.

## The product

Natural-disaster safety software for coastal (California/Japan) tsunami-prone zones. The demo is one story in two acts: calm preparation, then the emergency.

**Step 1 (required, build and finish first): Prepare**
1. Room photo scan: SAM 3.1 segments objects, Muse Spark classifies each (falls / slides / shatters, near bed or seat, safe spot), deterministic plain-Python scoring produces a safe-spot list and a fix list. Scoring is not done by the model.
2. Building profile from the address using public data: Nominatim geocode, CGS tsunami hazard zone FeatureServer point query, DataSF/Berkeley soft-story lists, Overpass for building tags. Building blueprints are NOT available by API (CA HSC 19851), so say "public flags", never "structural analysis".
3. Household needs: kids, wheelchair, medical, pets.
4. A plan page saved offline on the device (PWA: service worker, IndexedDB).

**Step 2 (optional, only after Step 1 works end to end)**
- 2a: emergency screen plus offline tsunami walking route (OSM foot routing, polygon-exit check, about 1 m/s pace).
- 2b: shelter finder using FEMA shelter data, filtered and ranked by household needs and fullness, with timestamps and a "replay" snapshot because the data is not guaranteed live.
- Stretch: floor-plan parsing.
- Facebook resource feed is roadmap only (Groups API removed in 2024, no public read API for Community Help).
- If Step 2 is not working by noon PT on Nov 4, ship Act 1 only and record the demo from that.

**Safety rules (never break)**
- Never route or instruct anyone to move during shaking. The emergency flow says drop, cover, hold first.
- Do not claim structural analysis from a photo. Tell users it is a preparedness aid, not an engineering assessment.
- Shelter and route data show their age. Never present stale data as live.

**Platform:** PWA (web), FastAPI backend, Leaflet map, Modal for deployment.

## Meta Model API (verified so far)

- Base URL `https://api.meta.ai/v1`, `POST /responses`, header `Authorization: Bearer <key>`. Key env var: `MODEL_API_KEY`. One key covers both models.
- **SAM 3.1**: model `sam-3.1`. Body: `{"model": "sam-3.1", "input": [{"type":"message","role":"user","content":[{"type":"input_text","text":"bookshelf"},{"type":"input_image","image_url":"<url or data URL>"}]}], "stream": false, "metadata": {"include_confidence":"true","mask_encoding":"one_bit"}}`. Text is ONE short noun phrase per request (no comma lists). Output is text records like `<0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=0;y=0;data=...|>`, comma-separated per match, `x2`/`y2` inclusive, `~` = lossless mask, `!` = one_bit. Docs page "Reading segmentation output" and packages `@meta-sam-parser` / `meta-sam-parser` cover decoding. Price about $2.50 per 1,000 images, so one request per object class per photo is about 2.5 cents for 10 classes.
- **Muse Spark**: `muse-spark-1.3` worked with this key (probe succeeded). `reasoning: {"effort": "low"}` keeps it cheap and fast. Override the model with `MUSE_MODEL` in `.env`.
- `.env` holds the key (gitignored). Never print, log, paste or commit it.

## API budget rules (user asked to minimize paid calls; free credits had not arrived)

- ALL Meta calls go through `safezone/meta_client.py`: disk cache in `.cache/meta/` keyed by request hash, hard lifetime cap `MAX_API_CALLS` (default 15, counted in `.cache/meta/ledger.jsonl`), `SAFEZONE_OFFLINE=1` serves cache only.
- Develop against saved fixtures, not live calls. Tests must never hit the network.
- Raise `MAX_API_CALLS` only deliberately, and only for the final demo recording and a few real checks. Tell the user before raising it.
- Known quirk: the user's ledger may contain 2 false entries from an early bug, so "used" can read 2 higher than reality.

## What exists in the repo

- `safezone/config.py` (env loading, never prints the key), `safezone/meta_client.py` (cached, budgeted client), `tests/test_meta_client.py` (7 tests, pass), `scripts/probe.py` (phase 1 probe), `.env.example`, `.gitignore`, `README.md`.
- Run tests: `python -m pytest -q`.
- The probe was run on the user's machine and both calls succeeded. The responses are saved on their machine in `fixtures/probe/sam.json` and `muse.json`. **As of this file's writing they were not yet pushed.** First action: `git pull` and check that `fixtures/probe/` exists. If not, ask the user to run `git add fixtures; git commit -m "Add probe fixtures"; git push` (confirm with `git status` that `.env` is not staged).

## Environment limits (cloud sandbox)

- The cloud sandbox cannot reach `api.meta.ai` or `gis.conservation.ca.gov` (egress proxy returns 403). Live Meta calls and the CGS tsunami layer must run on the user's machine, or the user must allow those domains in claude.ai Settings > Capabilities. Work from fixtures in the sandbox.
- Pushing to the repo from the sandbox worked for `judecutler/safezone`.
- Still unverified (phase 1 of the plan): the exact SAM mask decoding, the routing service choice, the CGS FeatureServer query shape, and Nominatim/OSM usage-policy details that were written from memory. Check these against live docs or real responses before relying on them.

## Next steps, in order

1. Pull the fixtures. Write a SAM output parser and a Muse JSON parser against the real responses, with tests that use those fixtures.
2. Room pipeline: `room/` package with Segment, Classified, SafeSpot, Fix, RoomScan types; SAM per class, Muse classification, deterministic scoring and fix list. Cache everything.
3. Building profile (`building/`): geocode, tsunami zone check, soft-story lookup. Cache the public responses as fixtures too.
4. Household needs and the offline plan page (PWA). Get Act 1 demo-able end to end before touching Step 2.
5. Step 2a, then 2b, only if Step 1 passes its gate.
6. Demo video, README, and submission write-up in the last hours.

## Model split (poteto mode)

- Opus: pipelines, parsers, bug fixing, prose, most of the building.
- Sonnet: bounded worker tasks.
- Fable: safety-critical review only: route correctness, the "never move during shaking" invariant, the shelter filter and ranking, the classifier prompt, and a final pre-submission review.
- Poteto principles to hold: validate at boundaries and keep logic in pure functions, never let concurrent workers write the same file, and prove it works by running the real thing.

## Working style for this user

- Plain language, short, exact commands. Do not ask the user to decide things you can decide. Commit and push working increments. Report what runs and what is unverified, not what you hoped.
