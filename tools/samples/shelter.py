"""Hand-authored FEMA open-shelters stand-in for the demo. Six obviously synthetic shelters east of DEMO_HOME.

Each exercises one filter or note: F sits inside SAMPLE_HAZARD_RING, D is not wheelchair accessible,
B is 85% full, C reports no capacity, E is closed.
"""
from __future__ import annotations

import json

from safezone.shelter.fema import LAYER_URL
from safezone.transport import Request, Response
from tools.samples.geo import DEMO_HOME

DEG_PER_KM_EAST = 1 / 87.9


def _east(km: float, lat_offset: float = 0.0) -> tuple[float, float]:
    return (round(DEMO_HOME[0] + km * DEG_PER_KM_EAST, 5), round(DEMO_HOME[1] + lat_offset, 5))


def _shelter(n: int, letter: str, lon: float, lat: float, status: str, capacity: int | None, population: int,
             wheelchair: str, pets: str | None) -> dict:
    return {
        "objectid": n,
        "shelter_id": 900000 + n,
        "shelter_name": f"Sample Shelter {letter}",
        "address": "Sample address",
        "city": "San Francisco",
        "state": "CA",
        "zip": "94121",
        "shelter_status": status,
        "evacuation_capacity": capacity,
        "post_impact_capacity": None,
        "total_population": population,
        "hours_open": "00:00",
        "hours_close": "23:59",
        "org_name": "Sample Relief Org",
        "ada_compliant": "Y",
        "pet_accommodations_code": pets,
        "wheelchair_accessible": wheelchair,
        "latitude": lat,
        "longitude": lon,
    }


SHELTERS = [
    _shelter(1, "A", *_east(1.2, 0.0020), "OPEN", 200, 60, "Y", "PETS ACCEPTED"),
    _shelter(2, "B", *_east(2.5, -0.0015), "OPEN", 100, 85, "Y", None),
    _shelter(3, "C", *_east(4.0, 0.0030), "OPEN", None, 12, "Y", None),
    _shelter(4, "D", *_east(5.5, -0.0040), "OPEN", 300, 40, "N", "PETS ACCEPTED"),
    _shelter(5, "E", *_east(8.0, 0.0010), "CLOSED", 250, 0, "Y", None),
    _shelter(6, "F", -122.5115, 37.7620, "OPEN", 150, 20, "Y", None),
]


def respond(request: Request) -> Response | None:
    if request.url != LAYER_URL:
        return None
    body = {"objectIdFieldName": "objectid", "features": [{"attributes": s} for s in SHELTERS]}
    return Response(200, json.dumps(body), "sample")
