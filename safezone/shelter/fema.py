"""FEMA National Shelter System open-shelters layer. ArcGIS JSON in, `Shelter` out."""
from __future__ import annotations

from typing import Any

from ..shapes import LonLat, Provenance, Shelter
from ..transport import Transport, get_json

LAYER_URL = "https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query"
DEFAULT_RADIUS_M = 25_000

YES = {"Y", "YES", "TRUE", "1"}
NO = {"N", "NO", "FALSE", "0"}


def fetch_shelters(transport: Transport, origin: LonLat,
                   radius_m: int = DEFAULT_RADIUS_M) -> tuple[list[Shelter], Provenance]:
    """Raises HttpError when FEMA does not answer; the caller shows an honest unavailable state."""
    data, provenance = get_json(transport, LAYER_URL, {
        "geometry": f"{origin[0]:.6f},{origin[1]:.6f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    })
    return parse_shelters(data), provenance


def parse_shelters(data: Any) -> list[Shelter]:
    out = []
    for feature in data.get("features", []):
        shelter = parse_shelter(feature.get("attributes", {}))
        if shelter is not None:
            out.append(shelter)
    return out


def parse_shelter(a: dict[str, Any]) -> Shelter | None:
    lon, lat = _number(a.get("longitude")), _number(a.get("latitude"))
    if lon is None or lat is None:
        return None
    shelter_id = a.get("shelter_id") or a.get("objectid")
    if shelter_id is None:
        return None
    address = ", ".join(str(part) for part in (a.get("address"), a.get("city"), a.get("state"), a.get("zip")) if part)
    capacity = _int(a.get("evacuation_capacity"))
    if capacity is None:
        capacity = _int(a.get("post_impact_capacity"))
    return Shelter(
        id=str(shelter_id),
        name=str(a.get("shelter_name") or "Unnamed shelter"),
        address=address,
        lon=lon,
        lat=lat,
        status=str(a.get("shelter_status") or ""),
        capacity=capacity,
        residents=_int(a.get("total_population")),
        ada=parse_yes_no(a.get("ada_compliant")),
        wheelchair=parse_yes_no(a.get("wheelchair_accessible")),
        pets_code=_text(a.get("pet_accommodations_code")),
        source_url=LAYER_URL,
    )


def parse_yes_no(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in YES:
        return True
    if text in NO:
        return False
    return None


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    n = _number(value)
    return None if n is None else int(n)


def _text(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None
