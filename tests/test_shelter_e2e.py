"""The demo path: sample FEMA and OSRM recorded as fixtures, then replayed offline."""
from datetime import datetime, timezone

import pytest

from safezone import geo
from safezone.shapes import BuildingProfile, HazardArea, Household
from safezone.shelter.pipeline import find_shelters
from safezone.transport import HttpError, RecordingTransport, ReplayTransport
from tools.samples import route as sample_route
from tools.samples import shelter as sample_shelter
from tools.samples.geo import DEMO_ADDRESS, DEMO_DISPLAY, DEMO_HOME, SAMPLE_HAZARD_RING

NOW = datetime(2026, 11, 3, 12, 30, tzinfo=timezone.utc)
POLYGONS = [[SAMPLE_HAZARD_RING]]
ROUTE_END = (-122.5073, 37.7697)


class Samples:
    def send(self, request):
        return sample_shelter.respond(request) or sample_route.respond(request)


def demo_profile():
    return BuildingProfile(address=DEMO_ADDRESS, display_name=DEMO_DISPLAY, lon=DEMO_HOME[0], lat=DEMO_HOME[1],
                           city="San Francisco", footprint=None, flags=[],
                           hazard_area=HazardArea(contains_home=True, polygons=POLYGONS, county="San Francisco",
                                                  map_url=None, source_url="https://cgs.test/hazard"),
                           provenance="sample")


def in_sample_ring(p):
    return geo.point_in_any(p, POLYGONS)


def test_demo_shelters_record_then_replay(tmp_path):
    household = Household(wheelchair=True, pets=True)
    recorder = RecordingTransport(Samples(), tmp_path, provenance="sample")
    recorded = find_shelters(ROUTE_END, demo_profile(), household, recorder, in_sample_ring, NOW, replay=False)

    names = [m.shelter.name for m in recorded.matches]
    assert names == ["Sample Shelter A", "Sample Shelter B", "Sample Shelter C"]
    assert recorded.excluded == {"not_open": 1, "in_hazard_area": 1, "hazard_check_failed": 0,
                                 "not_wheelchair_accessible": 1}
    assert all(m.walk_method == "route" for m in recorded.matches)
    assert all(not in_sample_ring((m.shelter.lon, m.shelter.lat)) for m in recorded.matches)
    walk = [m.walk_min for m in recorded.matches]
    assert walk == sorted(walk), "A reports room; B (nearly full) and C (unreported) follow by walking time"
    assert recorded.provenance == "sample"
    assert "Nearly full: about 85% of capacity, so shelters with more room rank first." in recorded.matches[1].notes
    assert "Capacity not reported, so shelters that report room rank first." in recorded.matches[2].notes
    assert all("Listed as wheelchair accessible." in m.notes for m in recorded.matches)
    assert all(m.shelter.name.startswith("Sample") for m in recorded.matches)

    replayed = find_shelters(ROUTE_END, demo_profile(), household, ReplayTransport(tmp_path), in_sample_ring, NOW,
                             replay=True)
    assert replayed.matches == recorded.matches
    assert replayed.replay is True


def test_demo_without_fixtures_raises_so_the_ui_shows_unavailable(tmp_path):
    with pytest.raises(HttpError):
        find_shelters(ROUTE_END, demo_profile(), Household(), ReplayTransport(tmp_path), in_sample_ring, NOW, True)
