"""Adversarial safety probes. Each test asserts the safe behavior, so a failure is a proven finding.

Geometry is metres east/north of HOME. The ocean is west (negative x) in every polygon here.
"""
import json
from datetime import datetime, timezone

import pytest

from safezone import geo
from safezone.room.classify import FloorProposal, parse_classification
from safezone.room.score import floor_rejection, rank_spots
from safezone.route import osrm
from safezone.route.pipeline import check_route, plan_route
from safezone.shapes import (BuildingProfile, Classified, DirectionOnly, HazardArea, Household, Segment,
                             WalkingRoute)
from safezone.shelter.pipeline import filter_shelters
from safezone.shapes import Shelter
from safezone.transport import Response

HOME = (-122.5100, 37.7700)
FRAME = geo.LocalFrame(HOME)
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def ll(x, y):
    return FRAME.to_lonlat(x, y)


def xy(p):
    return FRAME.to_xy(p)


def rect(x0, x1, y0, y1):
    return [[ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1)]]


def path(*pts):
    return [ll(x, y) for x, y in pts]


def profile(polygons):
    area = HazardArea(contains_home=True, polygons=polygons, county=None, map_url=None, source_url="u")
    return BuildingProfile(address="a", display_name="a", lon=HOME[0], lat=HOME[1], city=None, footprint=None,
                           flags=[], hazard_area=area, provenance="live")


def osrm_json(pts):
    return {"code": "Ok", "routes": [{"geometry": {"coordinates": [list(p) for p in pts]}, "legs": [{"steps": []}],
                                      "distance": geo.path_length_m(pts)}]}


class ScriptedOsrm:
    def __init__(self, answer):
        self.answer = answer

    def send(self, request):
        pts = [tuple(float(v) for v in c.split(",")) for c in request.url.split("/foot/")[1].split(";")]
        out = self.answer(pts[0], pts[1])
        return out if isinstance(out, Response) else Response(200, json.dumps(out), "live")


# Route: the polygon's seaward edge is the shoreline, 30 m west of home. Land exit 150 m east.
SHORE_30M = [rect(-30, 150, -2000, 2000)]


def test_osrm_down_never_points_at_the_water():
    result = plan_route(profile(SHORE_30M), ScriptedOsrm(lambda o, d: Response(599, "down", "live")), NOW)
    assert isinstance(result, DirectionOnly)
    assert xy(result.destination)[0] > 0, f"direction target is {result.compass}, {result.straight_m:.0f} m out to sea"


def test_a_route_onto_a_pier_is_never_shown():
    # OSRM reaches a pier 130 m west of home; that end clears the shoreline edge by 100 m.
    def answer(origin, dest):
        return osrm_json([origin, ll(-130, 0)]) if xy(dest)[0] < 0 else osrm_json([origin, dest])
    route = plan_route(profile(SHORE_30M), ScriptedOsrm(answer), NOW)
    assert isinstance(route, WalkingRoute)
    assert all(xy(p)[0] >= -30 for p in route.path), f"route ends at x={xy(route.destination)[0]:.0f} m (seaward)"


def test_check_route_rejects_a_seaward_end():
    assert check_route(HOME, path((0, 0), (-130, 0)), SHORE_30M) != []


def test_long_leg_along_the_shore_is_rejected():
    # 1500 m north inside the zone, parallel to the water, when the land exit is 150 m east.
    failures = check_route(HOME, path((0, 0), (0, 1500), (300, 1500)), [rect(-100, 150, -2000, 2000)])
    assert failures != []


def test_empty_osrm_geometry_does_not_crash_the_evac_endpoint():
    data = {"code": "Ok", "routes": [{"geometry": {"coordinates": []}, "legs": [], "distance": 0}]}
    assert osrm.parse_route(data) is None


# Shelter --------------------------------------------------------------------

def shelter(n, x_m, wheelchair):
    lon, lat = ll(x_m, 0)
    return Shelter(id=str(n), name=f"S{n}", address="", lon=lon, lat=lat, status="OPEN", capacity=100, residents=1,
                   ada=None, wheelchair=wheelchair, pets_code=None, source_url="u")


