"""Hand-authored SAMPLE answers for the building pipeline. Not official data; the UI labels it sample."""
from __future__ import annotations

import json
import re

from safezone.building import cgs, osm, softstory
from safezone.building.geocode import NOMINATIM_URL
from safezone.geo import LocalFrame, haversine_m, point_in_ring
from safezone.transport import NETWORK_FAILURE, Request, Response

from .geo import (DEMO_ADDRESS, DEMO_DISPLAY, DEMO_HOME, OUTSIDE_ADDRESS, OUTSIDE_DISPLAY, OUTSIDE_HOME,
                  SAMPLE_HAZARD_RING, SAMPLE_LAND_RING)

PLACES = {
    DEMO_ADDRESS: (DEMO_DISPLAY, DEMO_HOME, {
        "amenity": "Beach Chalet", "house_number": "1000", "road": "Great Highway", "suburb": "Outer Richmond",
        "city": "San Francisco", "county": "San Francisco", "state": "California", "postcode": "94121",
        "country": "United States", "country_code": "us"}),
    OUTSIDE_ADDRESS: (OUTSIDE_DISPLAY, OUTSIDE_HOME, {
        "amenity": "San Francisco City Hall", "house_number": "1", "road": "Doctor Carlton B Goodlett Place",
        "suburb": "Civic Center", "city": "San Francisco", "county": "San Francisco", "state": "California",
        "postcode": "94102", "country": "United States", "country_code": "us"}),
}

# Esri outer rings run clockwise; the shared sample ring is drawn counter-clockwise.
ESRI_RING = [list(p) for p in reversed(SAMPLE_HAZARD_RING)]
ESRI_LAND_RING = [list(p) for p in reversed(SAMPLE_LAND_RING)]
HAZARD = {"Evacuate": "Yes, Tsunami Hazard Area", "County": "San Francisco", "Map_Link": None}
OUTSIDE = {"Evacuate": "No, Outside Hazard Area", "County": "San Francisco", "Map_Link": None}
FOOTPRINT_HALF_M = (18.0, 12.0)
OVERPASS_POINT = re.compile(r"around:[\d.]+,(-?[\d.]+),(-?[\d.]+)\)")


def _ok(body: object) -> Response:
    return Response(200, json.dumps(body), "sample")


def _nominatim(params: dict[str, str]) -> Response:
    place = PLACES.get(params.get("q", ""))
    if place is None:
        return _ok([])
    display, (lon, lat), address = place
    return _ok([{"place_id": 1, "lat": f"{lat}", "lon": f"{lon}", "display_name": display,
                 "category": "amenity", "type": "building", "address": address}])


def _cgs(params: dict[str, str]) -> Response:
    xs = [float(v) for v in params["geometry"].split(",")]
    if params["geometryType"] == "esriGeometryPoint":
        attrs = HAZARD if point_in_ring((xs[0], xs[1]), SAMPLE_HAZARD_RING) else OUTSIDE
        return _ok({"objectIdFieldName": "OBJECTID", "features": [{"attributes": attrs}]})
    xmin, ymin, xmax, ymax = xs
    is_land = params.get("where", "").startswith("Evacuate LIKE 'No")
    ring, esri_ring, attrs = (SAMPLE_LAND_RING, ESRI_LAND_RING, OUTSIDE) if is_land else (SAMPLE_HAZARD_RING, ESRI_RING, HAZARD)
    lons, lats = zip(*ring)
    overlaps = xmin <= max(lons) and min(lons) <= xmax and ymin <= max(lats) and min(lats) <= ymax
    features = [{"attributes": attrs, "geometry": {"rings": [esri_ring]}}] if overlaps else []
    return _ok({"objectIdFieldName": "OBJECTID", "geometryType": "esriGeometryPolygon",
                "spatialReference": {"wkid": 4326}, "features": features, "exceededTransferLimit": False})


def _overpass(params: dict[str, str]) -> Response:
    m = OVERPASS_POINT.search(params.get("data", ""))
    if not m or haversine_m((float(m.group(2)), float(m.group(1))), DEMO_HOME) > osm.RADIUS_M:
        return _ok({"version": 0.6, "elements": []})
    frame = LocalFrame(DEMO_HOME)
    hx, hy = FOOTPRINT_HALF_M
    corners = [frame.to_lonlat(x, y) for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy), (-hx, -hy))]
    way = {"type": "way", "id": 1, "tags": {"building": "yes", "building:levels": "2"},
           "geometry": [{"lat": round(lat, 7), "lon": round(lon, 7)} for lon, lat in corners]}
    return _ok({"version": 0.6, "elements": [way]})


def respond(request: Request) -> Response | None:
    params = dict(request.params)
    if request.url == NOMINATIM_URL:
        return _nominatim(params)
    if request.url == cgs.QUERY_URL:
        return _cgs(params)
    if request.url == softstory.SF_ENDPOINT:
        return _ok([])
    if request.url == osm.OVERPASS_URL:
        return _overpass(params)
    return None


class SampleTransport:
    """Answers from the building samples; anything else reads as no response."""

    def send(self, request: Request) -> Response:
        return respond(request) or Response(NETWORK_FAILURE, "no sample", "sample")
