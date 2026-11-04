"""Building footprint, storeys and year built from OpenStreetMap through Overpass. Missing data means no flag."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..geo import LocalFrame, distance_to_boundary_m, point_in_ring
from ..shapes import BuildingFlag, FlagKind, LonLat, Provenance, Ring
from ..transport import HttpError, Transport, get_json

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRROR = "https://overpass.private.coffee/api/interpreter"
"""The main instance is often at capacity (502); this public worldwide mirror is the fallback."""
RADIUS_M = 25.0
OSM_CAVEAT = "From OpenStreetMap; volunteers map this and it can be wrong."
LEVELS = re.compile(r"^\d+(\.\d+)?$")


class _Node(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lat: float
    lon: float


class _Element(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    id: int
    tags: dict[str, str] = {}
    geometry: list[_Node] = []


class _Result(BaseModel):
    model_config = ConfigDict(extra="ignore")
    elements: list[_Element]


@dataclass(frozen=True)
class Building:
    footprint: Ring
    tags: dict[str, str]


def overpass_query(point: LonLat) -> str:
    lon, lat = point
    return f'[out:json][timeout:20];way(around:{RADIUS_M:g},{lat},{lon})["building"];out tags geom;'


def _area(ring: Ring, frame: LocalFrame) -> float:
    xy = [frame.to_xy(p) for p in ring]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))) / 2


def parse_buildings(data: Any) -> list[Building]:
    return [Building(footprint=[(n.lon, n.lat) for n in e.geometry], tags=e.tags)
            for e in _Result.model_validate(data).elements
            if e.type == "way" and len(e.geometry) >= 3]


def choose_building(buildings: list[Building], point: LonLat) -> Building | None:
    """The smallest footprint containing the point, else the nearest within RADIUS_M."""
    frame = LocalFrame(point)
    containing = [b for b in buildings if point_in_ring(point, b.footprint)]
    if containing:
        return min(containing, key=lambda b: _area(b.footprint, frame))
    near = [(distance_to_boundary_m(point, [[b.footprint]]), b) for b in buildings]
    near = [(d, b) for d, b in near if d <= RADIUS_M]
    return min(near, key=lambda t: t[0])[1] if near else None


def _flag(kind: FlagKind, value: str, url: str, provenance: Provenance) -> BuildingFlag:
    return BuildingFlag(kind=kind, tone="info", value=value, detail=OSM_CAVEAT, status=None,
                        source_name="OpenStreetMap", source_url=url, provenance=provenance)


def building_flags(building: Building, point: LonLat, provenance: Provenance) -> list[BuildingFlag]:
    lon, lat = point
    url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}"
    flags = []
    levels = building.tags.get("building:levels", "").strip()
    if LEVELS.match(levels) and float(levels) > 0:
        n = f"{float(levels):g}"
        flags.append(_flag("storeys", f"{n} storey" if n == "1" else f"{n} storeys", url, provenance))
    built = (building.tags.get("start_date") or building.tags.get("building:start_date") or "").strip()
    if built:
        flags.append(_flag("year_built", f"Built {built}", url, provenance))
    return flags


def fetch_building(transport: Transport, point: LonLat) -> tuple[Building | None, Provenance]:
    params = {"data": overpass_query(point)}
    try:
        data, provenance = get_json(transport, OVERPASS_URL, params)
    except HttpError:
        data, provenance = get_json(transport, OVERPASS_MIRROR, params)
    return choose_building(parse_buildings(data), point), provenance
