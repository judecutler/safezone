from safezone import geo
from safezone.building import cgs, osm
from safezone.geo import LocalFrame
from safezone.shapes import HazardArea

OUTER_CW = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]
HOLE_CCW = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]
OTHER_CW = [(20.0, 0.0), (20.0, 5.0), (25.0, 5.0), (25.0, 0.0), (20.0, 0.0)]


def test_esri_rings_group_into_polygons_with_holes():
    data = {"features": [{"attributes": {"Evacuate": "Yes, Tsunami Hazard Area"},
                          "geometry": {"rings": [OUTER_CW, OTHER_CW, HOLE_CCW]}}]}
    polygons = cgs.parse_polygons(data)
    assert len(polygons) == 2
    assert geo.point_in_any((1.0, 1.0), polygons)
    assert geo.point_in_any((22.0, 2.0), polygons)
    assert not geo.point_in_any((5.0, 5.0), polygons)


def test_outside_polygons_are_not_hazard_area():
    data = {"features": [{"attributes": {"Evacuate": "No, Outside Hazard Area"},
                          "geometry": {"rings": [OUTER_CW]}}]}
    assert cgs.parse_polygons(data) == []


def test_point_inside_when_any_feature_says_yes():
    data = {"features": [{"attributes": {"Evacuate": "No, Outside Hazard Area", "County": "Marin"}},
                         {"attributes": {"Evacuate": "Yes, Tsunami Hazard Area", "County": "San Francisco",
                                         "Map_Link": "https://example.org/map.pdf"}}]}
    assert cgs.parse_point(data) == (True, "San Francisco", "https://example.org/map.pdf")
    assert cgs.parse_point({"features": []}) == (False, None, None)


def area(inside):
    return HazardArea(contains_home=inside, polygons=[], county=None, map_url=cgs.MAPS_PAGE,
                      source_url=cgs.LAYER_URL)


def test_zone_flag_wording():
    inside, outside = cgs.zone_flag(area(True), "live"), cgs.zone_flag(area(False), "live")
    assert (inside.tone, inside.value) == ("alert", "In the tsunami hazard area")
    assert "leave on foot right away" in inside.detail
    assert (outside.tone, outside.value) == ("ok", "Outside the mapped tsunami hazard area")
    assert "tsunamis only, not shaking" in outside.detail
    assert "safe" not in outside.value.lower() + outside.detail.lower()


HOME = (-122.5, 37.77)
FRAME = LocalFrame(HOME)


def box(cx, cy, half):
    return [FRAME.to_lonlat(cx + dx, cy + dy) for dx, dy in ((-half, -half), (half, -half), (half, half),
                                                           (-half, half), (-half, -half))]


def way(ring, tags):
    return {"type": "way", "id": 1, "tags": tags, "geometry": [{"lon": x, "lat": y} for x, y in ring]}


def test_containing_building_wins_over_a_nearer_edge():
    data = {"elements": [way(box(12, 0, 5), {"building": "yes", "building:levels": "9"}),
                         way(box(0, 0, 10), {"building": "yes", "building:levels": "3"})]}
    chosen = osm.choose_building(osm.parse_buildings(data), HOME)
    assert chosen.tags["building:levels"] == "3"


def test_nearest_building_within_25_m_when_none_contains():
    data = {"elements": [way(box(20, 0, 5), {"building": "yes", "building:levels": "4"}),
                         way(box(0, 30, 5), {"building": "yes", "building:levels": "6"})]}
    assert osm.choose_building(osm.parse_buildings(data), HOME).tags["building:levels"] == "4"
    far = {"elements": [way(box(40, 0, 5), {"building": "yes"})]}
    assert osm.choose_building(osm.parse_buildings(far), HOME) is None


def test_osm_flags_only_when_mapped():
    b = osm.Building(footprint=box(0, 0, 5), tags={"building": "yes", "building:levels": "1", "start_date": "1925"})
    flags = osm.building_flags(b, HOME, "live")
    assert [(f.kind, f.value) for f in flags] == [("storeys", "1 storey"), ("year_built", "Built 1925")]
    assert all(f.tone == "info" and "can be wrong" in f.detail for f in flags)
    bare = osm.Building(footprint=box(0, 0, 5), tags={"building": "yes", "building:levels": "lots"})
    assert osm.building_flags(bare, HOME, "live") == []
