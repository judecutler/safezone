"""plan_route against a scripted OSRM. Geometry in metres east/north of HOME."""
import json
from datetime import datetime, timezone

import pytest

from safezone import geo, rules
from safezone.route import osrm, pipeline
from safezone.route.pipeline import plan_route
from safezone.shapes import BuildingProfile, DirectionOnly, HazardArea, NotInZone, WalkingRoute
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


OCEAN_COVERED = [rect(-3000, 150, -2000, 2000)]
SHORELINE_EDGED = [rect(-60, 400, -2000, 2000)]
LAND = {id(OCEAN_COVERED): [rect(150, 6000, -2000, 2000)], id(SHORELINE_EDGED): [rect(400, 6000, -2000, 2000)]}


def profile(polygons=OCEAN_COVERED, contains_home=True, hazard_known=True):
    area = HazardArea(contains_home=contains_home, polygons=polygons, land_polygons=LAND.get(id(polygons), []),
                      county="San Francisco",
                      map_url=None, source_url="https://cgs.test/hazard") if hazard_known else None
    return BuildingProfile(address="a", display_name="a", lon=HOME[0], lat=HOME[1], city="San Francisco",
                           footprint=None, flags=[], hazard_area=area, provenance="live")


def osrm_json(path, distance=None, steps=()):
    distance = geo.path_length_m(path) if distance is None else distance
    return {"code": "Ok", "routes": [{"geometry": {"type": "LineString", "coordinates": [list(p) for p in path]},
                                      "legs": [{"steps": list(steps)}], "distance": distance}]}


class ScriptedOsrm:
    """answer(origin, destination) -> dict | Response; records every destination asked for."""

    def __init__(self, answer, provenance="live"):
        self.answer = answer
        self.provenance = provenance
        self.asked = []

    def send(self, request):
        points = [tuple(float(v) for v in c.split(",")) for c in request.url.split("/foot/")[1].split(";")]
        self.asked.append(points[1])
        out = self.answer(points[0], points[1])
        return out if isinstance(out, Response) else Response(200, json.dumps(out), self.provenance)


def straight(origin, dest):
    return osrm_json([origin, dest])


def test_map_unavailable_gives_none_and_outside_gives_not_in_zone():
    assert plan_route(profile(hazard_known=False), ScriptedOsrm(straight), NOW) is None
    assert plan_route(profile(polygons=[]), ScriptedOsrm(straight), NOW) is None
    result = plan_route(profile(contains_home=False), ScriptedOsrm(straight), NOW)
    assert result == NotInZone(reason=rules.NOT_IN_ZONE)


def test_walking_route_ends_outside_with_clearance_at_conservative_pace():
    route = plan_route(profile(), ScriptedOsrm(straight), NOW)
    assert isinstance(route, WalkingRoute)
    assert not geo.point_in_any(route.destination, OCEAN_COVERED)
    assert geo.distance_to_boundary_m(route.destination, OCEAN_COVERED) >= pipeline.END_CLEARANCE_M
    assert route.destination == route.path[-1]
    assert route.walk_min == pytest.approx(route.distance_m / 60)
    assert route.origin == HOME and route.computed_at == NOW and route.provenance == "live"


def test_shortest_accepted_route_wins_even_when_its_destination_is_farther():
    def answer(origin, dest):
        nearest_candidate = abs(xy(dest)[1]) < 50
        return osrm_json([origin, dest], distance=900.0 if nearest_candidate else 400.0 + xy(dest)[0])
    route = plan_route(profile(), ScriptedOsrm(answer), NOW)
    assert isinstance(route, WalkingRoute)
    assert route.distance_m < 900.0
    assert abs(xy(route.destination)[1]) >= 50


def test_snapped_endpoint_inside_is_never_shown():
    def answer(origin, dest):
        return osrm_json([origin, ll(120, xy(dest)[1])])  # the road OSRM found is still inside
    result = plan_route(profile(), ScriptedOsrm(answer), NOW)
    assert isinstance(result, DirectionOnly)
    assert result.compass == "east"
    assert result.reason == "No walking route passed SafeZone's checks. Head east, inland and uphill, on foot."


