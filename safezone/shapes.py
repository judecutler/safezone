"""Every shape SafeZone passes between pipelines, the server and the browser.

External responses are parsed into these at the boundary (each adapter's
`parse_*` function). Code past the boundary trusts them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Shape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


Provenance = Literal["live", "recorded", "sample"]
"""Where a value came from. `sample` is hand-authored stand-in data and the UI labels it."""

PROVENANCE_RANK: dict[Provenance, int] = {"live": 0, "recorded": 1, "sample": 2}


def weakest(*sources: Provenance) -> Provenance:
    return max(sources, key=PROVENANCE_RANK.__getitem__, default="live")


ImagePoint = tuple[float, float]
"""(x, y) in pixels of the scanned image."""

BBox = tuple[float, float, float, float]
"""(left, top, right, bottom) in image pixels, half-open."""

LonLat = tuple[float, float]
"""(longitude, latitude), WGS84. GeoJSON order."""

Ring = list[LonLat]
Polygon = list[Ring]
"""Outer ring first, then holes."""


# Room ----------------------------------------------------------------------

class Segment(Shape):
    id: str
    label: str
    bbox: BBox
    outline: str | None
    """SVG path in image pixels. None when only a box is known."""
    area_px: float
    centroid: ImagePoint
    touches_floor: bool
    height_ratio: float
    confidence: float | None


Role = Literal["cover", "hazard", "neutral"]

HazardKind = Literal[
    "tall_furniture",
    "heavy_up_high",
    "tv",
    "glass",
    "overhead_fixture",
    "hanging_object",
    "bed_under_window",
    "cabinet_doors",
]


class Classified(Shape):
    segment: Segment
    role: Role
    hazard_kind: HazardKind | None
    reason: str

    @model_validator(mode="after")
    def _kind_iff_hazard(self) -> Classified:
        if (self.role == "hazard") != (self.hazard_kind is not None):
            raise ValueError("hazard_kind is set exactly when role is 'hazard'")
        return self


RelationKind = Literal["in_tip_zone", "under_stored_items", "near_glass", "blocks_exit"]


class Relation(Shape):
    kind: RelationKind
    subject_id: str
    """The segment at risk, e.g. a bed."""
    hazard_id: str
    """A segment classified as a hazard."""
    note: str
    """The model's one line, shown attributed to Muse Spark."""


class SafeSpot(Shape):
    kind: Literal["cover", "open_floor", "no_cover"]
    anchor_id: str | None
    """Segment id of the cover object. None for open_floor and no_cover."""
    point: ImagePoint | None
    """Image pixels. Set only for open_floor."""
    nearest_hazard_px: float | None
    score: Annotated[float, Field(ge=0, le=1)]
    instruction: str
    cautions: list[str]


Effort = Literal["minutes", "hour", "pro"]


class Fix(Shape):
    id: str
    target_id: str
    target_label: str
    hazard_kind: HazardKind
    action: str
    effort: Effort
    cost_usd: tuple[int, int]
    done: bool = False


class ModelUse(Shape):
    segmenter: str
    classifier: str | None
    classifier_ok: bool


class RoomScan(Shape):
    id: str
    name: str
    image_size: tuple[int, int]
    classified: list[Classified]
    spots: list[SafeSpot]
    """Ranked, best first. Always non-empty: no cover gives one no_cover spot."""
    fixes: list[Fix]
    models: ModelUse
    notes: list[str]
    provenance: Provenance
    relations: list[Relation]
    exit_note: str | None
    """The model's one line on what could block the way to the door."""


# Building ------------------------------------------------------------------

FlagKind = Literal["tsunami_zone", "soft_story", "storeys", "year_built"]
FlagTone = Literal["alert", "ok", "unknown", "info"]
"""alert: a reason to act. ok: the official source says no. unknown: no data. info: context."""


class BuildingFlag(Shape):
    kind: FlagKind
    tone: FlagTone
    value: str
    detail: str
    status: str | None
    """The source's own status text, verbatim, when it has one."""
    source_name: str
    source_url: str
    provenance: Provenance