def test_an_accessible_shelter_is_not_hidden_behind_25_inaccessible_nearer_ones():
    shelters = [shelter(n, 500 * n, wheelchair=False) for n in range(1, 26)] + [shelter(26, 13000, wheelchair=True)]
    kept, excluded = filter_shelters(shelters, HOME, Household(wheelchair=True), lambda p: False, [])
    assert [s.id for s in kept] == ["26"], f"kept={[s.id for s in kept]} excluded={excluded}"


# Room -----------------------------------------------------------------------

SIZE = (1000, 800)


def seg(seg_id, label, bbox, touches_floor=True):
    return Segment(id=seg_id, label=label, bbox=bbox, outline=None, area_px=1.0, centroid=(0, 0),
                   touches_floor=touches_floor, height_ratio=(bbox[3] - bbox[1]) / SIZE[1], confidence=0.9)


def neutral(s):
    return Classified(segment=s, role="neutral", hazard_kind=None, reason="r")


def hazard(s, kind):
    return Classified(segment=s, role="hazard", hazard_kind=kind, reason="r")


def test_floor_spot_in_the_tip_zone_of_an_unclassified_wardrobe_is_rejected():
    wardrobe = seg("wardrobe-0", "wardrobe", (100, 100, 300, 700))
    spot = FloorProposal((350, 720), "next to the wardrobe", "open floor")
    assert floor_rejection(spot, [neutral(wardrobe)], SIZE) is not None


def test_floor_spot_under_a_box_the_model_called_neutral_is_rejected():
    box = seg("box-0", "box", (400, 50, 500, 150), touches_floor=False)
    spot = FloorProposal((450, 700), "below the shelf", "open floor")
    assert floor_rejection(spot, [neutral(box)], SIZE) is not None


def test_floor_spot_on_the_ceiling_is_rejected():
    assert floor_rejection(FloorProposal((500, 40), "top of the room", "r"), [], SIZE) is not None


def test_table_against_a_window_is_not_the_safe_spot():
    table = seg("table-0", "table", (100, 450, 400, 700))
    window = seg("window-0", "window", (120, 100, 380, 440), touches_floor=False)
    spots, _ = rank_spots([Classified(segment=table, role="cover", hazard_kind=None, reason="sturdy"),
                           hazard(window, "glass")], None, SIZE)
    best = spots[0]
    assert not (best.kind == "cover" and any("Stay clear of the window" in c for c in best.cautions)), \
        f"instruction={best.instruction!r} cautions={best.cautions}"


def test_model_prose_is_not_shown_as_an_unattributed_instruction():
    floor = FloorProposal((500, 700), "run across the hall to the stairwell", "far from glass")
    spots, _ = rank_spots([], floor, SIZE)
    assert "run across the hall" not in spots[0].instruction, spots[0].instruction


def test_guards_that_hold():
    """Bed as cover, unknown hazard ids, NaN and out-of-frame spots are all caught."""
    segments = [seg("bed-0", "bed", (100, 400, 600, 700)), seg("table-0", "table", (650, 450, 900, 700))]
    data = {"segments": [{"id": "bed-0", "role": "cover", "hazard_kind": None, "reason": "r"},
                         {"id": "table-0", "role": "hazard", "hazard_kind": "glass", "reason": "r"}],
            "relations": [{"kind": "near_glass", "subject_id": "bed-0", "hazard_id": "ghost-9", "note": "n"},
                          {"kind": "in_tip_zone", "subject_id": "bed-0", "hazard_id": "table-0", "note": "n"}],
            "best_spot": {"x": float("nan"), "y": 0.5, "description": "d", "reason": "r"}, "exit_note": None}
    classified, relations, floor, _ = parse_classification(data, segments, SIZE)
    assert classified[0].role == "neutral"
    assert relations == []
    assert floor_rejection(floor, classified, SIZE) == "it is outside the photo"
    far = FloorProposal((1.5 * SIZE[0], 0.5 * SIZE[1]), "d", "r")
    assert floor_rejection(far, classified, SIZE) == "it is outside the photo"