def test_osrm_down_gives_direction_toward_nearest_candidate():
    transport = ScriptedOsrm(lambda o, d: Response(599, "no response", "live"))
    result = plan_route(profile(), transport, NOW)
    assert isinstance(result, DirectionOnly)
    assert result.compass == "east"
    assert result.straight_m == pytest.approx(250, abs=15)
    assert result.bearing_deg == pytest.approx(90, abs=3)
    assert result.provenance == "live"


def test_no_route_from_osrm_counts_as_a_failed_candidate():
    transport = ScriptedOsrm(lambda o, d: Response(400, json.dumps({"code": "NoRoute"}), "live"))
    assert isinstance(plan_route(profile(), transport, NOW), DirectionOnly)


def test_seaward_route_is_rejected_in_favour_of_an_inland_one():
    def answer(origin, dest):
        return osrm_json([origin, ll(-400, 0), ll(-400, 100), dest]) if abs(xy(dest)[1]) < 50 else osrm_json([origin, dest])
    route = plan_route(profile(), ScriptedOsrm(answer), NOW)
    assert isinstance(route, WalkingRoute)
    assert all(xy(p)[0] >= 0 for p in route.path)


def test_fallback_direction_points_at_mapped_land_never_the_water():
    # Shoreline-edged polygon: the geometrically nearest "outside" point is out to sea. Only the map's
    # land counts, so the water side is never even asked for. Inland routes double back, so none is accepted.
    def answer(origin, dest):
        x, y = xy(dest)
        if x < 0:
            return osrm_json([origin, ll(-40, y)])
        return osrm_json([origin, ll(x, y), ll(300, y), dest])
    transport = ScriptedOsrm(answer)
    result = plan_route(profile(polygons=SHORELINE_EDGED), transport, NOW)
    assert isinstance(result, DirectionOnly)
    assert min(xy(d)[0] for d in transport.asked) > 400, "only land-side candidates are tried"
    assert result.compass == "east"
    assert xy(result.destination)[0] > 400


def test_provenance_is_the_weakest_osrm_response():
    route = plan_route(profile(), ScriptedOsrm(straight, provenance="sample"), NOW)
    assert route.provenance == "sample"


def test_steps_are_built_from_maneuvers():
    steps = [
        {"maneuver": {"type": "depart", "bearing_after": 2}, "name": "48th Avenue", "distance": 210.5},
        {"maneuver": {"type": "turn", "modifier": "right", "bearing_after": 90}, "name": "Fulton Street", "distance": 240},
        {"maneuver": {"type": "new name", "bearing_after": 90}, "name": "", "distance": 30},
        {"maneuver": {"type": "arrive", "bearing_after": 90}, "name": "", "distance": 0},
    ]
    parsed = osrm.parse_route(osrm_json([HOME, ll(300, 0)], steps=steps))
    assert [s.instruction for s in parsed.steps] == ["Head north on 48th Avenue", "Turn right onto Fulton Street",
                                                     "Continue", "Arrive"]
    assert [s.distance_m for s in parsed.steps] == [210.5, 240, 30, 0]
    assert osrm.parse_route({"code": "NoRoute", "routes": []}) is None
    assert osrm.parse_route({"code": "Ok", "routes": []}) is None


def test_zero_length_turns_are_dropped_but_arrive_stays():
    from safezone.route.osrm import parse_route

    def step(kind, modifier, name, distance):
        return {"maneuver": {"type": kind, "modifier": modifier, "bearing_after": 0}, "name": name, "distance": distance}

    data = {"code": "Ok", "routes": [{"distance": 300.0, "geometry": {"coordinates": [[0, 0], [0, 0.001]]},
            "legs": [{"steps": [step("depart", None, "48th Avenue", 220.0), step("turn", "right", "Fulton Street", 80.0),
                                step("turn", "right", "46th Avenue", 0.0), step("arrive", None, "", 0.0)]}]}]}
    steps = parse_route(data).steps
    assert [s.distance_m for s in steps] == [220.0, 80.0, 0.0]
    assert steps[-1].instruction.startswith("Arrive")
