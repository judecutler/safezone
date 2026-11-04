<!--
TODO after tomorrow's recording:
- Go-bag check: if `python tools/record_fixtures.py --gobag <photo>` succeeds, change "the demo's go-bag result is labelled sample data" (What it does) to "the demo's go-bag result is a recorded Muse Spark answer".
- Kamakura: if `python tools/record_japan.py` succeeds and demo/plan_jp.json is rebuilt, change "Kamakura runs on labelled sample data until it is recorded" (What it does, Accomplishments) to "recorded real data".
- Video link: add it to the Devpost video field.
-->

# SafeZone: Devpost text

Paste each section into the Devpost field with the same name.

## Project name

SafeZone

## Tagline

Prepare once. In a quake, your phone talks you out.

(51 characters.)

## Elevator pitch (one sentence)

SafeZone turns a few phone photos and an address into a household earthquake and tsunami plan that lives on the phone and, when the shaking stops, speaks you along a checked walking route out of the official hazard area.

## Elevator pitch (three sentences)

On Dec 5, 2024, about 5 million people got a tsunami warning that did not say who was in the zone, and Berkeley's survey of 1,602 residents found people did not know where the zone was. SafeZone fixes that before the day: SAM 3.1 and Muse Spark read each room and the go bag, official hazard maps place the home, and code checks a walking route out of the zone and shelters that fit the household. When the quake comes, the phone says Drop, Cover, Hold On, and when the shaking stops it talks you along the saved route with live GPS, even with no signal.

## Inspiration

