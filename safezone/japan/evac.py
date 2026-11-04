"""Walking route to a designated tsunami evacuation site, and the sites as the shelter list.

Japanese practice is to go to the nearest designated site (指定緊急避難場所, tsunami): high ground, or a tsunami
evacuation building whose upper floors are the refuge. Every candidate comes from GSI's tsunami layer, so the
designation is checked by construction. Its own pixel decides its kind. Each OSRM route is sampled along its
length against the inundation raster before it is shown. With no checked route, the answer is the same
"move inland and to higher ground" fallback as in the US.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from .. import geo
from ..route.osrm import OsrmRoute, fetch_route, fetch_table
from ..shapes import (BuildingProfile, EvacSite, Household, LonLat, NoCheckedRoute, NotInZone, Provenance, Shelter,
                      ShelterMatch, ShelterResult, SiteKind, SiteRoute, weakest)
from ..transport import Transport
from . import rules
from .profile import EDGE_RADIUS_M
from .sites import Site, fetch_sites
from .tiles import Depth, InundationMap, TileUnavailable, depth_label

MAX_SITES = 6
SAMPLE_EVERY_M = 15.0
END_SNAP_M = 80.0
"""OSRM snaps the destination to the nearest path; the route must still end this close to the site."""
AWAY_SLACK_M = 75.0
"""Inside the inundation area the path may run at most this far backward along the home-to-site axis."""
REENTRY_LIMIT_M = 100.0
DETOUR_FACTOR = 2.5
DETOUR_SLACK_M = 300.0
WALK_SPEED_MPS = 1.0
"""Conservative pace for children and older adults, as in the US route."""

RouteFailure = Literal["ends_away_from_site", "goes_deeper", "moves_away_from_site", "re_enters", "too_long"]


def _rank(depth: Depth) -> int:
    return -1 if depth is None else depth


def site_kind(depth: Depth) -> SiteKind:
    return "high_ground" if depth is None else "evacuation_building"


def check_route(home: LonLat, home_depth: Depth, site: LonLat, kind: SiteKind, path: Sequence[LonLat],
                distance_m: float, inundation: InundationMap) -> list[RouteFailure]:
    """Every invariant the path breaks. Empty means it may be shown. Raises TileUnavailable."""
    failures: list[RouteFailure] = []
    if geo.haversine_m(path[-1], site) > END_SNAP_M:
        failures.append("ends_away_from_site")
    straight = geo.haversine_m(home, site)
    if distance_m > DETOUR_FACTOR * straight + DETOUR_SLACK_M:
        failures.append("too_long")

    dense = geo.densify(path, SAMPLE_EVERY_M)
    depths = [inundation.depth(p) for p in dense]
    if any(_rank(d) > _rank(home_depth) for d in depths):
        failures.append("goes_deeper")

    frame = geo.LocalFrame(home)
    sx, sy = frame.to_xy(site)
    norm = math.hypot(sx, sy)
    if norm > 0 and any(d is not None and (x * sx + y * sy) / norm < -AWAY_SLACK_M
                        for (x, y), d in zip(map(frame.to_xy, dense), depths)):
        failures.append("moves_away_from_site")

    if kind == "high_ground":
        first_out = next((i for i, d in enumerate(depths) if d is None), None)
        if first_out is not None:
            back_in = sum(geo.haversine_m(dense[i - 1], dense[i])
                          for i in range(first_out + 1, len(dense)) if depths[i] is not None)
            if back_in > REENTRY_LIMIT_M:
                failures.append("re_enters")
    return failures


def evac_site(site: Site, depth: Depth, provenance: Provenance) -> EvacSite:
    kind = site_kind(depth)
    name, _ = rules.SOURCES["gsi_sites"]
    return EvacSite(name=site.name, address=site.address, lon=site.lon, lat=site.lat, kind=kind,
                    instruction=rules.HIGH_GROUND if kind == "high_ground" else rules.EVACUATION_BUILDING,
                    depth=depth_label(depth), remarks=site.remarks, source_name=name, source_url=site.source_url,
                    provenance=provenance)


def plan_evacuation(profile: BuildingProfile, transport: Transport, now: datetime) -> SiteRoute | NoCheckedRoute | NotInZone | None:
    """None when the inundation map was unavailable, so the UI can say so instead of guessing."""
    area = profile.hazard_area
    if area is None:
        return None
    if not area.contains_home:
        return NotInZone(reason=rules.NOT_IN_ZONE)
    home: LonLat = (profile.lon, profile.lat)
    fallback = NoCheckedRoute(reason=rules.NO_CHECKED_ROUTE, map_url=area.map_url)
    inundation = InundationMap(transport)
    try:
        home_depth = inundation.depth_near(home, EDGE_RADIUS_M)
        sites, sites_provenance = fetch_sites(transport, home)
        accepted: list[tuple[OsrmRoute, Provenance, EvacSite]] = []
        for site in sites[:MAX_SITES]:
            point = (site.lon, site.lat)
            depth = inundation.depth(point)
            got = fetch_route(transport, home, point)
            if got is None:
                continue
            route, provenance = got
            if check_route(home, home_depth, point, site_kind(depth), route.path, route.distance_m, inundation):
                continue
            accepted.append((route, provenance, evac_site(site, depth, weakest(sites_provenance, provenance))))
    except TileUnavailable:
        return fallback
    if not accepted:
        return fallback
    route, provenance, site = min(accepted, key=lambda a: a[0].distance_m)
    return SiteRoute(origin=home, destination=route.path[-1], site=site, path=route.path, steps=route.steps,
                     distance_m=route.distance_m, walk_min=route.distance_m / WALK_SPEED_MPS / 60,
                     home_depth=depth_label(home_depth),
                     computed_at=now, provenance=weakest(provenance, inundation.provenance(), sites_provenance))


def find_sites_as_shelters(origin: LonLat, household: Household, transport: Transport,
                           now: datetime) -> ShelterResult:
    """Designated tsunami sites outside the mapped inundation area, nearest walk first.

    These are evacuation sites, not stay-over shelters, and GSI lists no access data, so a wheelchair household
    gets none (fail closed, counted). Raises TileUnavailable when GSI does not answer.
    """
    inundation = InundationMap(transport)
    sites, provenance = fetch_sites(transport, origin)
    excluded = {"not_open": 0, "in_hazard_area": 0, "hazard_check_failed": 0, "not_wheelchair_accessible": 0}
    kept: list[Site] = []
    for site in sites:
        if household.wheelchair:
            excluded["not_wheelchair_accessible"] += 1
            continue
        try:
            depth = inundation.depth((site.lon, site.lat))
        except TileUnavailable:
            excluded["hazard_check_failed"] += 1
            continue
        if depth is not None:
            excluded["in_hazard_area"] += 1
        else:
            kept.append(site)
    kept = kept[:10]
    provenances = [provenance, *inundation.provenances]
    cells: list[float | None] = [None] * len(kept)
    table = fetch_table(transport, origin, [(s.lon, s.lat) for s in kept])
    if table is not None:
        cells, table_provenance = table
        provenances.append(table_provenance)
    matches = [_match(s, cell, origin, household) for s, cell in zip(kept, cells)]
    matches.sort(key=lambda m: m.walk_min)
    return ShelterResult(origin=origin, matches=matches, excluded=excluded, fetched_at=now, replay=False,
                         ranking="Designated tsunami evacuation sites, nearest walk first.",
                         provenance=weakest(*provenances))


def _match(site: Site, table_m: float | None, origin: LonLat, household: Household) -> ShelterMatch:
    shelter = Shelter(id=site.id, name=site.name, address=site.address, lon=site.lon, lat=site.lat,
                      status="Designated emergency evacuation site (tsunami)", capacity=None, residents=None,
                      ada=None, wheelchair=None, pets_code=None, source_url=site.source_url)
    if table_m is None:
        distance_m, method = geo.haversine_m(origin, (site.lon, site.lat)) * 1.4, "estimate"
    else:
        distance_m, method = table_m, "route"
    notes = ["An evacuation site, not a place to stay. Ask the city which shelter (指定避難所) opens after."]
    if site.remarks:
        notes.append(f"Municipal note: {site.remarks}")
    if household.pets:
        notes.append("No pet information. Ask the city about pets.")
    if household.medical:
        notes.append("GSI data does not show medical support.")
    return ShelterMatch(shelter=shelter, walk_min=distance_m / WALK_SPEED_MPS / 60, walk_method=method,
                        fill_ratio=None, notes=notes)

