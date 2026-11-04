"""California Geological Survey tsunami hazard area (ArcGIS FeatureServer)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ..geo import point_in_ring
from ..shapes import BuildingFlag, FlagTone, HazardArea, LonLat, Polygon, Provenance, Ring, weakest
from ..transport import Transport, get_json

LAYER_URL = "https://gis.conservation.ca.gov/server/rest/services/CGS/IW_Tsunami_Hazard_Area/FeatureServer/0"
QUERY_URL = f"{LAYER_URL}/query"
MAPS_PAGE = "https://www.conservation.ca.gov/cgs/tsunami/maps"
SOURCE_NAME = "California Geological Survey: Tsunami Hazard Area map"
ENVELOPE_DEG = 0.05
OUT_FIELDS = "Evacuate,County,Map_Link"


class IncompleteHazardArea(ValueError):
    """The service truncated the polygons, so any route or shelter check against them could be wrong."""


class _Attributes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    Evacuate: str | None = None
    County: str | None = None
    Map_Link: str | None = None


class _Geometry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rings: list[list[tuple[float, float]]] = []


class _Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attributes: _Attributes
    geometry: _Geometry | None = None


class _FeatureSet(BaseModel):
    # `features` is required: ArcGIS reports query errors as HTTP 200 with an `error` object instead.
    model_config = ConfigDict(extra="ignore")
    features: list[_Feature]
    exceededTransferLimit: bool = False


def _is_hazard(f: _Feature) -> bool:
    return (f.attributes.Evacuate or "").startswith("Yes")


def parse_point(data: Any) -> tuple[bool, str | None, str | None]:
    """(inside, county, map_link) from a point query. The layer holds both Yes and No polygons."""
    features = _FeatureSet.model_validate(data).features
    hits = [f for f in features if _is_hazard(f)]
    chosen = hits[0] if hits else (features[0] if features else None)
    if chosen is None:
        return False, None, None
    return bool(hits), chosen.attributes.County, chosen.attributes.Map_Link


def signed_area(ring: Ring) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])) / 2


def group_rings(rings: list[Ring]) -> list[Polygon]:
    """Esri rings to polygons: clockwise rings are outers, counter-clockwise rings are holes."""
    outers: list[Polygon] = []
    holes: list[Ring] = []
    for ring in rings:
        if signed_area(ring) < 0:
            outers.append([ring])
        else:
            holes.append(ring)
    for hole in holes:
        # A hole with no containing outer is dropped, which only ever enlarges the hazard area.
        owner = next((p for p in outers if point_in_ring(hole[0], p[0])), None)
        if owner is not None:
            owner.append(hole)
    return outers


def parse_polygons(data: Any) -> list[Polygon]:
    fs = _FeatureSet.model_validate(data)
    if fs.exceededTransferLimit:
        raise IncompleteHazardArea("CGS returned a truncated polygon set")
    polygons: list[Polygon] = []
    for f in fs.features:
        if _is_hazard(f) and f.geometry:
            polygons.extend(group_rings([[tuple(p) for p in r] for r in f.geometry.rings]))
    return polygons


def _point_query(transport: Transport, point: LonLat) -> tuple[Any, Provenance]:
    return get_json(transport, QUERY_URL, {
        "geometry": f"{point[0]},{point[1]}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": OUT_FIELDS, "returnGeometry": "false", "f": "json",
    })


def in_hazard_area(transport: Transport, point: LonLat) -> bool:
    data, _ = _point_query(transport, point)
    return parse_point(data)[0]


def fetch_hazard_area(transport: Transport, home: LonLat) -> tuple[HazardArea, Provenance]:
    point_data, p1 = _point_query(transport, home)
    inside, county, map_link = parse_point(point_data)
    lon, lat = home
    envelope = f"{lon - ENVELOPE_DEG},{lat - ENVELOPE_DEG},{lon + ENVELOPE_DEG},{lat + ENVELOPE_DEG}"
    poly_data, p2 = get_json(transport, QUERY_URL, {
        "geometry": envelope, "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "where": "Evacuate LIKE 'Yes%'", "returnGeometry": "true",
        "outSR": 4326, "maxAllowableOffset": 0.00005, "outFields": OUT_FIELDS, "f": "json",
    })
    area = HazardArea(contains_home=inside, polygons=parse_polygons(poly_data), county=county,
                      map_url=map_link or MAPS_PAGE, source_url=LAYER_URL)
    return area, weakest(p1, p2)


def _flag(tone: FlagTone, value: str, detail: str, url: str, provenance: Provenance) -> BuildingFlag:
    return BuildingFlag(kind="tsunami_zone", tone=tone, value=value, detail=detail, status=None,
                        source_name=SOURCE_NAME, source_url=url, provenance=provenance)


def zone_flag(area: HazardArea, provenance: Provenance) -> BuildingFlag:
    url = area.map_url or MAPS_PAGE
    if area.contains_home:
        return _flag("alert", "In the tsunami hazard area",
                     "California's official tsunami hazard map includes this address. "
                     "After strong or long shaking, leave on foot right away.", url, provenance)
    return _flag("ok", "Outside the mapped tsunami hazard area",
                 "California's official tsunami hazard map does not include this address. "
                 "This map covers tsunamis only, not shaking or other hazards.", url, provenance)


def not_california_flag(provenance: Provenance) -> BuildingFlag:
    return _flag("unknown", "No tsunami map for this state",
                 "SafeZone uses California's official map and has none for this location.", MAPS_PAGE, provenance)


def unreachable_flag(provenance: Provenance) -> BuildingFlag:
    return _flag("unknown", "Tsunami map could not be reached",
                 "Check the official map before relying on this plan.", MAPS_PAGE, provenance)
