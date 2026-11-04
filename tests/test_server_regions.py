"""The JSON API in both regions, and the honest "no data" answer outside them, through the real Starlette app."""
import json
from urllib.parse import quote
from datetime import datetime, timezone

from safezone import regions
from safezone.app import Services, create_app
from safezone.config import ROOT
from safezone.shapes import Plan
from safezone.transport import ReplayTransport
from tests.asgi import call
from tests.test_server_api import SETTINGS
from tools.demo import SampleResponder, build_plan_jp
from tools.samples import japan as jp_sample
from tools.samples.geo import DEMO_ADDRESS, DEMO_HOME

FIXTURES = ROOT / "fixtures" / "demo"
DEMO_PLAN = ROOT / "demo" / "plan.json"
NOW = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
NEBRASKA = (-99.9, 41.5)
PARIS = (2.35, 48.85)


class Both:
    """Japan samples first, then US samples, like the real services answering their own countries."""

    def send(self, request):
        return jp_sample.respond(request) or SampleResponder().send(request)


class NoCalls:
    def send(self, request):
        raise AssertionError(f"looked up {request.url}")


class Nebraska:
    """Nominatim placing the point in Nebraska; every other source answers nothing."""

    def send(self, request):
        from safezone.transport import Response
        if "reverse" in request.url:
            body = {"lat": "41.5", "lon": "-99.9", "display_name": "Custer County, Nebraska, United States",
                    "address": {"road": "Road 1", "county": "Custer County", "state": "Nebraska",
                                "country_code": "us"}}
            return Response(200, json.dumps(body), "sample")
        return Response(599, "offline", "sample")


def app(transport=None):
    t = transport or Both()
    return create_app(Services(SETTINGS, t, t, True, DEMO_PLAN))


def get(transport, url):
    return call(app(transport), "GET", url)


def post_evac(transport, building, household=None):
    body = json.dumps({"building": building, "household": household or {}}).encode()
    return call(app(transport), "POST", "/api/evac", body, "application/json")


# us-ca: the recorded demo replays exactly as before ----------------------------------------------------------

def test_us_demo_address_replays_from_the_recorded_fixtures():
    r = get(ReplayTransport(FIXTURES), f"/api/profile?address={quote(DEMO_ADDRESS)}")
    assert r.status == 200
    body = r.json()
    assert body["region"] == "us-ca" and body["provenance"] == "recorded"
    assert body["hazard_area"]["contains_home"]
    shipped = json.loads(DEMO_PLAN.read_text())["plan"]["building"]
    assert {**body, "region": None} == {**shipped, "region": None}


def test_us_evac_replays_the_recorded_route_and_shelters():
    plan = json.loads(DEMO_PLAN.read_text())["plan"]
    r = post_evac(ReplayTransport(FIXTURES), plan["building"], plan["household"])
    assert r.status == 200
    body = r.json()
    assert body["route"]["kind"] == plan["route"]["kind"] == "walking_route"
    assert body["route"]["path"] == plan["route"]["path"] and body["route"]["provenance"] == "recorded"
    assert [m["shelter"]["name"] for m in body["shelters"]["matches"]] == \
        [m["shelter"]["name"] for m in plan["shelters"]["matches"]]
    assert body["shelters_error"] is None


def test_evac_accepts_the_profile_exactly_as_the_profile_endpoint_returned_it():
    building = get(Both(), f"/api/profile?lat={DEMO_HOME[1]}&lon={DEMO_HOME[0]}").json()
    assert building["region"] == "us-ca"
    r = post_evac(Both(), building)
    assert r.status == 200 and r.json()["route"]["kind"] == "walking_route"


def test_us_guidance_keeps_its_keys_and_is_the_default():
    default, us = get(NoCalls(), "/api/guidance").json(), get(NoCalls(), "/api/guidance?region=us-ca").json()
    assert default == us
    assert {"during", "during_special", "after", "go_now", "stay_away", "not_in_zone", "disclaimers", "sources",
            "hazard_labels"} <= us.keys()
    assert "quotes" not in us


