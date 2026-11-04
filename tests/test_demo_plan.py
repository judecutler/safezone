"""The whole demo household, every pipeline together, recorded from samples and replayed offline."""
from datetime import datetime, timezone

from safezone import geo
from safezone.transport import RecordingTransport, ReplayTransport
from tools.demo import SampleResponder, build_plan

NOW = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)


def test_demo_plan_is_complete_and_replays_identically(tmp_path):
    recorded = build_plan(RecordingTransport(SampleResponder(), tmp_path, provenance="sample"), True, NOW)
    plan = recorded["plan"]
    area = plan["building"]["hazard_area"]
    assert area["contains_home"] and area["polygons"] and area["land_polygons"]
    assert plan["route"]["kind"] == "walking_route"
    end = tuple(plan["route"]["destination"])
    land = [[[tuple(p) for p in ring] for ring in poly] for poly in area["land_polygons"]]
    assert geo.point_in_any(end, land)
    assert [s["kind"] for s in plan["rooms"][0]["spots"]] == ["no_cover"]
    assert plan["shelters"]["matches"] and all(m["shelter"]["wheelchair"] for m in plan["shelters"]["matches"])
    assert build_plan(ReplayTransport(tmp_path), True, NOW) == recorded
