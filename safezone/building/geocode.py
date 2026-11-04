"""Address to point, and point to address, through Nominatim (OpenStreetMap)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ..shapes import Geocode, Provenance
from ..transport import Transport, get_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


class GeocodeNotFound(LookupError):
    pass


class _Hit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lat: float
    lon: float
    display_name: str
    address: dict[str, str] = {}


def _city(a: dict[str, str]) -> str | None:
    return a.get("city") or a.get("town") or a.get("village")


def parse_geocode(query: str, data: Any, provenance: Provenance) -> Geocode:
    if not isinstance(data, list) or not data:
        raise GeocodeNotFound(query)
    hit = _Hit.model_validate(data[0])
    a = hit.address
    return Geocode(query=query, display_name=hit.display_name, lon=hit.lon, lat=hit.lat,
                   city=_city(a), state=a.get("state"), provenance=provenance)


def geocode(transport: Transport, address: str) -> Geocode:
    params = {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "us"}
    data, provenance = get_json(transport, NOMINATIM_URL, params)
    return parse_geocode(address, data, provenance)


def street_address(a: dict[str, str]) -> str | None:
    """A one-line postal address from Nominatim's parts, or None when it has no road."""
    road = a.get("road")
    if not road:
        return None
    street = f"{a['house_number']} {road}" if a.get("house_number") else road
    tail = " ".join(p for p in (a.get("state"), a.get("postcode")) if p)
    return ", ".join(p for p in (street, _city(a), tail) if p)


def parse_reverse(point: tuple[float, float], data: Any, provenance: Provenance) -> Geocode:
    """Keeps the phone's own point: Nominatim answers with the nearest mapped object, which can sit metres away."""
    if not isinstance(data, dict) or "error" in data:
        raise GeocodeNotFound(f"{point[1]},{point[0]}")
    try:
        hit = _Hit.model_validate(data)
    except ValidationError as exc:
        raise GeocodeNotFound(f"{point[1]},{point[0]}") from exc
    a = hit.address
    return Geocode(query=street_address(a) or hit.display_name, display_name=hit.display_name,
                   lon=point[0], lat=point[1], city=_city(a), state=a.get("state"), provenance=provenance)


def reverse_geocode(transport: Transport, lon: float, lat: float) -> Geocode:
    params = {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "addressdetails": 1, "zoom": 18}
    data, provenance = get_json(transport, NOMINATIM_REVERSE_URL, params)
    return parse_reverse((lon, lat), data, provenance)
