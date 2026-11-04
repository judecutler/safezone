import json

from safezone.config import Settings
from safezone.meta import MetaClient
from safezone.room.classify import CLASSIFIER_UNAVAILABLE, classify, parse_classification
from safezone.shapes import Segment
from safezone.transport import Response

SETTINGS = Settings(meta_api_key=None, meta_api_base="https://meta.test/v1", vision_model="muse", segment_model="sam")
SIZE = (100, 100)


def seg(seg_id, label, bbox=(0, 0, 10, 10)):
    return Segment(id=seg_id, label=label, bbox=bbox, outline=None, area_px=100, centroid=(5, 5),
                   touches_floor=False, height_ratio=0.1, confidence=None)


SEGS = [seg("table-0", "table"), seg("bed-0", "bed"), seg("mirror-0", "mirror"),
        seg("wardrobe-0", "wardrobe"), seg("box-0", "box")]


def answer(segments, relations=(), best_spot=None, exit_note=None):
    return {"segments": [{"id": i, "role": r, "hazard_kind": k, "reason": "seen"} for i, r, k in segments],
            "relations": [{"kind": k, "subject_id": s, "hazard_id": h, "note": "n"} for k, s, h in relations],
            "best_spot": best_spot, "exit_note": exit_note}


def roles(data):
    classified, *_ = parse_classification(data, SEGS, SIZE)
    return {c.segment.id: (c.role, c.hazard_kind, c.reason) for c in classified}


def test_guards_apply_whatever_the_model_says():
    out = roles(answer([
        ("table-0", "cover", None), ("bed-0", "cover", None), ("mirror-0", "cover", None),
        ("wardrobe-0", "hazard", None), ("ghost-9", "hazard", "tv"),
    ]))
    assert out == {
        "table-0": ("cover", None, "seen"),
        "bed-0": ("neutral", None, "Only a sturdy table or desk counts as cover."),
        "mirror-0": ("neutral", None, "Glass is never cover."),
        "wardrobe-0": ("neutral", None, "Marked a hazard without a known kind. seen"),
        "box-0": ("neutral", None, "Not classified."),
    }


def test_relations_must_name_known_ids_and_a_fitting_hazard():
    data = answer([("wardrobe-0", "hazard", "tall_furniture"), ("box-0", "hazard", "heavy_up_high")], relations=[
        ("in_tip_zone", "bed-0", "wardrobe-0"),
        ("under_stored_items", "bed-0", "box-0"),
        ("in_tip_zone", "bed-0", "box-0"),
        ("near_glass", "bed-0", "mirror-0"),
        ("blocks_exit", "ghost-1", "wardrobe-0"),
        ("in_tip_zone", "bed-0", "ghost-2"),
    ])
    _, relations, _, _ = parse_classification(data, SEGS, SIZE)
    assert [(r.kind, r.subject_id, r.hazard_id) for r in relations] == [
        ("in_tip_zone", "bed-0", "wardrobe-0"),
        ("under_stored_items", "bed-0", "box-0"),
    ]


def test_best_spot_is_converted_to_pixels_and_text_is_one_line():
    data = answer([], best_spot={"x": 0.5, "y": 0.25, "description": "by the\nwall", "reason": "x" * 300},
                  exit_note="  ")
    _, _, floor, exit_note = parse_classification(data, SEGS, SIZE)
    assert floor.point == (50, 25) and floor.description == "by the wall" and len(floor.reason) == 140
    assert exit_note is None


class ChatTransport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def send(self, request):
        self.calls += 1
        status, content = self.replies.pop(0)
        body = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]})
        return Response(status, body, "recorded")


def test_retries_once_then_succeeds():
    t = ChatTransport((500, {}), (200, answer([("table-0", "cover", None)])))
    result = classify(b"jpeg", SEGS, SIZE, MetaClient(t, SETTINGS))
    assert t.calls == 2 and result.ok and result.classified[0].role == "cover"


def test_two_bad_answers_fall_back_to_neutral():
    t = ChatTransport((200, {"segments": "nope"}), (599, {}))
    result = classify(b"jpeg", SEGS, SIZE, MetaClient(t, SETTINGS))
    assert not result.ok and result.called and result.notes == [CLASSIFIER_UNAVAILABLE]
    assert {c.role for c in result.classified} == {"neutral"}


def test_no_segments_skips_the_call():
    t = ChatTransport()
    result = classify(b"jpeg", [], SIZE, MetaClient(t, SETTINGS))
    assert t.calls == 0 and not result.called
