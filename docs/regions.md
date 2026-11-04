# Regions

SafeZone covers two regions: California (`us-ca`) and Japan (`jp`). `safezone/regions.py` holds the registry. Each `Region` owns the whole chain for its area: geocoding, the `BuildingProfile`, the evacuation plan, the after-shaking destinations and the guidance text. The server picks a region and calls it. A place outside every region gets `NoCoverage` ("SafeZone has no hazard data for this area yet"). SafeZone never guesses.

## How a place finds its region

- Address. `profile_for_address` tries each region's geocoder in registry order, and the first hit decides. The US geocoder is restricted to `countrycodes=us`, so a Japanese address falls through to the Japan geocoder. If no geocoder finds the address, the function raises `GeocodeNotFound`, the same as today.
- Point. `profile_for_point` picks the region whose bounding box holds the point, then checks the reverse-geocoded country or state. A point inside no box gets `NoCoverage` without any network call.
- `us-ca` accepts every US state. Outside California the existing pipeline still says "No tsunami map for this state", so US behaviour is unchanged.

## Japan: data sources (all keyless)

| Need | Source | Verified from |
|---|---|---|
| In the zone, and how deep | Hazard Map Portal tsunami inundation tiles, `https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png`, zoom 2 to 17. The tiles come from 40 prefectures, Tokyo (13) and Kanagawa (14) included. SafeZone reads zoom 15. | [opendata page](https://disaportaldata.gsi.go.jp/hazardmap/copyright/opendata.html) |
| Depth classes | MLIT standard colours. p.37 fig. 3-3 sets the classes at 0.5, 3, 5, 10 and 20 m and says they serve tsunami as well. p.38 fig. 3-5 adds the 0.3 m and 1 m classes. A transparent pixel or a missing tile reads as outside. A coloured pixel that matches no legend colour reads as inside, at the deepest class. | [MLIT guide (2016)](https://www.mlit.go.jp/river/basic_info/jigyo_keikaku/saigai/tisiki/hazardmap/suigai_hazardmap_tebiki_201604.pdf) |
| Designated tsunami sites | GSI 指定緊急避難場所 GeoJSON tiles, layer `skhb05` (tsunami), zoom 10, `https://cyberjapandata.gsi.go.jp/xyz/skhb05/{z}/{x}/{y}.geojson`. Being in the layer is the designation. | [data.go.jp entry](https://data.e-gov.go.jp/data/dataset/mlit_20140919_3046/resource/b1deaf8b-ed55-40d2-a72b-ed538e42b200) and [skhb01 to 08 mapping](https://www.mitsumatado.com/zen/hinanjo/) |
| Geocoding, footprint, walking | The existing Nominatim, Overpass and OSRM adapters. FOSSGIS OSRM foot routing covers the whole world. | [routing.openstreetmap.de/about](https://routing.openstreetmap.de/about.html) |
| Guidance | Cabinet Office tsunami flyer, JMA 津波から身を守るために, JMA Osaka memo 192, JMA EEW 心得. Each line is quoted verbatim in `safezone/japan/rules.py`. | Links in `japan/rules.py` `SOURCES` |

Still unverified, and the recording will answer both:

- The GeoJSON property names of `skhb05`. GSI does not document them. The adapter reads `name` and `address` (what public clients use) and also accepts the Japanese column names. A feature with no name shows "Unnamed designated site". Its location is still used.
- Whether the PNG palette matches the MLIT RGB values exactly. The adapter allows a difference of 12 per channel. An unmatched colour still reads as inside.

## Japan: the evacuation rules in code (`safezone/japan/evac.py`)

1. If home (or any point within 10 m) reads coloured, home is in the zone. Otherwise the answer is `NotInZone`.
2. Candidates are the 6 nearest `skhb05` sites within 3 km. Each site's own pixel sets its kind. `high_ground` means outside the mapped area. `evacuation_building` means inside the area but designated for tsunami, labelled "Evacuation building: go to the upper floors."
3. Every OSRM foot route is sampled every 15 m against the raster. It is rejected if any of these hold: it ends more than 80 m from the site, it is longer than 2.5 x the straight distance + 300 m, it reaches a deeper class than home's, it runs more than 75 m back from the site while inside the area, or, for high ground, it re-enters the area for more than 100 m.
4. The shortest route that passes becomes a `SiteRoute`. If none passes, or a tile fails, the answer is `NoCheckedRoute` with "Move inland and to higher ground on foot", the same as the US fallback.
5. After shaking, the "shelters" list holds the designated sites outside the mapped area, ranked by OSRM walking time. Each is labelled as an evacuation site, not a place to stay. GSI lists no access data, so a wheelchair household gets no matches and the exclusions are counted (fail closed, as with FEMA).

Shape added: `SiteRoute` (kind `site_route`) and `EvacSite`, in `safezone/shapes.py`, and `SiteRoute` is part of `EvacRoute`. It is needed because `WalkingRoute.destination_kind` can only be `outside_hazard_area`, and an evacuation building sits inside the area. Every flag, site and route carries its source URL and provenance.

## Integration: the exact change `app.py` needs

1. Live transport. The tiles are binary, and the fixtures store text, so the Japan tile hosts must go through the base64 wrapper:
   ```python
   from . import regions
   transport: Transport = ReplayTransport(Path(fixtures)) if fixtures else regions.live_transport()
   ```
   (in `Services.from_env`, replacing `LiveTransport()`).
2. `/api/profile`:
   ```python
   if point: result = await run_in_threadpool(regions.profile_for_point, *point, svc.transport)
   else:     result = await run_in_threadpool(regions.profile_for_address, address, svc.transport)
   if isinstance(result, regions.NoCoverage):
       return JSONResponse(dump(result))          # 200, kind "no_coverage"; the UI shows result.reason
   region, profile = result
   return JSONResponse({**dump(profile), "region": region.id})
   ```
   `GeocodeNotFound` and `HttpError` keep their current handlers.
3. `/api/evac` replaces the body after validation:
   ```python
   evac = await run_in_threadpool(regions.evacuate, body.building, body.household, svc.transport,
                                  svc.shelter_transport, now, svc.shelter_replay)
   if isinstance(evac, regions.NoCoverage):
       return JSONResponse({"route": None, "shelters": None, "shelters_error": evac.reason})
   return JSONResponse({"route": dump(evac.route), "shelters": dump(evac.shelters), "shelters_error": evac.shelters_error})
   ```
   (`regions` builds the region's own hazard check, so the `in_hazard_area` lambda moves out of app.py.)
4. `/api/guidance?region=jp` returns `regions.guidance(request.query_params.get("region"))`. The `us-ca` payload has the same keys as today. `jp` adds `quotes` (`ja`, `en`, `source_url` for each line), and the UI should show `ja` under `en`.
5. `shapes.EvacRoute` gains `SiteRoute`, so a saved plan validates:
   `EvacRoute = Annotated[WalkingRoute | SiteRoute | DirectionOnly | NoCheckedRoute | NotInZone, Field(discriminator="kind")]`.
   Done: `SiteRoute` and `EvacSite` now live in `shapes.py`, and `japan/shapes.py` is gone.
6. Web. `routeView` draws `site_route` like `walking_route` and adds `route.site.name`, `route.site.instruction` and `route.site.depth`. The places list shows `no_coverage` as a grey "No data" flag.

## Adding a third region

1. Write the adapters under `safezone/<region>/`. Each one is a function that matches a `Region` field: `geocode`, `reverse`, `profile(place, transport) -> BuildingProfile`, `evacuate(...) -> Evacuation` and `guidance() -> dict`. Send every outside call through the `Transport` you are given. Raise or degrade to an `unknown` flag on failure. Never turn a failure into a quiet "outside".
2. Put every instruction in `safezone/<region>/rules.py`, with sources. Quote official text verbatim, add a faithful rendering, and write SafeZone's own lines in English only.
3. Add one `Region(...)` entry to `REGIONS`, with a bounding box and an `accepts` check on the geocoded place.
4. Add `tools/samples/<region>.py` (one demo address, every answer labelled sample) and `tests/test_<region>_*.py` that run on it. Copy `tests/test_japan_evac.py`, including the outage test and the record-then-replay test.
5. Add `tools/record_<region>.py`, modelled on `tools/record_japan.py`.

## Recording Japan (user's machine, no key needed)

Run it after `tools/record_fixtures.py`, which empties `fixtures/demo` first:

```powershell
git pull; python tools\record_japan.py
```

It prints one line per call, every failed call with its status and body, the flag, the route and the sites it found, and then checks that the replay matches.

The demo address is Kamakura City Hall (鎌倉市御成町18-10). Tokyo's own tsunami inundation assumption covers only its islands ([Tokyo document](https://www.bousai.metro.tokyo.lg.jp/_res/projects/default_project/_page_/001/023/364/1.pdf)). Kamakura's building plan says most of the city hall site floods under 0.5 m in the prefecture's assumption ([city plan](https://www.city.kamakura.kanagawa.jp/chousya-seibi/documents/hon_seibihoushin_gaiyou_2904_1.pdf)).
