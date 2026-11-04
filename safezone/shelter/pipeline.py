"""Shelters that fit the household, from the route's end.

Every filter fails closed: a shelter whose hazard status or wheelchair access
is unknown is excluded and counted, never shown as a match. Notes are plain
strings for the UI; nothing here claims a shelter can serve a medical need.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal, get_args

from .. import geo
from ..route.osrm import fetch_table
from ..shapes import (BuildingProfile, ExcludeReason, Household, LonLat, Polygon, Provenance, Shelter,
                      ShelterMatch, ShelterResult, weakest)
from ..transport import Transport
from .fema import fetch_shelters

NEAREST_N = 25
FILL_WARN = 0.8
"""Starting weight from the plan, not a standard. Shelters at or above it rank after the rest."""
ESTIMATE_DETOUR = 1.4
"""Straight line to walking distance when OSRM gives no cell."""
WALK_SPEED_MPS = 1.0

HazardCheck = Callable[[LonLat], bool]
HazardVerdict = Literal["ok", "in_hazard_area", "hazard_check_failed"]


def find_shelters(origin: LonLat, profile: BuildingProfile, household: Household, transport: Transport,
                  hazard_check: HazardCheck, now: datetime, replay: bool) -> ShelterResult:
    """Raises HttpError when FEMA does not answer. Zero matches is a valid result."""
    shelters, fema_provenance = fetch_shelters(transport, origin)
    polygons = profile.hazard_area.polygons if profile.hazard_area else []
    kept, excluded = filter_shelters(shelters, origin, household, hazard_check, polygons)

    provenances = [fema_provenance]
    cells: list[float | None] = [None] * len(kept)
    table = fetch_table(transport, origin, [(s.lon, s.lat) for s in kept])
    if table is not None:
        cells, table_provenance = table
        provenances.append(table_provenance)

    matches = sorted((build_match(s, cell, origin, household) for s, cell in zip(kept, cells)), key=rank_key)
    return ShelterResult(origin=origin, matches=matches, excluded=excluded, fetched_at=now, replay=replay,
                         provenance=weakest(*provenances))


def filter_shelters(shelters: Sequence[Shelter], origin: LonLat, household: Household, hazard_check: HazardCheck,
                    polygons: Sequence[Polygon]) -> tuple[list[Shelter], dict[ExcludeReason, int]]:
    excluded: Counter[ExcludeReason] = Counter({reason: 0 for reason in get_args(ExcludeReason)})
    open_shelters = []
    for shelter in shelters:
        if shelter.status.strip().upper() == "OPEN":
            open_shelters.append(shelter)
        else:
            excluded["not_open"] += 1
    nearest = sorted(open_shelters, key=lambda s: geo.haversine_m(origin, (s.lon, s.lat)))[:NEAREST_N]

    kept = []
    for shelter in nearest:
        verdict = hazard_verdict((shelter.lon, shelter.lat), polygons, hazard_check)
        if verdict != "ok":
            excluded[verdict] += 1
        elif household.wheelchair and shelter.wheelchair is not True:
            excluded["not_wheelchair_accessible"] += 1
        else:
            kept.append(shelter)
    return kept, dict(excluded)


def hazard_verdict(point: LonLat, polygons: Sequence[Polygon], hazard_check: HazardCheck) -> HazardVerdict:
    """The official polygons we already hold settle a point inside them; everything else asks the point query."""
    if geo.point_in_any(point, polygons):
        return "in_hazard_area"
    try:
        return "in_hazard_area" if hazard_check(point) else "ok"
    except Exception:  # any failure leaves the status unknown, and unknown is never shown
        return "hazard_check_failed"


def build_match(shelter: Shelter, table_m: float | None, origin: LonLat, household: Household) -> ShelterMatch:
    if table_m is None:
        distance_m = geo.haversine_m(origin, (shelter.lon, shelter.lat)) * ESTIMATE_DETOUR
        method = "estimate"
    else:
        distance_m, method = table_m, "route"
    fill = fill_ratio(shelter)
    return ShelterMatch(shelter=shelter, walk_min=distance_m / WALK_SPEED_MPS / 60, walk_method=method,
                        fill_ratio=fill, notes=shelter_notes(shelter, fill, household))


def fill_ratio(shelter: Shelter) -> float | None:
    if shelter.residents is None or not shelter.capacity or shelter.capacity <= 0:
        return None
    return shelter.residents / shelter.capacity


def shelter_notes(shelter: Shelter, fill: float | None, household: Household) -> list[str]:
    notes = []
    if fill is None:
        notes.append("Capacity not reported.")
    elif fill >= FILL_WARN:
        notes.append(f"Nearly full: about {round(fill * 100)}% of capacity.")
    if household.pets:
        notes.append(f"Pet accommodation code: {shelter.pets_code}. Call ahead about pets." if shelter.pets_code
                     else "No pet information. Call ahead about pets.")
    if household.medical:
        notes.append("Call ahead about medical needs. FEMA data does not show medical support.")
    if household.wheelchair:
        notes.append("Listed as wheelchair accessible.")
    return notes


def rank_key(match: ShelterMatch) -> tuple[int, float]:
    nearly_full = match.fill_ratio is not None and match.fill_ratio >= FILL_WARN
    return (1 if nearly_full else 0, match.walk_min)