class HazardArea(Shape):
    """Official tsunami hazard polygons near the address, for the route and shelter pipelines."""
    contains_home: bool
    polygons: list[Polygon]
    land_polygons: list[Polygon] = []
    """The same map's "outside hazard area" polygons. A route may end only on these: outside the hazard
    polygons alone also includes the ocean when a polygon's seaward edge is the shoreline."""
    county: str | None
    map_url: str | None
    source_url: str


class Geocode(Shape):
    query: str
    display_name: str
    lon: float
    lat: float
    city: str | None
    state: str | None
    provenance: Provenance


class BuildingProfile(Shape):
    address: str
    display_name: str
    lon: float
    lat: float
    city: str | None
    footprint: Ring | None
    flags: list[BuildingFlag]
    hazard_area: HazardArea | None
    """None when the CGS service could not be reached; the tsunami flag then reads unknown."""
    provenance: Provenance


# Household -----------------------------------------------------------------

class Household(Shape):
    children: bool = False
    wheelchair: bool = False
    medical: bool = False
    pets: bool = False


# Route ---------------------------------------------------------------------

class RouteStep(Shape):
    instruction: str
    distance_m: float


class WalkingRoute(Shape):
    kind: Literal["walking_route"] = "walking_route"
    origin: LonLat
    destination: LonLat
    destination_kind: Literal["outside_hazard_area"] = "outside_hazard_area"
    path: list[LonLat]
    steps: list[RouteStep]
    distance_m: float
    walk_min: float
    computed_at: datetime
    provenance: Provenance


class DirectionOnly(Shape):
    """Fallback when no checked walking route exists: head toward the nearest point outside the zone."""
    kind: Literal["direction_only"] = "direction_only"
    origin: LonLat
    destination: LonLat
    bearing_deg: float
    compass: str
    straight_m: float
    reason: str
    computed_at: datetime
    provenance: Provenance


class NoCheckedRoute(Shape):
    """No destination could be proven to be on mapped land outside the hazard area."""
    kind: Literal["no_checked_route"] = "no_checked_route"
    reason: str
    map_url: str | None


class NotInZone(Shape):
    kind: Literal["not_in_zone"] = "not_in_zone"
    reason: str


EvacRoute = Annotated[WalkingRoute | DirectionOnly | NoCheckedRoute | NotInZone, Field(discriminator="kind")]


# Shelter -------------------------------------------------------------------

class Shelter(Shape):
    id: str
    name: str
    address: str
    lon: float
    lat: float
    status: str
    capacity: int | None
    residents: int | None
    ada: bool | None
    wheelchair: bool | None
    pets_code: str | None
    source_url: str


class ShelterMatch(Shape):
    shelter: Shelter
    walk_min: float
    walk_method: Literal["route", "estimate"]
    fill_ratio: float | None
    notes: list[str]


ExcludeReason = Literal["not_open", "in_hazard_area", "hazard_check_failed", "not_wheelchair_accessible"]


class ShelterResult(Shape):
    origin: LonLat
    matches: list[ShelterMatch]
    excluded: dict[ExcludeReason, int]
    fetched_at: datetime
    replay: bool
    """True when the shelters come from a saved snapshot instead of the live FEMA feed."""
    provenance: Provenance


# Go bag --------------------------------------------------------------------

GoBagStatus = Literal["Seen in the photo", "Not seen"]


class GoBagItem(Shape):
    id: str
    label: str
    seen: bool
    status: GoBagStatus
    note: str | None
    """The model's short line on what it saw, attributed to Muse Spark. None when the item was not seen."""


class GoBagCheck(Shape):
    """What one photo shows of a go bag, item by item. It never says whether the kit is complete."""
    items: list[GoBagItem]
    """Every checklist item, in the checklist's order."""
    seen_count: int
    total: int
    model: str
    caveat: str
    source_name: str
    source_url: str
    provenance: Provenance


# Plan ----------------------------------------------------------------------

class Plan(Shape):
    building: BuildingProfile
    household: Household
    rooms: list[RoomScan]
    route: EvacRoute | None
    shelters: ShelterResult | None
    generated_at: datetime
