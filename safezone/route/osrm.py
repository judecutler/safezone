"""OSRM foot routing adapter. Raw JSON in, `OsrmRoute` / table distances out.

OSRM returns no instruction text, so `step_text` builds short English from the
maneuver type, modifier, bearing and road name.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .. import geo
from ..shapes import LonLat, Provenance, RouteStep
from ..transport import HttpError, Transport, get_json

ROUTE_BASE = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
TABLE_BASE = "https://routing.openstreetmap.de/routed-foot/table/v1/foot/"


@dataclass(frozen=True)
class OsrmRoute:
    path: list[LonLat]
    distance_m: float
    steps: list[RouteStep]


def coords_path(points: Sequence[LonLat]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)


def fetch_route(transport: Transport, origin: LonLat, destination: LonLat) -> tuple[OsrmRoute, Provenance] | None:
    """None when OSRM is unreachable, errors, or finds no route."""
    try:
        data, provenance = get_json(transport, ROUTE_BASE + coords_path((origin, destination)),
                                    {"overview": "full", "geometries": "geojson", "steps": "true"})
    except HttpError:
        return None
    route = parse_route(data)
    return None if route is None else (route, provenance)


def parse_route(data: Any) -> OsrmRoute | None:
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    route = data["routes"][0]
    path = [(float(lon), float(lat)) for lon, lat in route["geometry"]["coordinates"]]
    if len(path) < 2:
        return None
    steps = [parse_step(s) for leg in route.get("legs", []) for s in leg.get("steps", [])]
    # A zero-length turn is noise in a list read under stress; the final "Arrive" step is always 0 m.
    steps = [step for i, step in enumerate(steps) if step.distance_m >= 1 or i == len(steps) - 1]
    return OsrmRoute(path=path, distance_m=float(route["distance"]), steps=steps)


def parse_step(step: dict[str, Any]) -> RouteStep:
    m = step.get("maneuver", {})
    text = step_text(m.get("type", ""), m.get("modifier"), step.get("name") or "", m.get("bearing_after"))
    return RouteStep(instruction=text, distance_m=float(step.get("distance", 0.0)))


# maneuver type -> template. {dir} is the compass heading, {mod} the modifier, {name} the road.
_TURN = "Turn {mod} onto {name}"
_CONTINUE = "Continue on {name}"
STEP_TEMPLATES: dict[str, str] = {
    "depart": "Head {dir} on {name}",
    "arrive": "Arrive",
    "turn": _TURN,
    "end of road": _TURN,
    "fork": "Keep {mod} onto {name}",
    "merge": "Merge {mod} onto {name}",
    "on ramp": "Take the ramp onto {name}",
    "off ramp": "Take the exit onto {name}",
    "new name": _CONTINUE,
    "continue": _CONTINUE,
    "notification": _CONTINUE,
    "roundabout": "At the roundabout take the exit onto {name}",
    "rotary": "At the roundabout take the exit onto {name}",
    "roundabout turn": _TURN,
    "exit roundabout": "Exit the roundabout onto {name}",
    "exit rotary": "Exit the roundabout onto {name}",
}


def step_text(kind: str, modifier: str | None, name: str, bearing_after: float | None) -> str:
    template = STEP_TEMPLATES.get(kind, _CONTINUE)
    if kind == "turn" and modifier in ("straight", "uturn"):
        template = "Go straight on {name}" if modifier == "straight" else "Turn around onto {name}"
    if not name:
        template = template.replace(" onto {name}", "").replace(" on {name}", "")
    direction = geo.compass(bearing_after) if bearing_after is not None else "out"
    return template.format(dir=direction, mod=modifier or "", name=name).replace("  ", " ").strip()


def fetch_table(transport: Transport, origin: LonLat,
                destinations: Sequence[LonLat]) -> tuple[list[float | None], Provenance] | None:
    """Foot distances from origin to each destination; a None cell is OSRM's own null. None when the call fails."""
    if not destinations:
        return [], "live"
    try:
        data, provenance = get_json(transport, TABLE_BASE + coords_path((origin, *destinations)),
                                    {"sources": "0", "annotations": "distance"})
    except HttpError:
        return None
    cells = parse_table(data, len(destinations))
    return None if cells is None else (cells, provenance)


def parse_table(data: Any, n: int) -> list[float | None] | None:
    if data.get("code") != "Ok":
        return None
    rows = data.get("distances") or []
    if not rows or len(rows[0]) != n + 1:
        return None
    return [None if d is None else float(d) for d in rows[0][1:]]
