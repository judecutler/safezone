import json

import pytest
from pydantic import ValidationError

from safezone import geo
from safezone.meta import responses_output_text
from safezone.shapes import Classified, Segment, weakest
from safezone.transport import RecordingTransport, ReplayTransport, Request, Response, get_json

SQUARE = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]]
DONUT = [SQUARE[0], [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]]


def test_point_in_polygon_respects_holes():
    assert geo.point_in_polygon((0.2, 0.2), DONUT)
    assert not geo.point_in_polygon((0.5, 0.5), DONUT)
    assert not geo.point_in_polygon((1.5, 0.5), DONUT)


def test_distances_match_known_values():
    one_degree_lat = geo.haversine_m((-122.0, 37.0), (-122.0, 38.0))
    assert one_degree_lat == pytest.approx(111_195, rel=1e-3)
    assert geo.compass(geo.bearing_deg((-122.0, 37.0), (-121.9, 37.0))) == "east"
    near = [[(-122.001, 36.9), (-122.001, 37.1), (-123.0, 37.1), (-123.0, 36.9)]]
    assert geo.distance_to_boundary_m((-122.0, 37.0), [near]) == pytest.approx(88.8, rel=0.02)


def test_hazard_role_requires_kind():
    seg = Segment(id="tv-0", label="TV", bbox=(0, 0, 1, 1), outline=None, area_px=1, centroid=(0.5, 0.5),
                  touches_floor=False, height_ratio=0.1, confidence=None)
    with pytest.raises(ValidationError):
        Classified(segment=seg, role="hazard", hazard_kind=None, reason="x")
    with pytest.raises(ValidationError):
        Classified(segment=seg, role="cover", hazard_kind="tv", reason="x")


def test_weakest_provenance():
    assert weakest("live", "sample", "recorded") == "sample"
    assert weakest("live") == "live"


class Echo:
    def send(self, request):
        return Response(200, json.dumps({"url": request.url}), "live")


def test_record_then_replay_round_trip(tmp_path):
    recorder = RecordingTransport(Echo(), tmp_path, provenance="sample")
    assert get_json(recorder, "https://x.test/a", {"q": 1}) == ({"url": "https://x.test/a"}, "sample")
    replay = ReplayTransport(tmp_path)
    assert get_json(replay, "https://x.test/a", {"q": 1}) == ({"url": "https://x.test/a"}, "sample")
    assert replay.send(Request("GET", "https://x.test/other")).status == 599


def test_auth_header_does_not_change_fixture_key():
    a = Request("GET", "https://x.test", headers=(("Authorization", "Bearer 1"),))
    b = Request("GET", "https://x.test", headers=(("Authorization", "Bearer 2"),))
    assert a.key() == b.key()


def test_responses_stream_text_is_concatenated():
    sse = "\n".join([
        "event: response.output_text.delta",
        'data: {"type":"response.output_text.delta","delta":"<0f>0<|box;"}',
        'data: {"type":"response.output_text.delta","delta":"x1=1|>"}',
        'data: {"type":"response.completed","response":{"output":[]}}',
    ])
    assert responses_output_text(sse) == "<0f>0<|box;x1=1|>"
    assert responses_output_text('data: {"type":"response.completed","response":{"output":[]}}') == ""
