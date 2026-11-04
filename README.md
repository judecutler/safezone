# SafeZone

Prepare once for a coastal earthquake, then follow the plan.

On the coast, an earthquake gives you two jobs: survive the shaking, then get out of the water's way. Almost nobody has worked out either in advance. SafeZone builds that plan in a few minutes from a photo of each room and your address. The plan lives on your phone and works offline. When the shaking stops, the same app becomes a one-screen guide to your walking route out of the tsunami hazard area and to shelters that fit your household.

Built for the Meta Global AI Developer Hackathon (indie track, Build for Your World problem statement).

**Built during the hackathon.** Everything in this repository was written during the hackathon's building period (Oct 27 to Nov 4, 2026). The git history shows every step. Nothing was carried over from an earlier project. Third-party pieces are only the Python packages in `requirements.txt` and the public data services listed under Data sources.

## What it does

**Prepare (calm mode).**

1. **Room scan.** Photograph a room. SAM 3.1 finds the objects that matter in an earthquake. Muse Spark reads the photo against a fixed safety rule set: which objects are hazards, which are sturdy cover, and how they relate (a bed inside a wardrobe's tipping zone, boxes stored above a bed). Code then ranks safe spots and builds a fix list from a fixed table, so the model never invents a fix.
2. **Building profile.** Type the address. SafeZone checks California's official tsunami hazard map, San Francisco's soft-story list and OpenStreetMap, and shows each flag with a link to its source.
3. **Household needs.** Four taps: young children, wheelchair or mobility aid, medical needs, pets.
4. **The plan.** Building flags, each room's safe spot, the fix checklist and what to do when the shaking stops, on one page. It is saved on the device and prints as a fridge sheet.

**Emergency (dark, high-contrast mode).**

1. **During shaking:** Drop, Cover, Hold On, with your rooms' safe spots. Nothing on this screen tells you to move.
2. **"Shaking has stopped":** if you are in the tsunami hazard area, go now, on foot. The walking route out of the hazard area opens offline, drawn without map tiles, with your live GPS position.
3. **Shelters that fit:** from FEMA's open-shelter layer, filtered for your household and ranked by walking time and how full they are, each with the data's timestamp.

## How it works

Four independent pipelines each fill one part of a `Plan` (`safezone/shapes.py`). Any one can fail without breaking the page.

| Pipeline | Runs on | Code |
|---|---|---|
| Room | SAM 3.1 (Meta Model API, Responses endpoint, one text prompt per object class) then one Muse Spark vision call with a strict JSON schema; scoring and fixes in plain Python | `safezone/room/` |
| Building | Nominatim geocoding; CGS tsunami hazard area (ArcGIS point and polygon queries); DataSF soft-story list; Overpass for storeys | `safezone/building/` |
| Route | Candidate points on the map's own "outside hazard area" land, OSRM foot routes to each, and hard checks in code: the route must end on that land, must never go deeper into the hazard area than home or double back toward the water, must not re-enter, and must not wander along the shore. Pace 1.0 m/s for children and older adults. If no route passes, it gives a compass direction toward proven land, and if there is none, it says it could not check a route | `safezone/route/` |
| Shelter | FEMA Open Shelters layer; drops closed shelters and any inside the hazard area (fail closed); wheelchair-accessible only when needed; ranked by walking time, then fullness | `safezone/shelter/` |

The only Meta model calls are SAM 3.1 and Muse Spark. The building flags, the route and the shelter filters come from official data and deterministic code you can check by hand.

Every outside call goes through one boundary (`safezone/transport.py`). That boundary can run live, record what it sees, or replay a recording. So the whole pipeline runs end to end offline from saved responses, and every value carries its provenance (`live`, `recorded` or `sample`). The app labels sample data as SAMPLE.

## Run it

Requires Python 3.12 or later.

```sh
pip install -r requirements.txt
cp .env.example .env            # add META_API_KEY from dev.meta.ai
python tools/record_fixtures.py # optional: record real responses for the demo household
uvicorn safezone.app:create_app --factory --port 8000
```

On Windows PowerShell the same steps work; start the server with `python -m uvicorn safezone.app:create_app --factory --port 8000`. If a recording run fails with `CERTIFICATE_VERIFY_FAILED`, run `pip install --upgrade certifi` and retry.

Open http://localhost:8000 on your phone (same network) or in a mobile-sized browser window. "Load the demo household" shows a full plan without any API calls.

Command-line checks:

```sh
python run.py demo/living_room.jpg --fixtures fixtures/demo
python profile_address.py "1000 Great Highway, San Francisco, CA 94121" --fixtures fixtures/demo
python -m pytest -q
```

Deploy: `modal deploy modal_app.py`.

### What has been checked against real responses

A probe run on Nov 3 (`tools/probe_apis.py`) recorded one real response from each service. The parsers were checked against them: SAM 3.1's box and mask format (masks arrive downscaled to at most 1024 px and are stretched over their box), Muse Spark's strict JSON schema mode, the CGS point query (the demo address is inside the official hazard area), DataSF soft-story rows, and OSRM foot routes. The FEMA layer has not been checked against a real response yet.

### About the demo data

The repository ships with hand-authored SAMPLE fixtures, so the demo runs anywhere. They follow the documented response formats of each API, but they are not real responses. The hazard polygon is a rough stand-in, and the shelters are synthetic. The app tags all of it SAMPLE DATA. `python tools/record_fixtures.py` replaces them with real recorded responses. Run it before filming.

## Data sources

- Meta Model API: [SAM 3.1](https://dev.meta.ai/docs/sam/segmenting) and Muse Spark ([models](https://dev.meta.ai/docs/models)).
- California Geological Survey, [Tsunami Hazard Area layer](https://gis.conservation.ca.gov/server/rest/services/CGS/IW_Tsunami_Hazard_Area/FeatureServer/0) and [tsunami maps](https://www.conservation.ca.gov/cgs/tsunami/maps).
- DataSF, [Soft-Story Properties](https://catalog-old.data.gov/dataset/soft-story-properties) (dataset `beah-shgi`).
- OpenStreetMap: [Nominatim](https://nominatim.org/) geocoding, [Overpass](https://overpass-api.de/) building data, [OSRM foot routing](https://routing.openstreetmap.de/).
- FEMA, [Open Shelters layer](https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0).

Safety guidance, quoted in `safezone/rules.py`:

- [Ready.gov: Earthquakes](https://www.ready.gov/earthquakes)
- [ShakeOut: Drop, Cover, Hold On](https://www.shakeout.org/dropcoverholdon/)
- [CGS: before, during and after a tsunami](https://conservation.ca.gov/cgs/tsunami/preparedness)
- [CGS: How to survive a tsunami](https://www.conservation.ca.gov/cgs/Documents/Tsunami/How-to-Survive-a-Tsunami.pdf)
- [PG&E: Earthquake safety](https://www.pge.com/assets/pge/docs/newsroom/safety-action-center/earthquake.pdf)

## Privacy

There are no accounts. The server stores nothing: photos and addresses exist only for the length of the request. Your plan and your room photos stay on your device, in the browser's storage.

## Limits, said plainly

- SafeZone shows hazards it can see in your photos and flags from official public data. It is not a structural assessment, and it does not have your building's plans. In California, building plans cannot be copied without the owner's and the architect's permission.
- Routes are planning aids computed from California's tsunami hazard map. They are not official evacuation routes.
- Shelter listings come from FEMA data, which can lag behind reality. Call ahead and confirm with local officials.
- Official instructions and local evacuation signs always override this app.

## Roadmap

Japan's designated evacuation sites (open data), floor plans pinned to room scans, Berkeley's soft-story inventory, live official alerts, and room scans through Meta's glasses.
