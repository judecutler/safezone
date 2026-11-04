"""Address or point in Japan to BuildingProfile: Nominatim, the tsunami inundation raster, and OpenStreetMap."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..building import osm
from ..building.geocode import NOMINATIM_REVERSE_URL, NOMINATIM_URL, parse_geocode, parse_reverse
from ..shapes import BuildingFlag, BuildingProfile, FlagTone, Geocode, HazardArea, Provenance, Ring, weakest
from ..transport import HttpError, Transport, get_json
from .rules import SOURCES
from .tiles import TILE_TEMPLATE, Depth, InundationMap, TileUnavailable, depth_label

PORTAL_NAME, PORTAL_URL = SOURCES["portal_tiles"]
MAP_URL = "https://disaportal.gsi.go.jp/"
EDGE_RADIUS_M = 10.0
"""The home reads inside when any probe this close is coloured, so a building on the mapped edge counts."""


class OutsideJapan(LookupError):
    """The point reverse-geocodes to another country."""


def geocode_jp(transport: Transport, address: str) -> Geocode:
    params = {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "jp"}
    data, provenance = get_json(transport, NOMINATIM_URL, params)
    return parse_geocode(address, data, provenance)


def reverse_jp(transport: Transport, lon: float, lat: float) -> Geocode:
    params = {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "addressdetails": 1, "zoom": 18}
    data, provenance = get_json(transport, NOMINATIM_REVERSE_URL, params)
    if isinstance(data, dict) and (data.get("address") or {}).get("country_code") not in (None, "jp"):
        raise OutsideJapan(f"{lat},{lon}")
    return parse_reverse((lon, lat), data, provenance)


def _flag(tone: FlagTone, value: str, detail: str, provenance: Provenance) -> BuildingFlag:
    return BuildingFlag(kind="tsunami_zone", tone=tone, value=value, detail=detail, status=None,
                        source_name=PORTAL_NAME, source_url=PORTAL_URL, provenance=provenance)


def zone_flag(depth: Depth, provenance: Provenance) -> BuildingFlag:
    if depth is None:
        return _flag("ok", "Outside the mapped tsunami inundation area",
                     "The prefecture's tsunami inundation assumption does not reach this address. "
                     "It covers tsunamis only, not shaking or other hazards.", provenance)
    return _flag("alert", f"In the tsunami inundation area ({depth_label(depth)})",
                 "The prefecture's tsunami inundation assumption reaches this address. After strong or long "
                 "shaking, go on foot to high ground or a designated evacuation site right away.", provenance)


def unreachable_flag(provenance: Provenance) -> BuildingFlag:
    return _flag("unknown", "Tsunami map could not be reached",
                 "Check the Hazard Map Portal before relying on this plan.", provenance)


def _tsunami(transport: Transport, place: Geocode) -> tuple[BuildingFlag, HazardArea | None]:
    inundation = InundationMap(transport)
    try:
        depth = inundation.depth_near((place.lon, place.lat), EDGE_RADIUS_M)
    except TileUnavailable:
        return unreachable_flag(place.provenance), None
    provenance = weakest(place.provenance, inundation.provenance())
    # The raster has no polygons; route and shelter checks sample it directly (japan/evac.py).
    area = HazardArea(contains_home=depth is not None, polygons=[], land_polygons=[], county=None,
                      map_url=MAP_URL, source_url=TILE_TEMPLATE)
    return zone_flag(depth, provenance), area


def _osm(transport: Transport, place: Geocode) -> tuple[list[BuildingFlag], Ring | None]:
    point = (place.lon, place.lat)
    try:
        building, provenance = osm.fetch_building(transport, point)
    except (HttpError, ValueError):
        return [], None
    if building is None:
        return [], None
    return osm.building_flags(building, point, weakest(place.provenance, provenance)), building.footprint


def profile_for(place: Geocode, transport: Transport) -> BuildingProfile:
    with ThreadPoolExecutor(max_workers=2) as pool:
        tsunami = pool.submit(_tsunami, transport, place)
        mapped = pool.submit(_osm, transport, place)
        zone, area = tsunami.result()
        osm_flags, footprint = mapped.result()
    flags = [zone, *osm_flags]
    return BuildingProfile(address=place.query, display_name=place.display_name, lon=place.lon, lat=place.lat,
                           city=place.city, footprint=footprint, flags=flags, hazard_area=area,
                           provenance=weakest(*(f.provenance for f in flags), place.provenance))


def build_profile(address: str, transport: Transport) -> BuildingProfile:
    return profile_for(geocode_jp(transport, address), transport)


def build_profile_at(lon: float, lat: float, transport: Transport) -> BuildingProfile:
    return profile_for(reverse_jp(transport, lon, lat), transport)

