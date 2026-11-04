"""The region registry: routing a place to its adapters, and an honest answer where SafeZone has no data."""
from datetime import datetime, timezone

import pytest

from safezone import regions
from safezone.building.geocode import GeocodeNotFound
from safezone.japan import rules as jp_rules
from safezone.shapes import Household
from safezone.transport import Response
from tools.demo import SampleResponder
from tools.samples import japan as jp_sample
from tools.samples.geo import DEMO_ADDRESS

NOW = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)


class Both:
    """US samples first, then Japan samples, like the real services answering their own countries."""

    def send(self, request):
        return jp_sample.respond(request) or SampleResponder().send(request)


def test_us_address_uses_the_existing_pipeline_unchanged():
    region, profile = regions.profile_for_address(DEMO_ADDRESS, Both())
    assert region.id == "us-ca" and profile.hazard_area and profile.hazard_area.contains_home
    evac = regions.evacuate(profile, Household(), Both(), Both(), NOW, True)
    assert evac.route.kind == "walking_route" and evac.shelters is not None


def test_japanese_address_goes_to_the_japan_region():
    region, _ = regions.profile_for_address(jp_sample.JP_DEMO_ADDRESS, Both())
    assert region.id == "jp"


def test_point_picks_the_region_by_its_box():
    assert regions.region_for_point(jp_sample.JP_DEMO_HOME).id == "jp"
    assert regions.region_for_point((-122.51, 37.77)).id == "us-ca"
    assert regions.region_for_point((2.35, 48.85)) is None


def test_point_outside_every_region_gets_no_coverage_and_no_lookup():
    class NoCalls:
        def send(self, request):
            raise AssertionError(f"looked up {request.url}")

    result = regions.profile_for_point(2.35, 48.85, NoCalls())
    assert isinstance(result, regions.NoCoverage) and result.reason == regions.NO_COVERAGE
    assert "Japan" in result.regions


def test_point_whose_country_is_not_japan_gets_no_coverage():
    class Korea:
        def send(self, request):
            body = '{"lat": "37.5", "lon": "126.9", "display_name": "Seoul", "address": {"country_code": "kr"}}'
            return Response(200, body, "sample")

    assert isinstance(regions.profile_for_point(126.98, 37.57, Korea()), regions.NoCoverage)


def test_geocoded_place_outside_every_region_gets_no_coverage():
    class Paris:
        def send(self, request):
            hit = '[{"lat": "48.85", "lon": "2.35", "display_name": "Paris", "address": {"state": "Ile-de-France"}}]'
            return Response(200, hit, "sample")

    assert isinstance(regions.profile_for_address("Paris", Paris()), regions.NoCoverage)


def test_unknown_address_still_raises_not_found():
    class Empty:
        def send(self, request):
            return Response(200, "[]", "sample")

    with pytest.raises(GeocodeNotFound):
        regions.profile_for_address("nowhere at all", Empty())


def test_guidance_per_region():
    us = regions.guidance("us-ca")
    jp = regions.guidance("jp")
    assert us["go_now"] and jp["language"] == "ja"
    assert regions.guidance("xx") == us and regions.guidance(None) == us
    for quote in jp["quotes"]["go_now"]:
        assert quote["ja"] and quote["en"] and quote["source_url"].startswith("https://")


@pytest.mark.parametrize("quote", jp_rules.DURING_SHAKING)
def test_shaking_guidance_never_tells_anyone_to_move(quote):
    for word in ("避難", "evacuate", "leave", "go to", "run"):
        assert word not in quote.ja and word not in quote.en.lower()


def test_every_region_has_complete_wiring():
    for region in regions.REGIONS.values():
        g = region.guidance()
        assert {"during", "after", "go_now", "stay_away", "not_in_zone", "disclaimers", "sources"} <= g.keys()
