import json

import pytest

from safezone.config import Settings
from safezone.meta import MetaClient, MetaUnavailable
from safezone.room.segment import MASKS_NOT_DECODED, PHRASES, offset_path, parse_sam_output, segment_image
from safezone.transport import Response

SETTINGS = Settings(meta_api_key=None, meta_api_base="https://meta.test/v1", vision_model="muse", segment_model="sam")


def stream(text):
    return f'data: {json.dumps({"type": "response.output_text.delta", "delta": text})}\n\n'


class PhraseTransport:
    def __init__(self, by_phrase, fail=()):
        self.by_phrase, self.fail = by_phrase, set(fail)

    def send(self, request):
        phrase = json.loads(request.body)["input"][0]["content"][0]["text"]
        if phrase in self.fail:
            return Response(500, "boom", "live")
        return Response(200, stream(self.by_phrase.get(phrase, "")), "recorded")


def scan(by_phrase, fail=(), size=(100, 100)):
    return segment_image(b"jpeg", size, MetaClient(PhraseTransport(by_phrase, fail), SETTINGS))


def test_multi_record_line_with_sparse_ids_and_inclusive_boxes():
    recs = parse_sam_output("<0f>3<|box;x1=10;y1=20;x2=29;y2=59;w=100;h=100;c=0.5|>,"
                            "7<|box;x1=0;y1=0;x2=9;y2=9;w=100;h=100|>")
    assert [(r.obj_id, r.box, r.confidence) for r in recs] == [
        (3, (10, 20, 30, 60), 0.5),
        (7, (0, 0, 10, 10), None),
    ]


def test_empty_output_is_zero_matches():
    assert parse_sam_output("") == []
    assert scan({}).segments == []


def test_garbage_output_fails_only_that_phrase():
    result = scan({"bed": "<0f>0<|box;x1=0;y1=70;x2=49;y2=99|>", "table": "I see a table"})
    assert [s.id for s in result.segments] == ["bed-0"]
    assert result.notes == ["Could not segment: table."]


def test_mask_without_parser_falls_back_to_boxes_with_one_note():
    mask = "<|mask;x=0;y=0;c=0.9;data=10,20,~A;b=c,d|>"
    result = scan({
        "bed": f"<0f>0<|box;x1=0;y1=70;x2=19;y2=79;w=100;h=100;c=0.9|>{mask}",
        "box": f"<0f>0<|box;x1=50;y1=0;x2=59;y2=9;w=100;h=100;c=0.8|>{mask}",
    })
    bed, box = result.segments
    assert bed.outline is None and bed.area_px == 200
    assert bed.touches_floor and not box.touches_floor
    assert bed.height_ratio == 0.1 and bed.centroid == (10, 75)
    assert result.notes.count(MASKS_NOT_DECODED) == 1


def test_boxes_scale_from_the_size_the_model_saw():
    result = scan({"bed": "<0f>0<|box;x1=10;y1=10;x2=19;y2=19;w=50;h=50|>"}, size=(100, 100))
    assert result.segments[0].bbox == (20, 20, 40, 40)


def test_overlapping_phrases_keep_the_more_confident_and_number_per_label():
    result = scan({
        "cabinet": "<0f>0<|box;x1=0;y1=0;x2=49;y2=99;c=0.6|>,1<|box;x1=60;y1=0;x2=69;y2=9|>",
        "wardrobe": "<0f>4<|box;x1=1;y1=0;x2=49;y2=99;c=0.9|>",
        "box": "<0f>2<|box;x1=60;y1=0;x2=69;y2=9;c=0.2|>",
    })
    assert [(s.id, s.label) for s in result.segments] == [("wardrobe-0", "wardrobe"), ("box-0", "box")]


def test_every_phrase_failing_raises_meta_unavailable():
    with pytest.raises(MetaUnavailable):
        scan({}, fail=PHRASES)


def test_offset_path_moves_absolute_coordinates_only():
    assert offset_path("M0 0 L2 0 l0 3 H5 V7 Z", 10, 20) == "M 10 20 L 12 20 l 0 3 H 15 V 27 Z"
    assert offset_path("m1,1 2,0z", 10, 20, 2, 2) == "m 22 42 4 0 z"


def test_real_sam_record_maps_its_downscaled_mask_onto_the_box(monkeypatch):
    # Header of a recorded SAM 3.1 answer for "wardrobe" on the 4032 x 2268 demo photo; payload shortened.
    text = ("<0f>0<|box;x1=400;y1=483;x2=2193;y2=2049;w=4032;h=2268;c=0.6559139490127563|>"
            "<|mask;x=0;y=0;c=0.6559139490127563;data=894,1024,~!!88k#L*0P|>\n")
    from safezone.room import segment

    (rec,) = segment.parse_sam_output(text)
    assert (rec.mask.width, rec.mask.height, rec.mask.encoding) == (1024, 894, "lossless")
    seen = {}

    def fake_decode(mask, ox, oy, sx, sy):
        seen["corners"] = ((ox * sx, oy * sy), ((ox + mask.width) * sx, (oy + mask.height) * sy))
        return "M0 0Z", 1.0, (0.0, 0.0)

    monkeypatch.setattr(segment, "_decode_mask", fake_decode)
    seg, decoded = segment._segment("wardrobe-0", "wardrobe", rec, (1600, 900))
    (x0, y0), (x1, y1) = seen["corners"]
    assert decoded
    assert (x0, y0, x1, y1) == pytest.approx(seg.bbox, abs=0.01)


def test_mask_decoding_reads_the_parser_byte_raster_and_never_crashes(monkeypatch):
    import sys
    import types

    from safezone.room import segment

    fake = types.ModuleType("meta_sam_parser")

    class SegmentationMask:
        def __init__(self, encoding, payload, width, height):
            self.width, self.height = width, height

    fake.SegmentationMask = SegmentationMask
    # 2 x 4 mask, row-major bytes: the right half of each row is set.
    fake.decode_mask_to_raster = lambda m: bytes([0, 0, 1, 1, 0, 0, 1, 1])
    fake.decode_mask_to_svg_path = lambda m: "M2 0L4 0L4 2L2 2Z"
    monkeypatch.setitem(sys.modules, "meta_sam_parser", fake)
    mask = segment.SamMask("lossless", "~abc", 4, 2, 0, 0)
    path, area, centroid = segment._decode_mask(mask, 10, 20, 1.0, 1.0)
    assert area == 4 and centroid == (13.0, 21.0)
    assert path.startswith("M 12 20")

    fake.decode_mask_to_raster = lambda m: (_ for _ in ()).throw(RuntimeError("bad payload"))
    assert segment._decode_mask(mask, 10, 20, 1.0, 1.0) is None
