"""The one route shape Japan adds. Everything else reuses safezone.shapes.

`WalkingRoute.destination_kind` can only say "outside_hazard_area", and an evacuation building sits inside the
inundation area, so a route to a designated site needs its own kind. The integrator adds `SiteRoute` to
`shapes.EvacRoute` (see docs/regions.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from ..shapes import LonLat, Provenance, RouteStep, Shape

SiteKind = Literal["high_ground", "evacuation_building"]
"""high_ground: the site's own pixel reads outside the mapped inundation area.
evacuation_building: a tsunami-designated site inside it, so its designation is for going up, not out."""


class EvacSite(Shape):
    name: str
    address: str
    lon: float
    lat: float
    kind: SiteKind
    instruction: str
    """Fixed text from japan/rules.py for this kind."""
    depth: str
    """Mapped depth class at the site, in English, e.g. "no mapped inundation"."""
    remarks: str | None
    source_name: str
    source_url: str
    provenance: Provenance


class SiteRoute(Shape):
    kind: Literal["site_route"] = "site_route"
    origin: LonLat
    destination: LonLat
    site: EvacSite
    path: list[LonLat]
    steps: list[RouteStep]
    distance_m: float
    walk_min: float
    home_depth: str
    computed_at: datetime
    provenance: Provenance
