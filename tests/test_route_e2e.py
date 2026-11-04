"""The demo path: sample OSRM recorded as fixtures, then replayed offline."""
from datetime import datetime, timezone

from safezone import geo
from safezone.route import pipeline
from safezone.route.pipeline import plan_route
from safezone.shapes import BuildingProfile, DirectionOnly, HazardArea, WalkingRoute
from safezone.transport import RecordingTransport, ReplayTransport
from tools.samples import route as sample_route
from tools.samples.geo import DEMO_ADDRESS, DEMO_DISPLAY, DEMO_HOME, SAMPLE_HAZARD_RING

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
POLYGONS = [[SAMPLE_HAZARD_RING]]


class Samples:
    def send(self, request):
        return sample_route.respond(request)


def demo_profile():
    return BuildingProfile(address=DEMO_ADDRESS, display_name=DEMO_DISPLAY, lon=DEMO_HOME[0], lat=DEMO_HOME[1],
                           city="San Francisco", footprint=None, flags=[],
                           hazard_area=HazardArea(contains_home=True, polygons=POLYGONS, county="San Francisco",
                                                  map_url=None, source_url="https://cgs.test/hazard"),
                           provenance="sample")


def test_demo_route_records_then_replays(tmp_path):
    recorded = plan_route(demo_profile(), RecordingTransport(Samples(), tmp_path, provenance="sample"), NOW)
    assert isinstance(recorded, WalkingRoute)
    assert recorded.provenance == "sample"
    assert recorded.path[0] == DEMO_HOME
    assert not geo.point_in_any(recorded.destination, POLYGONS)
    assert geo.distance_to_boundary_m(recorded.destination, POLYGONS) >= pipeline.END_CLEARANCE_M
    assert pipeline.check_route(DEMO_HOME, recorded.path, POLYGONS) == []
    assert recorded.steps[0].instruction.startswith("Head north on")
    assert recorded.steps[-1].instruction == "Arrive"
    assert 0 < recorded.distance_m < 1500
    assert recorded.walk_min == recorded.distance_m / 60

    replayed = plan_route(demo_profile(), ReplayTransport(tmp_path), NOW)
    assert replayed == recorded


def test_demo_without_fixtures_falls_back_to_a_direction(tmp_path):
    result = plan_route(demo_profile(), ReplayTransport(tmp_path), NOW)
    assert isinstance(result, DirectionOnly)
    assert result.compass == "east"
    assert not geo.point_in_any(result.destination, POLYGONS)
