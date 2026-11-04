"""The Japan region end to end on the samples, plus the route checks that keep a shown route honest."""
import json
from datetime import datetime, timezone

import pytest

from safezone import geo, regions
from safezone.japan import evac, rules
from safezone.japan.tiles import InundationMap
from safezone.route.osrm import ROUTE_BASE
from safezone.shapes import Household
from safezone.transport import NETWORK_FAILURE, RecordingTransport, ReplayTransport, Response
from tools.samples import japan as sample

NOW = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
HOME = sample.JP_DEMO_HOME


@pytest.fixture
def transport():
    return sample.SampleTransport()


def demo_profile(transport):
    region, profile = regions.profile_for_address(sample.JP_DEMO_ADDRESS, transport)
    assert region.id == "jp"
    return profile


def test_demo_address_is_flagged_in_the_inundation_area_with_its_source(transport):
    profile = demo_profile(transport)
    (flag,) = [f for f in profile.flags if f.kind == "tsunami_zone"]
    assert flag.tone == "alert" and "inundation area" in flag.value
    assert flag.source_url.startswith("https://disaportaldata.gsi.go.jp/") and flag.provenance == "sample"
    assert profile.hazard_area and profile.hazard_area.contains_home


def test_route_goes_to_a_designated_site_outside_the_inundation_area(transport):
    route = regions.evacuate(demo_profile(transport), Household(), transport, transport, NOW, True).route
    assert route.kind == "site_route"
    assert route.site.name in {name for name, *_ in sample.SITES}
    assert route.site.kind == "high_ground" and route.site.instruction == rules.HIGH_GROUND
    assert InundationMap(transport).depth(route.destination) is None
    assert route.provenance == "sample" and route.site.source_url.startswith("https://cyberjapandata.gsi.go.jp/xyz/skhb05/")


def test_sites_list_excludes_inundated_sites_and_labels_them_evacuation_sites(transport):
    result = regions.evacuate(demo_profile(transport), Household(pets=True), transport, transport, NOW, True).shelters
    names = [m.shelter.name for m in result.matches]
    assert names and "Sample site B (evacuation building)" not in names
    assert result.excluded["in_hazard_area"] == 1
    assert all("not a place to stay" in m.notes[0] for m in result.matches)


def test_wheelchair_household_gets_no_unverified_sites(transport):
    result = regions.evacuate(demo_profile(transport), Household(wheelchair=True), transport, transport, NOW, True)
    assert result.shelters.matches == [] and result.shelters.excluded["not_wheelchair_accessible"] == 3


def test_seaward_route_is_rejected_and_falls_back_to_move_inland(transport):
    class SeawardOsrm:
        def send(self, request):
            if request.url.startswith(ROUTE_BASE):
                origin, dest = sample._coords(request.url[len(ROUTE_BASE):])
                shore = (origin[0], sample.SAMPLE_SHORE_LAT + 0.0005)
                path = [origin, shore, dest]
                body = {"code": "Ok", "routes": [{"geometry": {"coordinates": [list(p) for p in path]},
                                                  "legs": [], "distance": geo.path_length_m(path)}]}
                return Response(200, json.dumps(body), "sample")
            return transport.send(request)

    route = regions.evacuate(demo_profile(transport), Household(), SeawardOsrm(), transport, NOW, True).route
    assert route.kind == "no_checked_route" and route.reason == rules.NO_CHECKED_ROUTE


def test_check_route_names_each_broken_rule(transport):
    m = InundationMap(transport)
    site = (sample.SITES[0][2], sample.SITES[0][3])
    deeper = [HOME, (HOME[0], sample.SAMPLE_SHORE_LAT + 0.0005), site]
    assert "goes_deeper" in evac.check_route(HOME, 0, site, "high_ground", deeper, geo.path_length_m(deeper), m)
    short = [HOME, (HOME[0], 35.3230)]
    assert "ends_away_from_site" in evac.check_route(HOME, 0, site, "high_ground", short, 400.0, m)
    assert evac.check_route(HOME, 0, site, "high_ground", [HOME, site], geo.haversine_m(HOME, site), m) == []


def test_map_outage_reads_unknown_and_gives_no_route():
    class TilesDown(sample.SampleTransport):
        def send(self, request):
            if "disaportaldata" in request.url:
                return Response(NETWORK_FAILURE, "down", "live")
            return super().send(request)

    t = TilesDown()
    profile = demo_profile(t)
    assert profile.flags[0].tone == "unknown" and profile.hazard_area is None
    assert regions.evacuate(profile, Household(), t, t, NOW, True).route is None


def test_japan_run_records_and_replays_identically(tmp_path, transport):
    from tools.record_japan import run

    recorded = run(RecordingTransport(transport, tmp_path, provenance="sample"), sample.JP_DEMO_HOME, NOW)
    assert run(ReplayTransport(tmp_path), sample.JP_DEMO_HOME, NOW) == recorded
