"""Walking route out of the official tsunami hazard area.

Every route OSRM returns is checked along its densified length against the
hazard polygons before it is shown. A route that fails any check is never
returned; the fallback is a compass direction toward the nearest exit point
we have evidence for.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

import numpy as np

from .. import geo, rules
from ..shapes import BuildingProfile, DirectionOnly, EvacRoute, LonLat, NotInZone, Polygon, Provenance, WalkingRoute, weakest
from ..transport import Transport
from .osrm import OsrmRoute, fetch_route

CANDIDATE_RADIUS_M = 3000.0
SAMPLE_EVERY_M = 50.0
CLEARANCE_M = 100.0
"""A destination must sit this far outside every hazard polygon."""
PUSH_LIMIT_M = 400.0
PUSH_STEP_M = 10.0
MAX_CANDIDATES = 5
CANDIDATE_SPACING_M = 150.0

END_CLEARANCE_M = 50.0
"""OSRM snaps the destination to the nearest road, which may land back inside; the snapped end must still clear the boundary by this."""
DEEPER_SLACK_M = 75.0
"""Inside the hazard area the path may be at most this much farther from the boundary than home is."""
AWAY_SLACK_M = 75.0
"""Inside the hazard area the path may travel at most this far backward along the home-to-exit axis.
Distance to the nearest boundary edge cannot see a seaward leg when the polygon's seaward edge is the shoreline,
because walking toward the water shrinks that distance. This check does."""
REENTRY_LIMIT_M = 100.0
DENSIFY_STEP_M = 10.0
WALK_SPEED_MPS = 1.0
"""Conservative pace for children and older adults."""

DIRECTION_ONLY_REASON = "No walking route passed SafeZone's checks. Head {compass}, inland and uphill, on foot."

RouteFailure = Literal["ends_inside", "goes_deeper", "moves_away_from_exit", "re_enters"]

XY = tuple[float, float]


class Boundary:
    """The hazard polygons as edge arrays in a metre frame around home, so thousands of probes stay cheap.

    Containment is the even-odd rule per polygon, which equals `geo.point_in_polygon` for well-formed rings.
    """

    def __init__(self, home: LonLat, polygons: Sequence[Polygon]):
        self.frame = geo.LocalFrame(home)
        self.rings: list[list[XY]] = []
        starts: list[XY] = []
        ends: list[XY] = []
        owner: list[int] = []
        for i, polygon in enumerate(polygons):
            for ring in polygon:
                xy = [self.frame.to_xy(p) for p in ring]
                self.rings.append(xy)
                for j in range(len(xy)):
                    starts.append(xy[j])
                    ends.append(xy[(j + 1) % len(xy)])
                    owner.append(i)
        a = np.array(starts, dtype=float).reshape(-1, 2)
        b = np.array(ends, dtype=float).reshape(-1, 2)
        self.ax, self.ay = a[:, 0], a[:, 1]
        self.bx, self.by = b[:, 0], b[:, 1]
        self.dx, self.dy = self.bx - self.ax, self.by - self.ay
        len2 = self.dx * self.dx + self.dy * self.dy
        self.len2 = np.where(len2 == 0, 1.0, len2)
        self.owner = np.array(owner, dtype=int)
        self.polygon_count = len(polygons)

    def inside(self, p: XY) -> bool:
        x, y = p
        straddles = (self.ay > y) != (self.by > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_cross = self.ax + (y - self.ay) * self.dx / self.dy
        hits = straddles & (x < x_cross)
        crossings = np.bincount(self.owner[hits], minlength=self.polygon_count)
        return bool((crossings % 2).any())

    def nearest(self, p: XY) -> XY:
        x, y = p
        t = np.clip(((x - self.ax) * self.dx + (y - self.ay) * self.dy) / self.len2, 0.0, 1.0)
        qx, qy = self.ax + t * self.dx, self.ay + t * self.dy
        k = int(np.argmin((qx - x) ** 2 + (qy - y) ** 2))
        return (float(qx[k]), float(qy[k]))

    def distance(self, p: XY) -> float:
        return math.dist(p, self.nearest(p))

    def clear(self, p: XY, margin: float) -> bool:
        return self.distance(p) >= margin and not self.inside(p)

    def ring_points(self, every_m: float, within_m: float) -> list[XY]:
        """Points every `every_m` along each ring, plus each long edge's nearest point to home, all within `within_m`."""
        out: list[XY] = [self.nearest((0.0, 0.0))]
        for ring in self.rings:
            walked = 0.0
            for a, b in zip(ring, ring[1:] + ring[:1]):
                length = math.dist(a, b)
                if length == 0:
                    continue
                if length >= every_m:
                    out.append(geo.nearest_on_segment((0.0, 0.0), a, b))
                while walked <= length:
                    t = walked / length
                    out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                    walked += every_m
                walked -= length
        return [p for p in out if math.hypot(*p) <= within_m]


