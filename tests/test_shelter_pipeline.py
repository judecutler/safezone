"""find_shelters against scripted FEMA and OSRM table answers."""
import json
from datetime import datetime, timezone

import pytest

from safezone import geo
from safezone.route.osrm import TABLE_BASE
from safezone.shapes import BuildingProfile, HazardArea, Household
from safezone.shelter import fema
from safezone.shelter.fema import LAYER_URL, parse_shelter, parse_yes_no
from safezone.shelter.pipeline import find_shelters
from safezone.transport import HttpError, Response

ORIGIN = (-122.5000, 37.7700)
FRAME = geo.LocalFrame(ORIGIN)
NOW = datetime(2026, 11, 3, 12, 30, tzinfo=timezone.utc)
NEVER_IN_HAZARD = lambda p: False  # noqa: E731


def ll(x, y):
    return FRAME.to_lonlat(x, y)


def feature(n, x_m, y_m=0.0, status="OPEN", capacity=100, population=10, wheelchair="Y", pets=None):
    lon, lat = ll(x_m, y_m)
    return {"objectid": n, "shelter_id": 100 + n, "shelter_name": f"Shelter {n}", "address": f"{n} Main St",
            "city": "Town", "state": "CA", "zip": "94000", "shelter_status": status,
            "evacuation_capacity": capacity, "post_impact_capacity": None, "total_population": population,
            "ada_compliant": "Y", "pet_accommodations_code": pets, "wheelchair_accessible": wheelchair,
            "latitude": lat, "longitude": lon}


def profile(polygons=()):
    return BuildingProfile(address="a", display_name="a", lon=ORIGIN[0], lat=ORIGIN[1], city=None, footprint=None,
                           flags=[], provenance="live",
                           hazard_area=HazardArea(contains_home=True, polygons=list(polygons), county=None,
                                                  map_url=None, source_url="u"))


class Scripted:
    """FEMA answers with `features`; the OSRM table answers with `table` (a dict, a Response, or a factor)."""

    def __init__(self, features, table=1.2, fema_status=200, provenance="live"):
        self.features = features
        self.table = table
        self.fema_status = fema_status
        self.provenance = provenance
        self.table_requests = 0

    def send(self, request):
        if request.url == LAYER_URL:
            body = json.dumps({"features": [{"attributes": f} for f in self.features]})
            return Response(self.fema_status, body if self.fema_status == 200 else "down", self.provenance)
        assert request.url.startswith(TABLE_BASE)
        self.table_requests += 1
        if isinstance(self.table, Response):
            return self.table
        points = [tuple(float(v) for v in c.split(",")) for c in request.url[len(TABLE_BASE):].split(";")]
        row = [0.0] + [geo.haversine_m(points[0], p) * self.table for p in points[1:]]
        return Response(200, json.dumps({"code": "Ok", "distances": [row]}), self.provenance)


def run(transport, household=Household(), hazard_check=NEVER_IN_HAZARD, polygons=(), replay=False):
    return find_shelters(ORIGIN, profile(polygons), household, transport, hazard_check, NOW, replay)


def test_each_exclusion_is_counted_and_nothing_excluded_is_shown():
    inside = [[ll(2900, -100), ll(3100, -100), ll(3100, 100), ll(2900, 100)]]
    features = [feature(1, 1000), feature(2, 2000, status="Closed"), feature(3, 3000),
                feature(4, 4000, wheelchair="N"), feature(5, 5000, wheelchair=None), feature(6, 6000)]

    def check(p):
        if abs(FRAME.to_xy(p)[0] - 6000) < 10:
            raise RuntimeError("point query timed out")
        return False

    result = run(Scripted(features), Household(wheelchair=True), check, polygons=[inside])
    assert [m.shelter.name for m in result.matches] == ["Shelter 1"]
    assert result.excluded == {"not_open": 1, "in_hazard_area": 1, "hazard_check_failed": 1,
                               "not_wheelchair_accessible": 2}


def test_without_a_wheelchair_need_unknown_access_is_kept():
    result = run(Scripted([feature(1, 1000, wheelchair=None)]))
    assert len(result.matches) == 1
    assert "Listed as wheelchair accessible." not in result.matches[0].notes


def test_hazard_check_true_excludes_and_a_shelter_inside_known_polygons_skips_the_query():
    asked = []

    def check(p):
        asked.append(p)
        return abs(FRAME.to_xy(p)[0] - 2000) < 10

    inside = [[ll(900, -100), ll(1100, -100), ll(1100, 100), ll(900, 100)]]
    result = run(Scripted([feature(1, 1000), feature(2, 2000), feature(3, 3000)]), hazard_check=check,
                 polygons=[inside])
    assert [m.shelter.name for m in result.matches] == ["Shelter 3"]
    assert result.excluded["in_hazard_area"] == 2
    assert len(asked) == 2


