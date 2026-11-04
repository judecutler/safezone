"""Pure route invariants. Geometry is given in metres east/north of HOME and converted at the edge."""
import itertools

import pytest

from safezone import geo
from safezone.route import pipeline
from safezone.route.pipeline import check_route, candidate_destinations

HOME = (-122.5100, 37.7700)
FRAME = geo.LocalFrame(HOME)


def ll(x, y):
    return FRAME.to_lonlat(x, y)


def rect(x0, x1, y0, y1):
    return [[ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1)]]


def path(*pts):
    return [ll(x, y) for x, y in pts]


# The official polygon covers the water: 3 km of ocean west of home, land boundary 150 m east.
OCEAN_COVERED = [rect(-3000, 150, -2000, 2000)]
# The official polygon stops at the shoreline, 100 m west of home.
SHORELINE_EDGED = [rect(-100, 150, -2000, 2000)]
# The map's own "outside hazard area" land, east of both.
LAND = [rect(150, 6000, -2000, 2000)]


def test_straight_route_out_passes():
    assert check_route(HOME, path((0, 0), (300, 0)), OCEAN_COVERED, LAND) == []


def test_route_ending_inside_or_hugging_the_boundary_is_rejected():
    assert "ends_inside" in check_route(HOME, path((0, 0), (100, 0)), OCEAN_COVERED, LAND)
    assert "ends_inside" in check_route(HOME, path((0, 0), (180, 0)), OCEAN_COVERED, LAND)
    assert "ends_inside" not in check_route(HOME, path((0, 0), (210, 0)), OCEAN_COVERED, LAND)


def test_seaward_leg_is_rejected_when_the_polygon_covers_the_water():
    failures = check_route(HOME, path((0, 0), (-300, 0), (-300, 100), (300, 100)), OCEAN_COVERED, LAND)
    assert "goes_deeper" in failures
    assert "moves_away_from_exit" in failures


def test_seaward_leg_is_rejected_when_the_shoreline_is_the_boundary():
    # Walking toward the water here brings the path closer to the polygon edge, so a depth
    # check alone would accept it. Only the exit-axis check sees the seaward leg.
    failures = check_route(HOME, path((0, 0), (-90, 0), (-90, 100), (300, 100)), SHORELINE_EDGED, LAND)
    assert failures == ["moves_away_from_exit"]


def test_small_detours_inside_are_tolerated():
    assert check_route(HOME, path((0, 0), (-50, 0), (-50, 100), (300, 100)), SHORELINE_EDGED, LAND) == []
    assert check_route(HOME, path((0, 0), (-50, 0), (-50, 100), (300, 100)), OCEAN_COVERED, LAND) == []


def test_re_entry_over_100m_is_rejected():
    assert "re_enters" in check_route(HOME, path((0, 0), (200, 0), (0, 50), (300, 50)), OCEAN_COVERED, LAND)
    assert check_route(HOME, path((0, 0), (200, 0), (120, 50), (300, 50)), OCEAN_COVERED, LAND) == []


def test_route_wholly_inside_fails_only_the_end_checks():
    assert check_route(HOME, path((0, 0), (50, 0)), OCEAN_COVERED, LAND) == ["ends_inside", "ends_off_land"]


def test_candidates_are_outside_with_clearance_sorted_and_spaced():
    candidates = candidate_destinations(HOME, OCEAN_COVERED, LAND)
    assert 1 <= len(candidates) <= pipeline.MAX_CANDIDATES
    for c in candidates:
        assert not geo.point_in_any(c, OCEAN_COVERED)
        assert geo.distance_to_boundary_m(c, OCEAN_COVERED) >= pipeline.CLEARANCE_M - 0.01
        assert geo.haversine_m(HOME, c) <= pipeline.CANDIDATE_RADIUS_M + pipeline.PUSH_LIMIT_M
    distances = [geo.haversine_m(HOME, c) for c in candidates]
    assert all(a <= b + 0.1 for a, b in zip(distances, distances[1:]))
    assert distances[0] == pytest.approx(250, abs=15)
    for a, b in itertools.combinations(candidates, 2):
        assert geo.haversine_m(a, b) >= pipeline.CANDIDATE_SPACING_M - 1


def test_candidates_never_land_in_the_water_beyond_a_shoreline_edge():
    # The water side of a shoreline-edged polygon is geometrically "outside" too; only mapped land counts.
    candidates = candidate_destinations(HOME, SHORELINE_EDGED, LAND)
    assert candidates
    assert all(FRAME.to_xy(c)[0] > 150 for c in candidates)


def test_no_land_polygons_means_no_candidates_and_no_proven_end():
    assert candidate_destinations(HOME, OCEAN_COVERED, []) == []
    assert "ends_off_land" in check_route(HOME, path((0, 0), (300, 0)), OCEAN_COVERED)


def test_no_candidate_when_the_boundary_is_too_far():
    assert candidate_destinations(HOME, [rect(-10000, 5000, -8000, 8000)], [rect(5000, 9000, -8000, 8000)]) == []


def test_candidate_requires_room_to_push_outward():
    # A 60 m wide safe strip between two hazard polygons never reaches 100 m clearance.
    sandwiched = [rect(-3000, 150, -2000, 2000), rect(210, 5000, -2000, 2000)]
    land = [rect(150, 210, -2000, 2000), rect(-3000, 5000, 2000, 6000)]
    candidates = candidate_destinations(HOME, sandwiched, land)
    assert candidates, "the open ground north of both polygons is still reachable"
    for c in candidates:
        x, y = FRAME.to_xy(c)
        assert not (150 < x < 210 and abs(y) < 2000)
        assert geo.distance_to_boundary_m(c, sandwiched) >= pipeline.CLEARANCE_M - 0.01
