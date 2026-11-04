from safezone import rules
from safezone.room.classify import FloorProposal
from safezone.room.score import fixes_for, floor_rejection, rank_spots
from safezone.rules import DURING_SPECIAL
from safezone.shapes import Classified, Segment

SIZE = (1000, 1000)


def item(seg_id, label, bbox, role="neutral", kind=None):
    s = Segment(id=seg_id, label=label, bbox=bbox, outline=None, area_px=1, centroid=(0, 0),
                touches_floor=True, height_ratio=0.1, confidence=None)
    return Classified(segment=s, role=role, hazard_kind=kind, reason="r")


def floor(x, y):
    return FloorProposal((x, y), "by the wall", "Nothing above it.")


def test_cover_near_a_window_ranks_below_cover_in_the_open():
    classified = [
        item("table-0", "table", (100, 600, 200, 700), "cover"),
        item("table-1", "table", (700, 600, 800, 700), "cover"),
        item("window-0", "window", (210, 300, 300, 500), "hazard", "glass"),
    ]
    spots, _ = rank_spots(classified, None, SIZE)
    assert [s.anchor_id for s in spots] == ["table-1", "table-0"]
    assert spots[0].score > spots[1].score
    assert "Glass can shatter. Stay clear of the window." in spots[1].cautions


def test_tall_furniture_tipping_zone_costs_score():
    wardrobe = item("wardrobe-0", "wardrobe", (0, 100, 100, 600), "hazard", "tall_furniture")
    near = [wardrobe, item("desk-0", "desk", (550, 700, 650, 800), "cover")]
    far = [wardrobe, item("desk-0", "desk", (650, 700, 750, 800), "cover")]
    (near_spot,), _ = rank_spots(near, None, SIZE)
    (far_spot,), _ = rank_spots(far, None, SIZE)
    assert near_spot.score < far_spot.score * 0.75
    assert near_spot.cautions[0] == "Tall furniture can tip. Stay clear of the wardrobe."


def test_no_cover_gives_one_guidance_spot_with_bed_and_doorway_lines():
    classified = [item("bed-0", "bed", (0, 600, 400, 1000)),
                  item("wardrobe-0", "wardrobe", (500, 100, 600, 600), "hazard", "tall_furniture")]
    (spot,), notes = rank_spots(classified, None, SIZE)
    assert (spot.kind, spot.score, spot.anchor_id, spot.instruction) == (
        "no_cover", 0, None, DURING_SPECIAL["no_cover"])
    assert spot.cautions == ["Tall furniture can tip. Stay clear of the wardrobe.",
                             DURING_SPECIAL["in_bed"], DURING_SPECIAL["doorway"]]
    assert notes == []


ROOM = [
    item("wardrobe-0", "wardrobe", (100, 200, 200, 400), "hazard", "tall_furniture"),
    item("door-0", "door", (600, 200, 700, 600)),
    item("bed-0", "bed", (800, 600, 1000, 1000)),
    item("box-0", "box", (400, 0, 500, 100), "hazard", "heavy_up_high"),
    item("window-0", "window", (900, 100, 1000, 300), "hazard", "glass"),
]


def test_floor_guards_reject_each_unsafe_kind_of_spot():
    assert floor_rejection(floor(150, 300), ROOM, SIZE) == "it is on or inside the wardrobe"
    assert floor_rejection(floor(705, 630), ROOM, SIZE) == "it is in a doorway"
    assert floor_rejection(floor(380, 450), ROOM, SIZE) == "it is where the wardrobe could land if it tips"
    assert floor_rejection(floor(450, 220), ROOM, SIZE) == "it is under the box"
    assert floor_rejection(floor(800, 380), ROOM, SIZE) == "it is close to glass (window)"
    assert floor_rejection(floor(-1, 500), ROOM, SIZE) == "it is outside the photo"
    assert floor_rejection(floor(450, 800), ROOM, SIZE) is None


def test_a_safe_floor_spot_replaces_no_cover_and_ranks_after_cover():
    spots, _ = rank_spots(ROOM, floor(450, 800), SIZE)
    assert [s.kind for s in spots] == ["open_floor"]
    assert spots[0].point == (450, 800) and spots[0].score <= 0.6
    assert spots[0].instruction == "Drop on the open floor here: by the wall. Cover your head and neck with your arms."
    assert spots[0].cautions[0] == "Nothing above it."

    with_cover = [*ROOM, item("table-0", "table", (300, 800, 400, 900), "cover")]
    spots, _ = rank_spots(with_cover, floor(450, 800), SIZE)
    assert [s.kind for s in spots] == ["cover", "open_floor"]


def test_rejected_floor_spot_is_explained_and_never_shown():
    spots, notes = rank_spots(ROOM, floor(150, 300), SIZE)
    assert [s.kind for s in spots] == ["no_cover"]
    assert spots[0].cautions[0] == "Muse Spark suggested a spot on the floor. SafeZone set it aside: it is on or inside the wardrobe."
    assert notes == []


def test_fixes_come_from_the_table_ordered_by_effort():
    fixes = fixes_for([
        item("light-0", "ceiling light", (0, 0, 1, 1), "hazard", "overhead_fixture"),
        item("wardrobe-0", "wardrobe", (0, 0, 1, 1), "hazard", "tall_furniture"),
        item("tv-0", "TV", (0, 0, 1, 1), "hazard", "tv"),
        item("box-0", "box", (0, 0, 1, 1), "hazard", "heavy_up_high"),
        item("bed-0", "bed", (0, 0, 1, 1)),
    ])
    assert [(f.id, f.effort) for f in fixes] == [
        ("fix-box-0", "minutes"), ("fix-tv-0", "minutes"), ("fix-wardrobe-0", "hour"), ("fix-light-0", "pro")]
    assert fixes[2].action == rules.FIX_TABLE["tall_furniture"][0]
