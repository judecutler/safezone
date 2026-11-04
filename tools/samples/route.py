"""Hand-authored OSRM stand-in for the demo. Answers any foot route or table request.

A route is an L: along the origin's avenue to Fulton Street, along Fulton to the
destination's longitude, then to the destination. Nothing here is real routing.
"""
from __future__ import annotations

import json

from safezone import geo
from safezone.route.osrm import ROUTE_BASE, TABLE_BASE
from safezone.shapes import LonLat
from safezone.transport import Request, Response

FULTON_LAT = 37.7716
TABLE_DETOUR = 1.3


def respond(request: Request) -> Response | None:
    if request.url.startswith(ROUTE_BASE):
        origin, dest = _coords(request.url[len(ROUTE_BASE):])
        return Response(200, json.dumps(route_json(origin, dest)), "sample")
    if request.url.startswith(TABLE_BASE):
        origin, *dests = _coords(request.url[len(TABLE_BASE):])
        row = [0.0] + [round(geo.haversine_m(origin, d) * TABLE_DETOUR, 1) for d in dests]
        return Response(200, json.dumps({"code": "Ok", "distances": [row]}), "sample")
    return None


def _coords(text: str) -> list[LonLat]:
    return [tuple(float(v) for v in pair.split(",")) for pair in text.split("?")[0].split(";")]  # type: ignore[misc]


def route_json(origin: LonLat, dest: LonLat) -> dict:
    corner1 = (origin[0], FULTON_LAT)
    corner2 = (dest[0], FULTON_LAT)
    path = [origin, corner1, corner2, dest]
    legs = list(zip(path, path[1:]))
    steps = []
    names = ["48th Avenue", "Fulton Street", "46th Avenue"]
    for i, (a, b) in enumerate(legs):
        bearing = geo.bearing_deg(a, b) if a != b else 0.0
        if i == 0:
            maneuver = {"type": "depart", "bearing_after": bearing, "location": list(a)}
        else:
            prev = geo.bearing_deg(*legs[i - 1]) if legs[i - 1][0] != legs[i - 1][1] else bearing
            turn = (bearing - prev + 360) % 360
            modifier = "right" if 0 < turn < 180 else "left"
            maneuver = {"type": "turn", "modifier": modifier, "bearing_after": bearing, "location": list(a)}
        steps.append({"maneuver": maneuver, "name": names[i], "mode": "walking",
                      "distance": round(geo.haversine_m(a, b), 1)})
    steps.append({"maneuver": {"type": "arrive", "bearing_after": 0, "location": list(dest)},
                  "name": names[-1], "mode": "walking", "distance": 0.0})
    distance = round(geo.path_length_m(path), 1)
    return {
        "code": "Ok",
        "routes": [{
            "geometry": {"type": "LineString", "coordinates": [list(p) for p in path]},
            "legs": [{"steps": steps, "distance": distance, "duration": distance / 1.2}],
            "distance": distance,
            "duration": distance / 1.2,
            "weight_name": "routability",
        }],
        "waypoints": [{"name": names[0], "location": list(origin), "distance": 0.0},
                      {"name": names[-1], "location": list(dest), "distance": 0.0}],
    }