On Thursday, Dec 5, 2024, at 10:44 a.m., a magnitude 7.0 earthquake struck off Cape Mendocino. Phones across the Bay Area buzzed with a tsunami warning for about 5 million people ([KQED](https://www.kqed.org/news/12032295)). The warning lasted 70 minutes. Berkeley's after-action survey drew 1,602 responses. People did not know where the inundation zone was, some evacuated from outside it, and the phone alert had no zone details ([Berkeley report](https://dev.berkeleyca.gov/sites/default/files/documents/2025-04-18%20%202024%20Tsunami%20Warning%20-%20After%20Action%20Report%20and%20Community%20Survey%20Summary.pdf)). San Francisco's sirens had been off since 2019, and many people walked to the waterfront to watch ([KTVU](https://www.ktvu.com/news/tsunami-warning-san-francisco-start-time-earthquake)).

Japan shows what preparation does. In Kamaishi in 2011, after years of school drills, nearly all of the city's roughly 3,000 schoolchildren reached high ground ([Government of Japan](https://www.atlanta.us.emb-japan.go.jp/hts5.html)). The work was done long before the day it was needed. Kamaishi also teaches the limit of a map: at Unosumai, 86% of the dead were in homes outside the mapped hazard area ([EERI report](https://kamome.humboldt.edu/sites/default/files/Japan-eq-report-tsunami_dengler.pdf)).

Most people never do that preparation. Only 35% of Californian adults say they are prepared for a disaster ([PPIC, 2024](https://www.ppic.org/blog/few-californians-are-prepared-for-a-disaster/)). In Japan, 35.9% have secured their furniture and 34.5% have chosen an evacuation site and route ([Cabinet Office, 2022](https://survey.gov-online.go.jp/r04/r04-bousai/gairyaku.pdf)). Furniture matters, because in Japanese earthquakes since 2003, 30% to 50% of injuries came from furniture tipping, falling or sliding ([Tokyo Fire Department](https://www.tfd.metro.tokyo.lg.jp/content/000010472.pdf)).

We wanted the preparation to take minutes, and the plan to run itself when nobody can think.

## What it does

SafeZone is a household plan in two acts. It is not a photo analyzer. The photo scan is one of five parts of the plan.

**Act 1. Prepare once.** A camera-first setup walks you through a short shot list with a live quality meter, and Skip and Back on every step.

- **Rooms.** SAM 3.1 outlines the furniture and objects that matter. Muse Spark reasons about the room: which objects can tip or fall, which bed is in a wardrobe's tip zone, what is stored above a bed, and what could block the way to the door. Code picks the best place to take cover and builds a fix list from a fixed table ("Strap it to a wall stud", "Move heavy or breakable items down low").
- **Go bag.** Muse Spark checks a photo of the open bag against Ready.gov's 14-item basic kit and reports each item as "Seen in the photo" or "Not seen". It never says the kit is complete. The demo's go-bag result is labelled sample data.
- **The way out and the gas shutoff.** These photos are saved with the plan, so everyone in the household can find them.
- **Building and route.** From the address or the phone's location, SafeZone checks the official tsunami hazard map. In the hazard area, it computes a walking route out and checks it in code before it is shown.
- **Shelters.** In California, it lists FEMA open shelters that fit the household (wheelchair access, outside the hazard area), ranked by walking time and how full they are. In Japan, it lists designated tsunami evacuation sites.

The plan is saved on the phone, prints as a two-page fridge sheet, and can cover several places, such as home and work.

**Act 2. The phone talks you through it.** While the places screen is open, SafeZone listens for sustained strong shaking with the motion sensor, or you tap Emergency.

- During shaking, the screen and the voice say Drop, Cover, Hold On, with your room's saved spot, and repeat it every 15 seconds. Nothing tells you to move.
- When you tap "Shaking has stopped" in the hazard area, the voice says to go now, on foot, without waiting for an official warning. Then it gives turn-by-turn directions along the saved route from live GPS, and warns you if you leave the route.
- The route map is drawn from stored data without map tiles, so it works offline.

Two regions work today. The San Francisco demo (1000 Great Highway, inside the official CGS hazard area) runs on real responses recorded from every service, except the shelters, which are labelled sample data because FEMA listed no open shelters that day. Kamakura, Japan, runs on labelled sample data until it is recorded.

## How we built it

**Meta models.** We use two Meta models through the Meta Model API.

- **SAM 3.1** segments each room photo. We send 13 noun phrases (table, desk, bookshelf, cabinet, wardrobe, window, glass door, mirror, ceiling light, TV, bed, box, door) as 13 parallel streaming requests to the Responses endpoint. We decode each mask with `meta-sam-parser`, and draw the outlines over the photo. If a mask fails to decode, we fall back to its box.
- **Muse Spark** (`muse-spark-1.3`) runs on the Chat Completions endpoint with a strict JSON schema and `reasoning_effort: low`. We make two kinds of call.
  - **Room reasoning.** The model gets the photo, the safety rule set from `rules.py` and SAM's segment list. It returns a role and hazard kind per segment, typed spatial relations (in the tip zone, under stored items, near glass, blocks the exit), a proposed open-floor spot and a note about the way to the door.
  - **Go-bag check.** The model gets the photo and the 14 Ready.gov item ids as an enum, and returns whether each item is visible, with a short note.

**Code guards.** The model proposes, and code decides. Answers that name unknown segments are dropped. The floor spot is rejected if it is in a doorway, inside furniture, off the floor, in a tip zone, under stored items or near glass, and these checks go by what the object is, so the model cannot switch them off by calling a wardrobe "neutral". Fix text comes only from a fixed table. Go-bag notes that judge the kit ("complete", "enough", "ready") are removed.

**Official data.** California uses the California Geological Survey tsunami hazard layer (the hazard polygons and the map's own land polygons outside them), DataSF's soft-story list, Nominatim, Overpass, OSRM foot routing and FEMA Open Shelters. Japan uses the Hazard Map Portal inundation tiles with MLIT depth classes and GSI's designated tsunami evacuation sites. A region registry lets a new city be one set of adapters.

**Route checks.** Each OSRM route is sampled along its length against the hazard polygons. It must end on the map's own land outside the zone, never go deeper into the zone than home, not double back, not re-enter the zone and not wander along the shore. If no route passes, the plan gives a compass direction toward proven land, then "could not check a route" with the official fallback. Walking time uses 1.0 m/s, for children and older adults.

**One boundary for every outside call.** `transport.py` runs live, records or replays. The whole pipeline runs offline from recorded responses, every value carries its provenance (live, recorded or sample), and the app labels sample data.

**Stack.** Python 3.12 and Starlette on the server, deployed on Vercel. A vanilla JavaScript PWA with no build step, IndexedDB for plans and photos, a service worker for offline use, the Web Speech API for the voice, the Wake Lock API, DeviceMotion for standby and the Geolocation API for turn-by-turn. We built it with Claude Code.

## Challenges we ran into

- **SAM 3.1's streaming mask format.** Records arrive as `<|box;...|><|mask;...;data=H,W,~payload|>`, and masks come downscaled to at most 1024 px and stretched over their box. Our second real recording crashed decoding a real mask, because `meta-sam-parser` returns row-major bytes. We fixed the reshape, added a test on a real mask, and made any decode failure fall back to the box.
- **Strict JSON schema.** Muse Spark's strict mode needs nullable fields written as `anyOf` with null. We kept every model answer in a schema and validated it again with Pydantic, so a malformed answer degrades to "labels only" and never reaches an instruction.
- **Silent failures in recording.** Our first real recording stopped after SAM, and the Muse Spark, OSRM and FEMA calls failed without saying why. We rebuilt the recorder to print one line per call and every failed call with its status and body.
- **Overpass timeouts.** The main Overpass server often answered 502 or timed out. We added a 60-second timeout and two mirrors. On our final recording all three still timed out, so the demo building has no storeys flag, and the app does not claim one.
- **FEMA's empty layer on a quiet day.** The real FEMA answer listed 0 open shelters, which is correct on a day with no disaster but leaves the emergency's last screen empty. We kept the real filters and filled the demo with clearly labelled sample shelters instead of hiding the gap.
- **The model saw a door that was a wardrobe door.** SAM's "door" phrase also matched wardrobe doors, so "stay clear of the door" read like "stay away from the exit". The text now names it "cabinet door".
- **A reviewer broke our first route check.** Where a hazard polygon stops at the shore, "outside the hazard area" includes the ocean. We changed the rule so a route must end on the map's own land outside the zone, and fail closed when no land is proven.
- **Tokyo's 23 wards have no mapped inundation.** Tokyo's tsunami inundation assumption covers only its islands, so a central Tokyo demo would always say "outside". We moved the Japan demo to Kamakura City Hall, which Kamakura's own plan says floods under 0.5 m.
- **Keeping model output behind code guards.** In a safety app, a model's sentence must never become the instruction someone follows in the dark. Every instruction read or spoken during an emergency is fixed text from an official source or our fixed table. The model's words appear only as labelled context.

## Accomplishments that we're proud of

- The San Francisco demo runs end to end on real responses from SAM 3.1, Muse Spark, CGS, DataSF, Nominatim and OSRM, recorded on Nov 3.
- In the real demo room, Muse Spark proposed a floor spot in a doorway, and SafeZone's own check set it aside. The model reasons, and code decides.
- A voice-led emergency that only speaks official guidance, the saved spot and checked route steps, and never tells anyone to move during shaking.
- Two regions behind one registry, with Japanese guidance quoted verbatim from the Cabinet Office and JMA. Kamakura runs on labelled sample data until it is recorded.
- 236 Python tests (including adversarial safety tests and a test of the whole demo plan), 37 web tests, and a 140-check browser run that drives every flow in a phone-sized Chromium and checks what the voice says.

## What we learned

- Record real responses early. Every parser that looked right against the documentation needed a fix against a real response.
- A model is good at noticing how things relate in a room. It should not have the last word on where a person crouches. Typed relations plus code guards give both.
- Fail closed, and say so. "No checked route" with the official fallback is safer than a route nobody checked.
- Pick the demo place from the data. Tokyo was the obvious choice, and the inundation map said otherwise.

## What's next for SafeZone

- Start the emergency screens from real alerts, such as USGS ShakeAlert in California and J-Alert in Japan. Today a web app cannot wake itself, so standby works only while the app is open.
- Record Kamakura and add more regions. Each region is one set of adapters.
- Floor plans pinned to room scans.
- Room scans through Meta's glasses.

## Built with

meta-sam-3.1, muse-spark, meta-model-api, meta-sam-parser, python, starlette, pydantic, numpy, pillow, javascript, pwa, indexeddb, service-worker, web-speech-api, wake-lock-api, geolocation-api, devicemotion, openstreetmap, nominatim, overpass, osrm, california-geological-survey, datasf, fema, gsi-japan, hazard-map-portal, vercel, claude-code

## Try it

See `docs/judge_quickstart.md`.
