"""Hand-authored SAMPLE answers for the Japan region, for one demo address. None of this is official data.

Demo address: Kamakura City Hall (鎌倉市役所, 〒248-8686 鎌倉市御成町18-10, from the city's own guide
https://www.city.kamakura.kanagawa.jp/kouhou/documents/benrichou1.pdf). Kamakura's building plan says most of the
city hall site lies inside the tsunami inundation assumption, under 0.5 m deep (partly 0.5 to 1.2 m):
https://www.city.kamakura.kanagawa.jp/chousya-seibi/documents/hon_seibihoushin_gaiyou_2904_1.pdf
Tokyo's own tsunami inundation assumption covers only its islands, not the 23 wards, which is why the demo uses
Kamakura: https://www.bousai.metro.tokyo.lg.jp/_res/projects/default_project/_page_/001/023/364/1.pdf

The stand-in map: Sagami Bay to the south, inundation everywhere south of SAMPLE_EDGE_LAT, deeper toward the
shore. The point is approximate. Sites are named "Sample site" so no one mistakes them for the city's list.
`tools/record_japan.py` replaces every answer here with a recorded real one.
"""
from __future__ import annotations

import base64
import io
import json
import re

import numpy as np
from PIL import Image

from safezone import geo
from safezone.building import osm
from safezone.building.geocode import NOMINATIM_REVERSE_URL, NOMINATIM_URL
from safezone.japan.sites import SITES_ZOOM
from safezone.japan.tiles import DEPTH_CLASSES, TILE_PX, tile_bounds
from safezone.route.osrm import ROUTE_BASE, TABLE_BASE
from safezone.shapes import LonLat
from safezone.transport import NETWORK_FAILURE, Request, Response

JP_DEMO_ADDRESS = "鎌倉市御成町18-10"
JP_DEMO_DISPLAY = "鎌倉市役所, 18-10, 御成町, 鎌倉市, 神奈川県, 248-8686, 日本"
JP_DEMO_HOME: LonLat = (139.5466, 35.3192)
"""Approximate, from public maps. The recorded Nominatim answer replaces it."""

SAMPLE_EDGE_LAT = 35.3215
SAMPLE_SHORE_LAT = 35.3090
BANDS = [(35.3175, 1), (35.3150, 3), (35.3120, 4), (SAMPLE_SHORE_LAT, 5)]
"""(south of this latitude, depth class index). Between the edge and the first band the class is 0."""

SITES = [
    # (name, address, lon, lat, remarks)
    ("Sample site A (hill)", "Sample address, Kamakura", 139.5480, 35.3262, "SAMPLE: not from the city's list."),
    ("Sample site B (evacuation building)", "Sample address, Kamakura", 139.5440, 35.3148, "SAMPLE: upper floors."),
    ("Sample site C (temple grounds)", "Sample address, Kamakura", 139.5355, 35.3248, None),
]
SITE_PATH = re.compile(r"/xyz/skhb05/(\d+)/(\d+)/(\d+)\.geojson$")
TILE_PATH = re.compile(r"/04_tsunami_newlegend_data/(\d+)/(\d+)/(\d+)\.png$")


def _ok(body: object) -> Response:
    return Response(200, body if isinstance(body, str) else json.dumps(body, ensure_ascii=False), "sample")


def depth_at_lat(lat: float) -> int | None:
    if lat >= SAMPLE_EDGE_LAT:
        return None
    depth = 0
    for south_of, cls in BANDS:
        if lat < south_of:
            depth = cls
    return depth


