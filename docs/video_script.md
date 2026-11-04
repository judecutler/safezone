# SafeZone demo video (final, 2:59.0)

The video is mostly animation, rendered in code from the app's own design tokens, real screenshots of the recorded demo, and the real SAM 3.1 masks and Muse Spark output. It includes two clips Jude filmed on Nov 4: his reaction, and the live app on a phone with the app's own voice. Nothing in the video makes a claim the app or its sources don't.

Rules the script follows: every number has a source on screen. No invented benefit figures. No photos or names of victims. Meta's models are named in text; Meta's logo is not used.

The narration voice is Kokoro (`af_heart`), an open-weight text-to-speech model, run locally. Captions are burnt in.

| At | Scene | Narration | Source on screen |
|---|---|---|---|
| 0:00.0 | tolls | Every one of these disasters began the same way. The ground shook, and people had minutes to act. | USGS (1906, 2004); Cabinet Office of Japan (1995, 2024); National Police Agency via Jiji, Mar 2026 (2011) |
| 0:08.9 | dec5 | December fifth, twenty twenty-four. Five million Californians got a tsunami warning that never said who was in the zone, or where to go. | KQED; City of Berkeley after-action report, Apr 2025 |
| 0:18.8 | gap | Most people never prepare. Only thirty-one percent of American households know their evacuation route. And up to half of quake injuries in Japan come from furniture. | FEMA National Household Survey 2023 (31%); Tokyo Fire Department 2024 (30–50%) |
| 0:31.0 | works | Yet preparation works. In twenty eleven, survivors who left at the last minute were ten times as likely to be caught by the wave. Japan estimates that if everyone evacuates within ten minutes, deaths in its next great tsunami fall by seventy percent. | Cabinet Office of Japan, 2011 survivor interviews (4.8% vs 49% caught by the wave); Cabinet Office Nankai Trough estimate, Mar 2025 (about 215,000 to about 73,000, 70% fewer) |
| 0:48.4 | title | So we built SafeZone, on Meta's SAM 3.1 and Muse Spark. It gets a household to those benchmarks in one sitting, then talks them through the emergency. | App screens from the recorded demo |
| 0:59.6 | hazard | Step one: prepare. SafeZone checks your home against the official tsunami hazard map. This one is inside the zone. | App screens from the recorded demo |
| 1:08.8 | sam | Then, one photo per room. SAM 3.1 outlines everything that could tip, fall, or swing open. | App screens from the recorded demo |
| 1:16.2 | muse | Muse Spark reasons about how they relate. This wardrobe can tip onto the bed. That box sits right above it. | App screens from the recorded demo |
| 1:24.3 | guard | Then code checks the model. Muse Spark suggested a spot in a doorway, so SafeZone set it aside. The model proposes. Code decides. | App screens from the recorded demo |
| 1:35.5 | react | (no narration) | Jude's reaction clip, with its own sound |
| 1:39.2 | gobag | Muse Spark checks the go bag against the Ready.gov kit, and never says it is enough. | App screens from the recorded demo |
| 1:45.4 | route | Then the route. Every walking route is checked in code. It must end outside the hazard area, on land, and never lead deeper in. This one is ten minutes at a child's pace, saved for offline use. | App screens from the recorded demo |
| 1:59.8 | japan | In Japan it uses official maps and evacuation sites. Where it can't check a route, it says so. | App screens from the recorded demo |
| 2:07.0 | bench | In five minutes, a household has done what most people never do. | App screens from the recorded demo |
| 2:12.1 | shake | Step two: when it happens. During shaking, SafeZone says one thing. Drop, cover, and hold on. Nothing on that screen tells you to move. | App screens from the recorded demo |
| 2:22.9 | clip | (no narration) | Jude's phone recording of the live app in demo mode, with the app's own voice |
| 2:30.9 | after | When it stops: go now, on foot. Then it talks you out, turn by turn, even with no signal, and lists shelters that fit your household. | same phone recording, under the narration |
| 2:40.4 | close | Remember those numbers. Getting out early, and securing the room around you, save lives. SafeZone puts that preparation in every home. | App screens from the recorded demo |
| 2:50.5 | end | SafeZone. Built on Meta AI. Prepare once, then follow the plan. | App screens from the recorded demo |

## Rebuild

See `video/README.md`. The phone clips are not in the repo, because they show a face.
