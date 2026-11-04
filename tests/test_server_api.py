"""The JSON API through the real Starlette app, answered by samples and replayed fixtures."""
import io
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from safezone.app import Services, create_app
from safezone.config import ROOT, Settings
from safezone.meta import MetaClient
from safezone.room.segment import PHRASES, segment_image
from safezone.transport import ReplayTransport
from tests.asgi import call
from tools.demo import SampleResponder
from tools.samples.geo import DEMO_HOME

SETTINGS = Settings(meta_api_key="k", meta_api_base="https://api.meta.ai/v1", vision_model="muse-spark-1.3",
                    segment_model="sam-3.1")
DEMO_PHOTO = ROOT / "demo" / "living_room.jpg"


def services(transport=None, demo_plan=ROOT / "demo" / "plan.json") -> Services:
    t = transport or SampleResponder()
    return Services(SETTINGS, t, t, True, demo_plan)


def jpeg(size=(64, 48)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 180, 150)).save(out, "JPEG")
    return out.getvalue()


def test_profile_by_point_returns_the_building_profile():
    r = call(create_app(services()), "GET", f"/api/profile?lat={DEMO_HOME[1]}&lon={DEMO_HOME[0]}")
    assert r.status == 200
    body = r.json()
    assert {"address", "display_name", "lon", "lat", "flags", "hazard_area", "provenance"} <= body.keys()
    assert body["flags"][0]["kind"] == "tsunami_zone" and body["flags"][0]["tone"] == "alert"


@pytest.mark.parametrize("query", ["lat=abc&lon=1", "lat=95&lon=0", "lat=1", "lat=nan&lon=0"])
def test_profile_rejects_a_bad_point(query):
    r = call(create_app(services()), "GET", f"/api/profile?{query}")
    assert (r.status, r.json()["error"]) == (400, "bad_location")


def test_profile_for_an_unmapped_point_is_404():
    r = call(create_app(services()), "GET", "/api/profile?lat=30&lon=-140")
    assert (r.status, r.json()["error"]) == (404, "location_not_found")


def test_profile_by_address_still_works():
    r = call(create_app(services()), "GET", "/api/profile?address=1000%20Great%20Highway%2C%20San%20Francisco%2C%20CA%2094121")
    assert r.status == 200 and r.json()["flags"][0]["kind"] == "tsunami_zone"


def test_gobag_returns_the_check_with_sample_provenance():
    r = call(create_app(services()), "POST", "/api/gobag", jpeg(), "image/jpeg")
    assert r.status == 200
    body = r.json()
    assert {"items", "seen_count", "total", "model", "provenance", "caveat"} <= body.keys()
    assert body["provenance"] == "sample"
    assert body["seen_count"] == sum(i["seen"] for i in body["items"]) and body["total"] == len(body["items"])
    assert {i["status"] for i in body["items"]} <= {"Seen in the photo", "Not seen"}


def test_gobag_rejects_an_empty_or_unreadable_photo():
    app = create_app(services())
    assert call(app, "POST", "/api/gobag", b"", "image/jpeg").json()["error"] == "empty_photo"
    assert call(app, "POST", "/api/gobag", b"not a photo", "image/jpeg").json()["error"] == "unreadable_photo"


def test_gobag_reports_meta_unavailable_when_the_model_is_down():
    class Down:
        def send(self, request):
            from safezone.transport import Response
            return Response(503, "down", "live")

    r = call(create_app(services(Down())), "POST", "/api/gobag", jpeg(), "image/jpeg")
    assert (r.status, r.json()["error"]) == (502, "meta_unavailable")


def test_demo_includes_the_labelled_sample_gobag_and_extras(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"plan": {"rooms": []}, "images": {}}))
    (tmp_path / "gobag.json").write_text((ROOT / "demo" / "gobag.json").read_text())
    (tmp_path / "exit.jpg").write_bytes(jpeg())
    body = call(create_app(services(demo_plan=plan)), "GET", "/api/demo").json()
    assert body["gobag"]["provenance"] == "sample"
    assert body["extras"] == {"exit": "/demo/exit.jpg"}
    assert body["plan"] == {"rooms": []}


def test_demo_without_a_gobag_says_so(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"plan": {}, "images": {}}))
    body = call(create_app(services(demo_plan=plan)), "GET", "/api/demo").json()
    assert body["gobag"] is None and body["extras"] == {}


def test_the_shipped_demo_gobag_is_labelled_sample_or_recorded():
    check = json.loads((ROOT / "demo" / "gobag.json").read_text())
    assert check["provenance"] in ("sample", "recorded")


def test_scan_replays_the_recorded_demo_photo():
    replay = ReplayTransport(ROOT / "fixtures" / "demo")
    r = call(create_app(services(replay)), "POST", "/api/scan?name=Bedroom", DEMO_PHOTO.read_bytes(), "image/jpeg")
    assert r.status == 200
    body = r.json()
    assert body["provenance"] == "recorded" and body["models"]["classifier_ok"]
    assert not any(n.startswith("Could not segment") for n in body["notes"])


def test_scan_with_no_model_answer_is_502_not_an_empty_room(tmp_path):
    r = call(create_app(services(ReplayTransport(tmp_path))), "POST", "/api/scan?name=Bedroom", jpeg(), "image/jpeg")
    assert (r.status, r.json()["error"]) == (502, "meta_unavailable")


class Overlap:
    """Every SAM request waits until all phrases are in flight, so a capped pool deadlocks into a timeout."""

    def __init__(self):
        self.inflight = self.peak = 0
        self.lock = threading.Lock()

    def send(self, request):
        with self.lock:
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
        deadline = time.monotonic() + 2
        while self.peak < len(PHRASES) and time.monotonic() < deadline:
            time.sleep(0.005)
        with self.lock:
            self.inflight -= 1
        return SampleResponder().send(request)


def test_every_sam_phrase_is_in_flight_at_once():
    t = Overlap()
    segment_image(DEMO_PHOTO.read_bytes(), (1600, 900), MetaClient(t, SETTINGS))
    assert t.peak == len(PHRASES)