def test_only_the_25_nearest_open_shelters_are_considered():
    features = [feature(n, 500 * n) for n in range(1, 31)]
    result = run(Scripted(features))
    assert len(result.matches) == 25
    assert max(FRAME.to_xy((m.shelter.lon, m.shelter.lat))[0] for m in result.matches) == pytest.approx(12500, abs=1)


def test_nearly_full_near_shelter_ranks_after_half_full_far_one():
    features = [feature(1, 1000, capacity=100, population=85), feature(2, 5000, capacity=100, population=50)]
    result = run(Scripted(features))
    assert [m.shelter.name for m in result.matches] == ["Shelter 2", "Shelter 1"]
    assert result.matches[1].fill_ratio == pytest.approx(0.85)
    assert "Nearly full: about 85% of capacity, so shelters with more room rank first." in result.matches[1].notes
    assert result.matches[0].notes == []
    assert result.ranking == "Shelters that report room come first, then by walking time."


def test_unknown_occupancy_is_no_evidence_of_room_so_walk_time_decides_against_nearly_full():
    """An unreported occupancy never outranks a nearer, nearly full shelter: both lack reported room."""
    features = [feature(1, 1000, capacity=200, population=60), feature(2, 5000, capacity=None, population=12),
                feature(3, 3000, capacity=100, population=85), feature(4, 4000, capacity=0, population=5)]
    result = run(Scripted(features))
    assert [m.shelter.name for m in result.matches] == ["Shelter 1", "Shelter 3", "Shelter 4", "Shelter 2"]
    assert result.matches[3].fill_ratio is None
    assert "Capacity not reported, so shelters that report room rank first." in result.matches[3].notes
    assert result.matches[2].fill_ratio is None


def test_walk_time_comes_from_the_table_at_one_metre_per_second():
    result = run(Scripted([feature(1, 1200)], table=1.5))
    match = result.matches[0]
    assert match.walk_method == "route"
    assert match.walk_min == pytest.approx(1200 * 1.5 / 60, rel=1e-3)


def test_table_failure_or_null_cell_falls_back_to_an_estimate():
    down = run(Scripted([feature(1, 1200)], table=Response(599, "no response", "live")))
    assert down.matches[0].walk_method == "estimate"
    assert down.matches[0].walk_min == pytest.approx(1200 * 1.4 / 60, rel=1e-3)

    null_cell = json.dumps({"code": "Ok", "distances": [[0, None]]})
    partial = run(Scripted([feature(1, 1200)], table=Response(200, null_cell, "live")))
    assert partial.matches[0].walk_method == "estimate"


def test_no_table_request_when_nothing_is_kept():
    transport = Scripted([feature(1, 1000, status="CLOSED")])
    result = run(transport)
    assert result.matches == [] and transport.table_requests == 0
    assert result.excluded["not_open"] == 1


def test_household_notes_never_claim_a_match():
    household = Household(pets=True, medical=True, wheelchair=True)
    result = run(Scripted([feature(1, 1000, pets="PETS ACCEPTED"), feature(2, 2000)]), household)
    with_code, without = result.matches
    assert with_code.notes == ["Pet accommodation code: PETS ACCEPTED. Call ahead about pets.",
                               "Call ahead about medical needs. FEMA data does not show medical support.",
                               "Listed as wheelchair accessible."]
    assert without.notes[0] == "No pet information. Call ahead about pets."


def test_fema_down_raises_instead_of_an_empty_list():
    with pytest.raises(HttpError):
        run(Scripted([], fema_status=599))


def test_result_carries_origin_time_replay_and_weakest_provenance():
    result = run(Scripted([feature(1, 1000)], provenance="recorded"), replay=True)
    assert (result.origin, result.fetched_at, result.replay, result.provenance) == (ORIGIN, NOW, True, "recorded")


def test_parse_yes_no_and_capacity_fallback():
    assert [parse_yes_no(v) for v in ("Y", "yes", "TRUE", 1, "N", "no", "False", "0", "", "maybe", None)] == \
        [True, True, True, True, False, False, False, False, None, None, None]
    attrs = feature(1, 100) | {"evacuation_capacity": None, "post_impact_capacity": "250", "shelter_id": None}
    shelter = parse_shelter(attrs)
    assert shelter.capacity == 250 and shelter.id == "1" and shelter.source_url == fema.LAYER_URL
    assert shelter.address == "1 Main St, Town, CA, 94000"
    assert parse_shelter(attrs | {"latitude": None}) is None