def candidate_destinations(home: LonLat, polygons: Sequence[Polygon]) -> list[LonLat]:
    """Up to MAX_CANDIDATES points at least CLEARANCE_M outside every polygon, nearest first, CANDIDATE_SPACING_M apart."""
    boundary = Boundary(home, polygons)
    pushed = [_push_outward(boundary, p) for p in boundary.ring_points(SAMPLE_EVERY_M, CANDIDATE_RADIUS_M)]
    pushed = sorted(_dedupe([p for p in pushed if p is not None]), key=lambda p: math.hypot(*p))
    chosen: list[XY] = []
    for p in pushed:
        if len(chosen) == MAX_CANDIDATES:
            break
        if all(math.dist(p, c) >= CANDIDATE_SPACING_M for c in chosen):
            chosen.append(p)
    return [boundary.frame.to_lonlat(*p) for p in chosen]


def _dedupe(points: list[XY]) -> list[XY]:
    return list({(round(x, 1), round(y, 1)): (x, y) for x, y in points}.values())


def _push_outward(boundary: Boundary, xy: XY) -> XY | None:
    r = math.hypot(*xy)
    if r == 0:
        return None
    ux, uy = xy[0] / r, xy[1] / r
    for k in range(int(PUSH_LIMIT_M // PUSH_STEP_M) + 1):
        p = (xy[0] + ux * k * PUSH_STEP_M, xy[1] + uy * k * PUSH_STEP_M)
        if boundary.clear(p, CLEARANCE_M):
            return p
    return None


def check_route(home: LonLat, path: Sequence[LonLat], polygons: Sequence[Polygon]) -> list[RouteFailure]:
    """Every invariant the path breaks. Empty means the route may be shown."""
    boundary = Boundary(home, polygons)
    dense = [boundary.frame.to_xy(p) for p in geo.densify(path, DENSIFY_STEP_M)]
    inside = [boundary.inside(p) for p in dense]
    failures: list[RouteFailure] = []

    end = dense[-1]
    if inside[-1] or boundary.distance(end) < END_CLEARANCE_M:
        failures.append("ends_inside")

    home_depth = boundary.distance((0.0, 0.0))
    if any(flag and boundary.distance(p) > home_depth + DEEPER_SLACK_M for p, flag in zip(dense, inside)):
        failures.append("goes_deeper")

    norm = math.hypot(*end)
    if norm > 0:
        ux, uy = end[0] / norm, end[1] / norm
        if any(flag and x * ux + y * uy < -AWAY_SLACK_M for (x, y), flag in zip(dense, inside)):
            failures.append("moves_away_from_exit")

    first_out = next((i for i, flag in enumerate(inside) if not flag), None)
    if first_out is not None:
        re_entered = sum(math.dist(dense[i - 1], dense[i]) for i in range(first_out + 1, len(dense)) if inside[i])
        if re_entered > REENTRY_LIMIT_M:
            failures.append("re_enters")
    return failures


def plan_route(profile: BuildingProfile, transport: Transport, now: datetime) -> EvacRoute | None:
    """None when the hazard map was unavailable, so the UI can say so instead of guessing."""
    area = profile.hazard_area
    if area is None:
        return None
    if not area.contains_home:
        return NotInZone(reason=rules.NOT_IN_ZONE)
    if not area.polygons:
        return None
    home: LonLat = (profile.lon, profile.lat)
    polygons = area.polygons

    candidates = candidate_destinations(home, polygons)
    accepted: list[tuple[OsrmRoute, Provenance]] = []
    land_exits: list[LonLat] = []
    provenances: list[Provenance] = []
    for candidate in candidates:
        got = fetch_route(transport, home, candidate)
        if got is None:
            continue
        route, provenance = got
        provenances.append(provenance)
        failures = check_route(home, route.path, polygons)
        if "ends_inside" not in failures:
            land_exits.append(route.path[-1])
        if not failures:
            accepted.append((route, provenance))

    if accepted:
        route, _ = min(accepted, key=lambda rp: rp[0].distance_m)
        return WalkingRoute(origin=home, destination=route.path[-1], path=route.path, steps=route.steps,
                            distance_m=route.distance_m, walk_min=route.distance_m / WALK_SPEED_MPS / 60,
                            computed_at=now, provenance=weakest(*provenances))

    # A road endpoint OSRM reached that cleared the boundary is proof of land outside the zone.
    # A geometric candidate is not: pushing outward through a shoreline edge lands in the water.
    target = (_nearest(home, land_exits) or _nearest(home, candidates)
              or _nearest_boundary_pushed(home, polygons))
    bearing = geo.bearing_deg(home, target)
    compass = geo.compass(bearing)
    return DirectionOnly(origin=home, destination=target, bearing_deg=bearing, compass=compass,
                         straight_m=geo.haversine_m(home, target),
                         reason=DIRECTION_ONLY_REASON.format(compass=compass),
                         computed_at=now, provenance=weakest(*provenances))


def _nearest(home: LonLat, points: Sequence[LonLat]) -> LonLat | None:
    return min(points, key=lambda p: geo.haversine_m(home, p), default=None)


def _nearest_boundary_pushed(home: LonLat, polygons: Sequence[Polygon]) -> LonLat:
    boundary = Boundary(home, polygons)
    qx, qy = boundary.nearest((0.0, 0.0))
    r = math.hypot(qx, qy) or 1.0
    scale = (r + CLEARANCE_M) / r
    return boundary.frame.to_lonlat(qx * scale, qy * scale)
