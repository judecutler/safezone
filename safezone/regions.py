"""Which hazard data serves a place. One Region per covered area; everything else gets an honest "no data".

A region owns the whole chain for its area: geocoding, the BuildingProfile, the evacuation plan, the
after-shaking destinations and the guidance text. The server picks a region and calls it, and never branches
on a country itself. To add a region, write its adapters and add one entry to REGIONS (docs/regions.md).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from . import rules
from .building import geocode as us_geocode
from .building.cgs import in_hazard_area
from .building.geocode import GeocodeNotFound
from .building.pipeline import profile_for as us_profile_for
from .japan import evac as jp_evac
from .japan import profile as jp_profile
from .japan import rules as jp_rules
from .japan.tiles import TileUnavailable
from .japan.tiles import live_transport as _jp_live_transport
from .route.pipeline import plan_route
from .shapes import BuildingProfile, DirectionOnly, EvacRoute, Geocode, Household, LonLat, Shape, ShelterResult, WalkingRoute
from .shelter.pipeline import find_shelters
from .transport import HttpError, Transport

RegionId = Literal["us-ca", "jp"]

NO_COVERAGE = ("SafeZone has no hazard data for this area yet. Use your local government's official tsunami and "
               "earthquake maps.")


class NoCoverage(Shape):
    """The answer for a place outside every region. Nothing about the place is guessed."""
    kind: Literal["no_coverage"] = "no_coverage"
    query: str
    reason: str = NO_COVERAGE
    regions: list[str]
    """Names of the regions SafeZone does cover, for the message."""


class Evacuation(Shape):
    route: EvacRoute | None
    """None when the hazard map was unavailable."""
    shelters: ShelterResult | None
    shelters_error: str | None


@dataclass(frozen=True)
class Bounds:
    west: float
    south: float
    east: float
    north: float

    def contains(self, p: LonLat) -> bool:
        return self.west <= p[0] <= self.east and self.south <= p[1] <= self.north


@dataclass(frozen=True)
class Region:
    id: RegionId
    name: str
    language: str
    """BCP-47 tag of the official guidance this region quotes."""
    bounds: Bounds
    """A coarse box. `accepts` makes the real decision from the geocoded place."""
    geocode: Callable[[Transport, str], Geocode]
    reverse: Callable[[Transport, float, float], Geocode]
    accepts: Callable[[Geocode], bool]
    profile: Callable[[Geocode, Transport], BuildingProfile]
    evacuate: Callable[[BuildingProfile, Household, Transport, Transport, datetime, bool], Evacuation]
    guidance: Callable[[], dict[str, Any]]


# us-ca: the existing pipelines, unchanged -----------------------------------------------------------------

def _us_evacuate(profile: BuildingProfile, household: Household, transport: Transport,
                 shelter_transport: Transport, now: datetime, replay: bool) -> Evacuation:
    route = plan_route(profile, transport, now)
    origin = route.destination if isinstance(route, (WalkingRoute, DirectionOnly)) else (profile.lon, profile.lat)
    shelters, shelters_error = None, None
    try:
        shelters = find_shelters(origin, profile, household, shelter_transport,
                                 lambda point: in_hazard_area(transport, point), now, replay)
    except (HttpError, ValueError, KeyError) as exc:
        shelters_error = f"Shelter data was unavailable ({type(exc).__name__})."
    return Evacuation(route=route, shelters=shelters, shelters_error=shelters_error)


def _us_guidance() -> dict[str, Any]:
    return {
        "region": "us-ca", "language": "en",
        "during": rules.DURING_SHAKING, "during_special": rules.DURING_SPECIAL, "after": rules.AFTER_SHAKING,
        "go_now": rules.GO_NOW, "stay_away": rules.STAY_AWAY, "not_in_zone": rules.NOT_IN_ZONE,
        "disclaimers": rules.DISCLAIMERS, "sources": rules.SOURCES, "hazard_labels": rules.HAZARD_LABELS,
    }


# jp ------------------------------------------------------------------------------------------------------

def _jp_evacuate(profile: BuildingProfile, household: Household, transport: Transport,
                 shelter_transport: Transport, now: datetime, replay: bool) -> Evacuation:
    route = jp_evac.plan_evacuation(profile, transport, now)
    shelters, shelters_error = None, None
    try:
        shelters = jp_evac.find_sites_as_shelters((profile.lon, profile.lat), household, transport, now)
    except (TileUnavailable, HttpError, ValueError) as exc:
        shelters_error = f"Evacuation site data was unavailable ({type(exc).__name__})."
    return Evacuation(route=route, shelters=shelters, shelters_error=shelters_error)


def _jp_guidance() -> dict[str, Any]:
    def en(quotes: list[jp_rules.Quote]) -> list[str]:
        return [q.en for q in quotes]

    return {
        "region": "jp", "language": "ja",
        "during": en(jp_rules.DURING_SHAKING),
        # Body-position advice for special cases is not region-specific; it keeps its ShakeOut source.
        "during_special": rules.DURING_SPECIAL,
        "after": rules.AFTER_SHAKING,
        "go_now": " ".join(en(jp_rules.GO_NOW)),
        "stay_away": " ".join(en(jp_rules.STAY_AWAY)),
        "not_in_zone": jp_rules.NOT_IN_ZONE,
        "disclaimers": jp_rules.DISCLAIMERS,
        "sources": {**rules.SOURCES, **jp_rules.SOURCES},
        "hazard_labels": rules.HAZARD_LABELS,
        "quotes": {
            "during": [q.as_json() for q in jp_rules.DURING_SHAKING],
            "go_now": [q.as_json() for q in jp_rules.GO_NOW],
            "stay_away": [q.as_json() for q in jp_rules.STAY_AWAY],
        },
    }


US_STATES = frozenset({
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
    "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas",
    "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
})

REGIONS: dict[RegionId, Region] = {
    "us-ca": Region(
        # Accepts every US state, as the app always has: outside California the existing pipeline already
        # says "No tsunami map for this state". The box is loose (it reaches into Mexico and Canada), so the
        # geocoded state decides.
        id="us-ca", name="California, United States", language="en",
        bounds=Bounds(-179.9, 18.0, -66.0, 71.6),
        geocode=us_geocode.geocode, reverse=us_geocode.reverse_geocode,
        accepts=lambda place: place.state in US_STATES,
        profile=us_profile_for, evacuate=_us_evacuate, guidance=_us_guidance,
    ),
    "jp": Region(
        id="jp", name="Japan", language="ja",
        bounds=Bounds(122.9, 20.4, 154.0, 45.6),
        geocode=jp_profile.geocode_jp, reverse=jp_profile.reverse_jp,
        accepts=lambda place: True,
        profile=jp_profile.profile_for, evacuate=_jp_evacuate, guidance=_jp_guidance,
    ),
}


def _no_coverage(query: str) -> NoCoverage:
    return NoCoverage(query=query, regions=[r.name for r in REGIONS.values()])


def region_for_point(p: LonLat) -> Region | None:
    return next((r for r in REGIONS.values() if r.bounds.contains(p)), None)


def profile_for_address(address: str, transport: Transport) -> tuple[Region, BuildingProfile] | NoCoverage:
    """Tries each region's geocoder in order; the first hit decides. Raises GeocodeNotFound when none finds it."""
    for region in REGIONS.values():
        try:
            place = region.geocode(transport, address)
        except GeocodeNotFound:
            continue
        if not (region.bounds.contains((place.lon, place.lat)) and region.accepts(place)):
            return _no_coverage(address)
        return region, region.profile(place, transport)
    raise GeocodeNotFound(address)