def tile_png(z: int, x: int, y: int) -> str:
    """Base64 PNG painted from the sample bands, or "" (no tile) when nothing in it is inundated."""
    _, south, _, _ = tile_bounds(x, y, z)
    if south >= SAMPLE_EDGE_LAT:
        return ""
    n = 2 ** z
    rows = (y + (np.arange(TILE_PX) + 0.5) / TILE_PX)
    lats = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * rows / n))))
    img = np.zeros((TILE_PX, TILE_PX, 4), dtype=np.uint8)
    for r, lat in enumerate(lats):
        d = depth_at_lat(float(lat))
        if d is not None:
            img[r, :, :3] = DEPTH_CLASSES[d].rgb
            img[r, :, 3] = 255
    buf = io.BytesIO()
    Image.fromarray(img, "RGBA").save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def site_tile(z: int, x: int, y: int) -> dict:
    west, south, east, north = tile_bounds(x, y, z)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
              "properties": {"name": name, "address": addr, **({"remarks": rem} if rem else {})}}
             for name, addr, lon, lat, rem in SITES if z == SITES_ZOOM and west <= lon < east and south < lat <= north]
    return {"type": "FeatureCollection", "features": feats}


def _coords(text: str) -> list[LonLat]:
    return [tuple(float(v) for v in pair.split(",")) for pair in text.split("?")[0].split(";")]  # type: ignore[misc]


def route_json(origin: LonLat, dest: LonLat) -> dict:
    """An L: along the origin's longitude to the destination's latitude, then across."""
    corner = (origin[0], dest[1])
    path = [origin, corner, dest]
    steps = []
    for i, (a, b) in enumerate(zip(path, path[1:])):
        bearing = geo.bearing_deg(a, b) if a != b else 0.0
        kind = {"type": "depart"} if i == 0 else {"type": "turn", "modifier": "right" if dest[0] > origin[0] else "left"}
        steps.append({"maneuver": {**kind, "bearing_after": bearing, "location": list(a)},
                      "name": f"Sample street {i + 1}", "distance": round(geo.haversine_m(a, b), 1)})
    steps.append({"maneuver": {"type": "arrive", "bearing_after": 0, "location": list(dest)}, "name": "", "distance": 0.0})
    distance = round(geo.path_length_m(path), 1)
    return {"code": "Ok", "routes": [{"geometry": {"type": "LineString", "coordinates": [list(p) for p in path]},
                                      "legs": [{"steps": steps}], "distance": distance, "duration": distance}]}


def _nominatim_hit(lon: float, lat: float) -> dict:
    return {"place_id": 1, "lat": f"{lat}", "lon": f"{lon}", "display_name": JP_DEMO_DISPLAY,
            "address": {"amenity": "鎌倉市役所", "house_number": "18-10", "road": "御成町", "city": "鎌倉市",
                        "province": "神奈川県", "postcode": "248-8686", "country": "日本", "country_code": "jp"}}


def respond(request: Request) -> Response | None:
    params = dict(request.params)
    url = request.url
    if url == NOMINATIM_URL and params.get("q") == JP_DEMO_ADDRESS:
        # Like the real service: the US-restricted search finds nothing for a Japanese address.
        return _ok([_nominatim_hit(*JP_DEMO_HOME)] if params.get("countrycodes") == "jp" else [])
    if url == NOMINATIM_REVERSE_URL and 122 < float(params.get("lon", 0)) < 154:
        return _ok(_nominatim_hit(float(params["lon"]), float(params["lat"])))
    if m := TILE_PATH.search(url):
        return _ok(tile_png(*map(int, m.groups())))
    if m := SITE_PATH.search(url):
        return _ok(site_tile(*map(int, m.groups())))
    if url in (osm.OVERPASS_URL, *osm.OVERPASS_MIRRORS) and "35.3" in params.get("data", ""):
        return _ok({"version": 0.6, "elements": []})
    if url.startswith(ROUTE_BASE):
        origin, dest = _coords(url[len(ROUTE_BASE):])
        if origin[0] > 100:
            return _ok(route_json(origin, dest))
    if url.startswith(TABLE_BASE):
        origin, *dests = _coords(url[len(TABLE_BASE):])
        if origin[0] > 100:
            row = [0.0] + [round(geo.haversine_m(origin, d) * 1.3, 1) for d in dests]
            return _ok({"code": "Ok", "distances": [row]})
    return None


class SampleTransport:
    """Answers from the Japan samples; anything else reads as no response."""

    def send(self, request: Request) -> Response:
        return respond(request) or Response(NETWORK_FAILURE, f"no Japan sample for {request.url}", "sample")

