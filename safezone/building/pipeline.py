"""Address or point to BuildingProfile: geocode (or reverse geocode), then the tsunami, soft-story and OpenStreetMap lookups in parallel."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..shapes import BuildingFlag, BuildingProfile, Geocode, HazardArea, Provenance, Ring, weakest
from ..transport import HttpError, Transport
from . import cgs, osm, softstory
from .geocode import geocode, reverse_geocode

SOURCE_FAILURES = (HttpError, ValueError)
"""A source that did not answer, or answered in a shape we cannot parse. Each degrades to its own unknown flag."""


def _tsunami(transport: Transport, place: Geocode) -> tuple[BuildingFlag, HazardArea | None]:
    if place.state != "California":
        return cgs.not_california_flag(place.provenance), None
    try:
        area, provenance = cgs.fetch_hazard_area(transport, (place.lon, place.lat))
    except SOURCE_FAILURES:
        return cgs.unreachable_flag(place.provenance), None
    return cgs.zone_flag(area, weakest(place.provenance, provenance)), area


def _soft_story(transport: Transport, place: Geocode) -> BuildingFlag:
    inventory = softstory.inventory_for(place.city)
    if inventory is None:
        return softstory.no_inventory_flag(place.city, place.provenance)
    address = softstory.normalize_address(place.query)
    if address is None:
        return softstory.unparsed_flag(inventory, place.provenance)
    try:
        statuses, provenance = inventory.lookup(transport, address)
    except SOURCE_FAILURES:
        return softstory.unreachable_flag(inventory, place.provenance)
    return softstory.result_flag(inventory, statuses, weakest(place.provenance, provenance))


def _osm(transport: Transport, place: Geocode) -> tuple[list[BuildingFlag], Ring | None]:
    point = (place.lon, place.lat)
    try:
        building, provenance = osm.fetch_building(transport, point)
    except SOURCE_FAILURES:
        return [], None
    if building is None:
        return [], None
    return osm.building_flags(building, point, weakest(place.provenance, provenance)), building.footprint


def build_profile(address: str, transport: Transport) -> BuildingProfile:
    return profile_for(geocode(transport, address), transport)


def build_profile_at(lon: float, lat: float, transport: Transport) -> BuildingProfile:
    return profile_for(reverse_geocode(transport, lon, lat), transport)


def profile_for(place: Geocode, transport: Transport) -> BuildingProfile:
    with ThreadPoolExecutor(max_workers=3) as pool:
        tsunami = pool.submit(_tsunami, transport, place)
        soft = pool.submit(_soft_story, transport, place)
        mapped = pool.submit(_osm, transport, place)
        zone_flag, hazard_area = tsunami.result()
        soft_flag = soft.result()
        osm_flags, footprint = mapped.result()
    flags = [zone_flag, soft_flag, *osm_flags]
    provenance: Provenance = weakest(*(f.provenance for f in flags), place.provenance)
    return BuildingProfile(address=place.query, display_name=place.display_name, lon=place.lon, lat=place.lat,
                           city=place.city, footprint=footprint, flags=flags, hazard_area=hazard_area,
                           provenance=provenance)
