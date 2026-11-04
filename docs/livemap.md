# Live map contract (Nov 4, noon)

`web/js/livemap.js` is the one module that draws a real map. Everything else calls it. Leaflet 1.9.4 is vendored in `web/vendor/leaflet/` (load `leaflet.js` with a script tag once, and `leaflet.css` with a link tag, both from the module; `L` is then global).

```js
// Creates a map inside `container` (an element already in the DOM, with a set height). Returns a controller.
export async function liveMap(container, { region = 'us-ca', interactive = true } = {}) -> MapController

MapController = {
  setHome([lon, lat], label = 'Home'),                 // yellow home marker
  setHazard(hazardArea),        // plan.building.hazard_area: { polygons: [[ring, ...holes], ...], land_polygons }
                                // rings are [[lon, lat], ...]; draw hazard polygons in --sev-3 orange, translucent,
                                // with a legend "Tsunami hazard area (California Geological Survey)".
                                // Region 'jp': add the Hazard Map Portal tsunami inundation raster as an overlay
                                // (https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png,
                                // opacity 0.6, maxNativeZoom 17) with its attribution, instead of polygons.
  setRoute(route),              // plan.route: walking_route | site_route draws path as a thick yellow line with a dark
                                // casing and the destination (OUT OF ZONE or the site's name); direction_only draws a
                                // dashed bearing arrow; others draw nothing. Numbered step markers at each turn.
  setPlaces(list),              // [{ lon, lat, label, kind: 'shelter' | 'site' }], green evacuation-site style markers
  setWalker([lon, lat] | null), // the live position (GPS or the demo walker), a pulsing dot
  highlight(what, text),        // what: 'home' | 'hazard' | 'route' | 'places'. Pans and zooms to it and shows a short
                                // label card on the map (text). Used by the setup screens to reveal findings.
  fit(what = 'all'),            // 'home' | 'route' | 'all'
  destroy(),
}
```

Base tiles: CARTO light (`https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png`, attribution
"© OpenStreetMap contributors © CARTO"). The service worker caches tiles as they are viewed (runtime cache, at most
about 300 tiles), so a plan viewed online shows its map offline. With no tiles at all, the overlays still draw on
the paper background, so the hazard area, route and walker never depend on the network.

Style: the app's tokens (`--accent` yellow route, `--sev-3` hazard, `--ink` casing). Labels use the app font. The map
never says "safe".
