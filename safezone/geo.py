"""Small-area geodesy on (lon, lat) pairs. Pure functions, no dependencies.

Distances use a local equirectangular projection around a reference point,
which is accurate to well under 1% over the few kilometres a walking
evacuation spans.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from .shapes import LonLat, Polygon, Ring

EARTH_RADIUS_M = 6_371_008.8
COMPASS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")


def haversine_m(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_deg(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(bearing: float) -> str:
    return COMPASS[round(bearing / 45) % 8]


class LocalFrame:
    """Metres east/north of an origin. Round-trips (lon, lat) within the walking-distance range."""

    def __init__(self, origin: LonLat):
        self.lon0, self.lat0 = origin
        self.kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        self.ky = math.radians(1) * EARTH_RADIUS_M

    def to_xy(self, p: LonLat) -> tuple[float, float]:
        return ((p[0] - self.lon0) * self.kx, (p[1] - self.lat0) * self.ky)

    def to_lonlat(self, x: float, y: float) -> LonLat:
        return (self.lon0 + x / self.kx, self.lat0 + y / self.ky)


def point_in_ring(p: LonLat, ring: Ring) -> bool:
    x, y = p
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                inside = not inside
    return inside


def point_in_polygon(p: LonLat, polygon: Polygon) -> bool:
    if not polygon or not point_in_ring(p, polygon[0]):
        return False
    return not any(point_in_ring(p, hole) for hole in polygon[1:])


def point_in_any(p: LonLat, polygons: Iterable[Polygon]) -> bool:
    return any(point_in_polygon(p, poly) for poly in polygons)


def nearest_on_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return (ax + t * dx, ay + t * dy)


def boundary_edges(polygons: Sequence[Polygon]) -> Iterable[tuple[LonLat, LonLat]]:
    for poly in polygons:
        for ring in poly:
            for i in range(len(ring)):
                yield ring[i], ring[(i + 1) % len(ring)]


def distance_to_boundary_m(p: LonLat, polygons: Sequence[Polygon]) -> float:
    frame = LocalFrame(p)
    best = math.inf
    for a, b in boundary_edges(polygons):
        q = nearest_on_segment((0.0, 0.0), frame.to_xy(a), frame.to_xy(b))
        best = min(best, math.hypot(*q))
    return best


def path_length_m(path: Sequence[LonLat]) -> float:
    return sum(haversine_m(path[i], path[i + 1]) for i in range(len(path) - 1))


def densify(path: Sequence[LonLat], step_m: float) -> list[LonLat]:
    """Insert points so no gap exceeds step_m. Used to check a route against the hazard area along its length."""
    out: list[LonLat] = list(path[:1])
    for a, b in zip(path, path[1:]):
        n = max(1, math.ceil(haversine_m(a, b) / step_m))
        out.extend((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1))
    return out
