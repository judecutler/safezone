from datetime import datetime, timezone

from safezone.transport import RecordingTransport, ReplayTransport
from tools.demo import build_plan_jp
from tools.record_japan import run
from tools.samples import japan
from tools.samples.japan import JP_DEMO_ADDRESS


def test_a_japan_recording_rebuilds_the_kamakura_demo_from_recorded_answers(tmp_path):
    now = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
    recorded = run(RecordingTransport(japan.SampleTransport(), tmp_path, provenance="recorded"), JP_DEMO_ADDRESS, now)
    plan = build_plan_jp(ReplayTransport(tmp_path), now)["plan"]
    assert plan["route"]["kind"] == "site_route"
    assert plan["route"]["site"]["name"] == recorded["route"]["site"]["name"]
    assert plan["building"]["provenance"] == "recorded"