def profile_for_point(lon: float, lat: float, transport: Transport) -> tuple[Region, BuildingProfile] | NoCoverage:
    query = f"{lat:.5f},{lon:.5f}"
    region = region_for_point((lon, lat))
    if region is None:
        return _no_coverage(query)
    try:
        place = region.reverse(transport, lon, lat)
    except jp_profile.OutsideJapan:
        return _no_coverage(query)
    if not region.accepts(place):
        return _no_coverage(query)
    return region, region.profile(place, transport)


def evacuate(profile: BuildingProfile, household: Household, transport: Transport, shelter_transport: Transport,
             now: datetime, replay: bool) -> Evacuation | NoCoverage:
    region = region_for_point((profile.lon, profile.lat))
    if region is None:
        return _no_coverage(profile.address)
    return region.evacuate(profile, household, transport, shelter_transport, now, replay)


def guidance(region_id: str | None) -> dict[str, Any]:
    """Unknown or missing ids fall back to us-ca, the app's existing default."""
    region = REGIONS.get(region_id) if region_id in REGIONS else None  # type: ignore[arg-type]
    return (region or REGIONS["us-ca"]).guidance()


def live_transport() -> Transport:
    """The live transport every region can use: plain HTTP, with Japan's raster tiles carried as base64 text."""
    return _jp_live_transport()
