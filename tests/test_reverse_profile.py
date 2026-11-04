"""A phone's GPS point to the same BuildingProfile an address gives."""
import json

import pytest

from safezone.building.geocode import NOMINATIM_REVERSE_URL, GeocodeNotFound
from safezone.building.pipeline import build_profile, build_profile_at
from safezone.transport import LiveTransport, Request, Response
from tools.samples import building as samples
from tools.samples.geo import DEMO_ADDRESS, DEMO_HOME, OUTSIDE_HOME


class Counting:
    def __init__(self, inner):
        self.inner, self.requests = inner, []

    def send(self, request):
        self.requests.append(request)
        return self.inner.send(request)


def test_a_point_at_the_demo_home_gives_the_same_flags_as_its_address():
    by_point = build_profile_at(*DEMO_HOME, samples.SampleTransport())
    by_address = build_profile(DEMO_ADDRESS, samples.SampleTransport())
    assert [(f.kind, f.tone) for f in by_point.flags] == [(f.kind, f.tone) for f in by_address.flags]
    assert by_point.hazard_area is not None and by_point.hazard_area.contains_home


def test_the_profile_keeps_the_phones_own_point():
    lon, lat = DEMO_HOME[0] + 0.0004, DEMO_HOME[1]
    p = build_profile_at(lon, lat, samples.SampleTransport())
    assert (p.lon, p.lat) == (lon, lat)
    assert p.address.startswith("1000 Great Highway, San Francisco")


def test_a_point_outside_the_zone_reads_outside():
    p = build_profile_at(*OUTSIDE_HOME, samples.SampleTransport())
    assert next(f for f in p.flags if f.kind == "tsunami_zone").tone == "ok"


def test_a_point_nominatim_cannot_place_is_not_found():
    with pytest.raises(GeocodeNotFound):
        build_profile_at(-140.0, 30.0, samples.SampleTransport())


def test_the_reverse_lookup_is_one_nominatim_call():
    t = Counting(samples.SampleTransport())
    build_profile_at(*DEMO_HOME, t)
    assert [r.url for r in t.requests].count(NOMINATIM_REVERSE_URL) == 1


def test_live_reverse_lookups_are_paced_like_search():
    assert LiveTransport().min_interval_s.get("nominatim.openstreetmap.org", 0) >= 1.0
    assert NOMINATIM_REVERSE_URL.startswith("https://nominatim.openstreetmap.org/")


def test_a_reverse_answer_without_a_road_still_profiles():
    class NoRoad:
        def send(self, request: Request) -> Response:
            if request.url == NOMINATIM_REVERSE_URL:
                return Response(200, json.dumps({"lat": "37.77", "lon": "-122.51", "display_name": "Ocean Beach",
                                                 "address": {"city": "San Francisco", "state": "California"}}), "live")
            return samples.SampleTransport().send(request)

    p = build_profile_at(*DEMO_HOME, NoRoad())
    assert p.address == "Ocean Beach"
