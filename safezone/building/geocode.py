"""Address to point through Nominatim (OpenStreetMap)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ..shapes import Geocode, Provenance
from ..transport import Transport, get_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class GeocodeNotFound(LookupError):
    pass


class _Hit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lat: float
    lon: float
    display_name: str
    address: dict[str, str] = {}


def parse_geocode(query: str, data: Any, provenance: Provenance) -> Geocode:
    if not isinstance(data, list) or not data:
        raise GeocodeNotFound(query)
    hit = _Hit.model_validate(data[0])
    a = hit.address
    return Geocode(query=query, display_name=hit.display_name, lon=hit.lon, lat=hit.lat,
                   city=a.get("city") or a.get("town") or a.get("village"), state=a.get("state"),
                   provenance=provenance)


def geocode(transport: Transport, address: str) -> Geocode:
    params = {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "us"}
    data, provenance = get_json(transport, NOMINATIM_URL, params)
    return parse_geocode(address, data, provenance)
