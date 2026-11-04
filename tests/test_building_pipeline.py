import json
from dataclasses import dataclass, field
from collections.abc import Callable

import pytest

from safezone.building import cgs, osm, softstory
from safezone.building.geocode import NOMINATIM_URL, GeocodeNotFound
from safezone.building.pipeline import build_profile
from safezone.transport import RecordingTransport, ReplayTransport, Request, Response
from tools.samples import building as samples
from tools.samples.geo import DEMO_ADDRESS, OUTSIDE_ADDRESS


@dataclass
class Patched:
    """The building samples, with chosen endpoints answered differently."""
    overrides: dict[str, Callable[[Request], Response]] = field(default_factory=dict)

    def send(self, request: Request) -> Response:
        if request.url in self.overrides:
            return self.overrides[request.url](request)
        return samples.SampleTransport().send(request)


def answer(body, status=200):
    return lambda _req: Response(status, json.dumps(body), "live")


def flag(profile, kind):
    return next(f for f in profile.flags if f.kind == kind)


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    recorder = RecordingTransport(samples.SampleTransport(), d, provenance="sample")
    for address in (DEMO_ADDRESS, OUTSIDE_ADDRESS):
        build_profile(address, recorder)
    return ReplayTransport(d)


def test_demo_address_replays_offline_with_sourced_flags(replay):
    p = build_profile(DEMO_ADDRESS, replay)
    assert [f.kind for f in p.flags] == ["tsunami_zone", "soft_story", "storeys"]
    assert flag(p, "tsunami_zone").tone == "alert"
    assert flag(p, "tsunami_zone").value == "In the tsunami hazard area"
    assert flag(p, "soft_story").value == "Not found in San Francisco's soft-story list"
    assert flag(p, "storeys").value == "2 storeys"
    assert p.hazard_area and p.hazard_area.contains_home and len(p.hazard_area.polygons) == 1
    assert p.footprint and len(p.footprint) >= 4
    assert p.provenance == "sample"
    assert all(f.source_name and f.source_url.startswith("https://") and f.provenance == "sample" for f in p.flags)


def test_outside_address_replays_offline(replay):
    p = build_profile(OUTSIDE_ADDRESS, replay)
    assert [f.kind for f in p.flags] == ["tsunami_zone", "soft_story"]
    assert flag(p, "tsunami_zone").tone == "ok"
    assert flag(p, "tsunami_zone").value == "Outside the mapped tsunami hazard area"
    assert p.hazard_area is not None and not p.hazard_area.contains_home
    assert p.footprint is None


def test_unknown_address_raises():
    with pytest.raises(GeocodeNotFound):
        build_profile("1 Nowhere Lane, Atlantis", samples.SampleTransport())


def test_not_california_skips_the_tsunami_map_and_soft_story_list():
    oregon = answer([{"lat": "45.5", "lon": "-123.9", "display_name": "Cannon Beach, Oregon",
                      "address": {"city": "Cannon Beach", "state": "Oregon"}}])
    p = build_profile("100 Ocean Ave, Cannon Beach, OR", Patched({NOMINATIM_URL: oregon}))
    zone, soft = flag(p, "tsunami_zone"), flag(p, "soft_story")
    assert (zone.tone, zone.value) == ("unknown", "No tsunami map for this state")
    assert p.hazard_area is None
    assert (soft.tone, soft.value) == ("unknown", "No soft-story inventory for Cannon Beach")
    assert "not soft-story" not in soft.value.lower()


@pytest.mark.parametrize("cgs_answer", [
    answer({}, status=503),
    answer({"error": {"code": 400, "message": "Unable to complete operation."}}),
])
def test_tsunami_map_failure_reads_unknown(cgs_answer):
    p = build_profile(DEMO_ADDRESS, Patched({cgs.QUERY_URL: cgs_answer}))
    zone = flag(p, "tsunami_zone")
    assert (zone.tone, zone.value) == ("unknown", "Tsunami map could not be reached")
    assert zone.source_url == cgs.MAPS_PAGE
    assert p.hazard_area is None
    assert flag(p, "soft_story").tone == "info"


def test_truncated_polygons_make_the_area_unknown_not_wrong():
    def truncated(req):
        resp = samples.respond(req)
        if dict(req.params)["geometryType"] == "esriGeometryEnvelope":
            body = json.loads(resp.text) | {"exceededTransferLimit": True}
            return Response(200, json.dumps(body), "sample")
        return resp

    p = build_profile(DEMO_ADDRESS, Patched({cgs.QUERY_URL: truncated}))
    assert flag(p, "tsunami_zone").value == "Tsunami map could not be reached"
    assert p.hazard_area is None


def test_point_query_decides_even_when_polygons_disagree():
    def no_polygons(req):
        if dict(req.params)["geometryType"] == "esriGeometryEnvelope":
            return Response(200, json.dumps({"features": []}), "live")
        return samples.respond(req)

    p = build_profile(DEMO_ADDRESS, Patched({cgs.QUERY_URL: no_polygons}))
    assert flag(p, "tsunami_zone").tone == "alert"


def test_soft_story_failure_reads_unknown():
    p = build_profile(DEMO_ADDRESS, Patched({softstory.SF_ENDPOINT: answer({}, status=599)}))
    soft = flag(p, "soft_story")
    assert (soft.tone, soft.value) == ("unknown", "Soft-story list could not be reached")
    assert flag(p, "tsunami_zone").tone == "alert"


def test_overpass_failure_drops_only_the_osm_flags():
    p = build_profile(DEMO_ADDRESS, Patched({osm.OVERPASS_URL: answer({}, status=504)}))
    assert [f.kind for f in p.flags] == ["tsunami_zone", "soft_story"]
    assert p.footprint is None


def test_overpass_falls_through_both_busy_instances_to_the_last_mirror():
    seen = []

    def busy(req):
        seen.append((req.url, req.timeout_s))
        return Response(599, "Read timed out", "live")

    def last(req):
        seen.append((req.url, req.timeout_s))
        return samples.SampleTransport().send(Request(req.method, osm.OVERPASS_URL, req.params))

    p = build_profile(DEMO_ADDRESS, Patched({osm.OVERPASS_URL: busy, osm.OVERPASS_MIRRORS[0]: busy,
                                             osm.OVERPASS_MIRRORS[1]: last}))
    assert [u for u, _ in seen] == [osm.OVERPASS_URL, *osm.OVERPASS_MIRRORS]
    assert all(t == 60 for _, t in seen)
    assert p.footprint is not None


def test_soft_story_match_reports_city_status_verbatim():
    rows = [{"property_address": "1000 GREAT HWY", "status": "Work Pending - Permit Issued"}]
    p = build_profile(DEMO_ADDRESS, Patched({softstory.SF_ENDPOINT: answer(rows)}))
    soft = flag(p, "soft_story")
    assert (soft.tone, soft.value) == ("alert", "On San Francisco's soft-story list")
    assert soft.status == "Work Pending - Permit Issued"
    assert soft.detail.endswith("City status: Work Pending - Permit Issued.")
    assert p.provenance == "sample"
    assert soft.provenance == "sample"


def test_hazard_point_check_works_for_any_point():
    t = samples.SampleTransport()
    assert cgs.in_hazard_area(t, (-122.512, 37.76))
    assert not cgs.in_hazard_area(t, (-122.47, 37.76))
