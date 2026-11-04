import io

import pytest
from PIL import Image

from run import SampleResponder, render
from safezone.config import ROOT, Settings
from safezone.meta import MetaClient
from safezone.room.classify import FloorProposal
from safezone.room.pipeline import SEGMENTATION_UNAVAILABLE, prepare_image, scan_room
from safezone.room.score import floor_rejection
from safezone.transport import RecordingTransport, ReplayTransport
from tools.samples import room as samples

SETTINGS = Settings(meta_api_key=None, meta_api_base="https://api.meta.ai/v1",
                    vision_model="muse-spark-1.3", segment_model="sam-3.1")
DEMO = ROOT / "demo" / "living_room.jpg"


@pytest.fixture(scope="module")
def demo_scans(tmp_path_factory):
    directory = tmp_path_factory.mktemp("fixtures")
    jpeg = prepare_image(DEMO.read_bytes())
    recorder = RecordingTransport(SampleResponder([samples.respond]), directory, provenance="sample")
    recorded = scan_room(jpeg, "Dorm room", MetaClient(recorder, SETTINGS))
    replayed = scan_room(jpeg, "Dorm room", MetaClient(ReplayTransport(directory), SETTINGS))
    return recorded, replayed


def test_demo_scan_replays_identically_and_is_labelled_sample(demo_scans):
    recorded, replayed = demo_scans
    assert replayed == recorded
    assert replayed.provenance == "sample"
    assert replayed.models.classifier == "muse-spark-1.3" and replayed.models.classifier_ok


def test_demo_room_has_no_cover_and_says_so(demo_scans):
    scan = demo_scans[1]
    assert [s.kind for s in scan.spots] == ["no_cover"]
    assert not any(c.role == "cover" for c in scan.classified)
    assert all(c.reason != "Not classified." for c in scan.classified)
    assert "Muse Spark's suggested floor spot was not used: it is where the wardrobe could land if it tips." in scan.notes


def test_demo_room_reasoning_reaches_the_plan(demo_scans):
    scan = demo_scans[1]
    assert {(r.kind, r.subject_id, r.hazard_id) for r in scan.relations} == {
        ("in_tip_zone", "bed-0", "wardrobe-0"), ("in_tip_zone", "bed-1", "bookshelf-0"),
        ("under_stored_items", "bed-1", "box-0"), ("blocks_exit", "door-0", "wardrobe-1")}
    assert scan.exit_note
    cautions = scan.spots[0].cautions
    assert sum(c.startswith("Muse Spark: ") for c in cautions) == 4
    assert {f.target_id for f in scan.fixes} == {c.segment.id for c in scan.classified if c.role == "hazard"}
    assert "Fixes:" in render(scan)


def test_a_best_spot_inside_a_demo_wardrobe_is_rejected(demo_scans):
    scan = demo_scans[1]
    wardrobe = next(c.segment for c in scan.classified if c.segment.id == "wardrobe-0")
    inside = FloorProposal(wardrobe.centroid, "inside the wardrobe", "It is enclosed.")
    assert floor_rejection(inside, scan.classified, scan.image_size) == "it is on or inside the wardrobe"


def test_no_api_answer_still_gives_guidance(tmp_path):
    scan = scan_room(DEMO.read_bytes(), "Room", MetaClient(ReplayTransport(tmp_path), SETTINGS))
    assert scan.notes[0] == SEGMENTATION_UNAVAILABLE
    assert [s.kind for s in scan.spots] == ["no_cover"] and scan.classified == [] and scan.fixes == []
    assert scan.models.classifier is None


def jpeg(size, exif_orientation=None):
    img = Image.new("RGB", size, (200, 10, 10))
    out = io.BytesIO()
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        img.save(out, "JPEG", exif=exif)
    else:
        img.save(out, "JPEG")
    return out.getvalue()


def test_prepare_image_uprights_shrinks_and_strips_metadata():
    out = Image.open(io.BytesIO(prepare_image(jpeg((4000, 3000), exif_orientation=6))))
    assert out.size == (1200, 1600)
    assert not out.getexif()


def test_prepare_image_leaves_a_clean_jpeg_byte_identical():
    raw = jpeg((800, 600))
    assert prepare_image(raw) == raw


def test_prepare_image_rejects_non_images():
    with pytest.raises(ValueError):
        prepare_image(b"not an image")