def test_us_demo_is_unchanged_and_names_its_region():
    body = get(NoCalls(), "/api/demo").json()
    assert body["region"] == "us-ca" and body["plan"]["rooms"]
    assert body["plan"] == json.loads(DEMO_PLAN.read_text())["plan"]


# jp: Kamakura on the samples ---------------------------------------------------------------------------------

def test_jp_address_profile_is_tagged_jp_and_sample():
    r = get(Both(), f"/api/profile?address={quote(jp_sample.JP_DEMO_ADDRESS)}")
    assert r.status == 200
    body = r.json()
    assert body["region"] == "jp" and body["provenance"] == "sample"
    assert body["flags"][0]["kind"] == "tsunami_zone" and body["flags"][0]["tone"] == "alert"


def test_jp_point_profile_is_tagged_jp():
    lon, lat = jp_sample.JP_DEMO_HOME
    body = get(Both(), f"/api/profile?lat={lat}&lon={lon}").json()
    assert body["region"] == "jp" and body["hazard_area"]["contains_home"]


def test_jp_evac_returns_a_site_route_and_sites():
    building = get(Both(), f"/api/profile?address={quote(jp_sample.JP_DEMO_ADDRESS)}").json()
    body = post_evac(Both(), building, {"pets": True}).json()
    route = body["route"]
    assert route["kind"] == "site_route" and route["provenance"] == "sample"
    assert {"name", "instruction", "depth", "kind", "source_url"} <= route["site"].keys()
    assert body["shelters"]["matches"] and body["shelters_error"] is None


def test_jp_guidance_adds_the_official_quotes():
    body = get(NoCalls(), "/api/guidance?region=jp").json()
    assert body["region"] == "jp"
    assert all({"ja", "en", "source_url"} <= q.keys() for q in body["quotes"]["during"])


def test_jp_demo_is_the_labelled_sample_kamakura_plan_without_a_room():
    body = get(NoCalls(), "/api/demo?region=jp").json()
    plan = Plan.model_validate(body["plan"])
    assert body["region"] == "jp" and plan.rooms == [] and "no room was scanned" in body["note"]
    assert plan.building.provenance == plan.route.provenance == "sample"
    assert plan.route.kind == "site_route" and plan.shelters.matches
    assert plan.shelters.provenance == "sample"


def test_the_shipped_jp_demo_matches_a_fresh_build_from_the_samples():
    shipped = json.loads((ROOT / "demo" / "plan_jp.json").read_text())
    assert shipped == json.loads(json.dumps(build_plan_jp(jp_sample.SampleTransport(), NOW)))


def test_a_saved_plan_with_a_site_route_validates():
    Plan.model_validate(json.loads((ROOT / "demo" / "plan_jp.json").read_text())["plan"])


# Outside every region ----------------------------------------------------------------------------------------

def test_point_outside_every_region_is_no_coverage_without_any_lookup():
    r = get(NoCalls(), f"/api/profile?lat={PARIS[1]}&lon={PARIS[0]}")
    assert r.status == 200
    body = r.json()
    assert body["kind"] == "no_coverage" and body["reason"] == regions.NO_COVERAGE
    assert "Japan" in " ".join(body["regions"])


def test_evac_for_a_building_outside_every_region_is_no_coverage():
    building = get(Both(), f"/api/profile?address={quote(DEMO_ADDRESS)}").json()
    building = {**building, "lon": PARIS[0], "lat": PARIS[1]}
    body = post_evac(NoCalls(), building).json()
    assert body == {"route": None, "shelters": None, "shelters_error": regions.NO_COVERAGE}


def test_a_nebraska_point_keeps_the_existing_us_answer_no_state_map():
    """us-ca accepts every US state (docs/regions.md), so Nebraska is not no_coverage: it says there is no map."""
    body = get(Nebraska(), f"/api/profile?lat={NEBRASKA[1]}&lon={NEBRASKA[0]}").json()
    assert body["region"] == "us-ca"
    (zone,) = [f for f in body["flags"] if f["kind"] == "tsunami_zone"]
    assert zone["tone"] == "unknown" and zone["value"] == "No tsunami map for this state"
    assert body["hazard_area"] is None
