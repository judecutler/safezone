import json

import pytest

from safezone.building import softstory
from safezone.building.softstory import StreetAddress, normalize_address
from safezone.transport import Response


@pytest.mark.parametrize("text, expected", [
    ("1000 Great Highway, San Francisco, CA 94121", "1000 GREAT HWY"),
    ("1000 great hwy", "1000 GREAT HWY"),
    ("1000 Great Highway Apt 4, San Francisco", "1000 GREAT HWY"),
    ("1000 Great Highway #4", "1000 GREAT HWY"),
    ("1000 Great Highway 4", "1000 GREAT HWY"),
    ("742 47th Avenue Unit B", "742 47TH AVE"),
    ("1 Dr. Carlton B. Goodlett Place", "1 DR CARLTON B GOODLETT PL"),
    ("2130 Fulton Street", "2130 FULTON ST"),
    ("55 Avenue of the Palms", "55 AVENUE OF THE PALMS"),
    ("1350A Masonic Ave", "1350A MASONIC AVE"),
    ("998-1002 Great Hwy", "998-1002 GREAT HWY"),
])
def test_normalize_address(text, expected):
    a = normalize_address(text)
    assert a is not None
    number = f"{a.lo}{a.letter}" if a.lo == a.hi else f"{a.lo}-{a.hi}"
    assert f"{number} {a.street}" == expected


@pytest.mark.parametrize("text", ["Great Highway, San Francisco", "", "1000", "Pier 39"])
def test_normalize_rejects_addresses_without_number_and_street(text):
    assert normalize_address(text) is None


class Rows:
    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return Response(200, json.dumps(self.rows), "live")


def lookup(address, rows):
    t = Rows(rows)
    statuses, _ = softstory.lookup_sf(t, normalize_address(address))
    return statuses, dict(t.requests[0].params)


def test_like_match_on_a_longer_number_is_not_this_building():
    statuses, params = lookup("100 Great Highway", [
        {"property_address": "1000 GREAT HWY", "status": "Listed"},
        {"property_address": "2100 GREAT HWY", "status": "Listed"},
    ])
    assert statuses == []
    assert params["$where"] == "upper(property_address) like '%100 GREAT%'"


def test_exact_number_and_street_match():
    statuses, _ = lookup("1000 Great Highway, San Francisco", [
        {"property_address": "11000 GREAT HWY", "status": "A"},
        {"property_address": "1000 GREAT HIGHWAY", "status": "B"},
    ])
    assert statuses == ["B"]


def test_listed_range_covers_same_side_numbers_only():
    rows = [{"property_address": "998-1002 GREAT HWY", "status": "Listed"}]
    assert lookup("1000 Great Highway", rows)[0] == ["Listed"]
    assert lookup("999 Great Highway", rows)[0] == []


def test_apostrophe_is_escaped_in_the_query():
    _, params = lookup("10 O'Farrell Street", [])
    assert params["$where"] == "upper(property_address) like '%10 O''FARRELL%'"


SF = softstory.INVENTORIES["san francisco"]


@pytest.mark.parametrize("status, tone", [
    ("Work Complete, CFC Issued", "info"),
    ("Completed", "info"),
    ("Incomplete", "alert"),
    ("Not complete", "alert"),
    ("Permit Issued", "alert"),
    (None, "alert"),
])
def test_listed_building_tone_follows_city_status(status, tone):
    f = softstory.result_flag(SF, [status], "live")
    assert (f.tone, f.value, f.status) == (tone, "On San Francisco's soft-story list", status)


def test_open_work_wins_when_records_disagree():
    f = softstory.result_flag(SF, ["Work Complete", "Permit Issued"], "live")
    assert (f.tone, f.status) == ("alert", "Permit Issued")


def test_not_found_never_says_not_soft_story():
    f = softstory.result_flag(SF, [], "live")
    assert f.tone == "info"
    assert f.value == "Not found in San Francisco's soft-story list"
    assert "not proof" in f.detail


def test_other_cities_have_no_inventory():
    assert softstory.inventory_for("Oakland") is None
    assert softstory.inventory_for("san francisco") is SF
    f = softstory.no_inventory_flag("Oakland", "live")
    assert (f.tone, f.value) == ("unknown", "No soft-story inventory for Oakland")


def test_same_building_compares_parsed_addresses():
    a = StreetAddress(1000, 1000, "", "GREAT HWY")
    assert softstory.same_building(a, normalize_address("01000 Great Highway"))
    assert not softstory.same_building(a, normalize_address("1000A Great Highway"))


REAL_SF_ROWS = [
    {"block": "1829", "lot": "001", "parcel_number": "1829001", "property_address": "1401 24TH AV",
     "address": "1401 24TH AV, SAN FRANCISCO CA", "tier": "3", "status": "Work Complete, CFC Issued"},
    {"block": "1213", "lot": "10", "parcel_number": "121310", "property_address": "2267 HAYES ST",
     "address": "2267 HAYES ST, SAN FRANCISCO CA", "tier": "3", "status": "Work Complete, CFC Issued"},
]


def test_real_datasf_rows_match_typed_addresses():
    from safezone.building.softstory import is_complete, normalize_address, parse_sf

    avenue = normalize_address("1401 24th Avenue, San Francisco, CA 94122")
    assert avenue.query_text() == "1401 24TH"
    assert parse_sf(avenue, REAL_SF_ROWS) == ["Work Complete, CFC Issued"]
    assert parse_sf(normalize_address("2267 Hayes Street"), REAL_SF_ROWS) == ["Work Complete, CFC Issued"]
    assert parse_sf(normalize_address("1401 24th Street"), REAL_SF_ROWS) == []
    assert is_complete("Work Complete, CFC Issued")


def test_datasf_rows_without_a_suffix_or_with_stray_symbols_still_match():
    from safezone.building.softstory import parse_sf

    rows = [{"property_address": "1230 LA PLAYA *", "status": "Work Complete, CFC Issued"}]
    assert parse_sf(normalize_address("1230 La Playa Street, San Francisco"), rows) == ["Work Complete, CFC Issued"]
    assert parse_sf(normalize_address("1230 La Playa"), rows) == ["Work Complete, CFC Issued"]
    assert parse_sf(normalize_address("1230 La Playa Avenue"), [{"property_address": "1230 LA PLAYA ST", "status": "x"}]) == []
