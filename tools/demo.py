"""Build the demo household's plan by running every pipeline through one transport.

`python tools/demo.py samples` regenerates the hand-authored SAMPLE fixtures and
rebuilds demo/plan.json from them. `python tools/demo.py replay` rebuilds the plan
from whatever fixtures/demo holds (after tools/record_fixtures.py, real ones).
`python tools/demo.py fill-samples` keeps every real recording, replaces FEMA's
answer with SAMPLE shelters (the live layer is empty on quiet days), and records
SAMPLE answers only for requests the recording lacks, such as the outside address.
Overpass is never filled: a sample storeys count on the real building would be invented.
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from safezone.building.cgs import in_hazard_area  # noqa: E402
from safezone.building.osm import OVERPASS_URL  # noqa: E402
from safezone.building.pipeline import build_profile  # noqa: E402
from safezone.config import load_settings  # noqa: E402
from safezone.meta import MetaClient  # noqa: E402
from safezone.room.pipeline import prepare_image, scan_room  # noqa: E402
from safezone.room.segment import MASKS_NOT_DECODED  # noqa: E402
from safezone.route.pipeline import plan_route  # noqa: E402
from safezone.shapes import DirectionOnly, Household, Plan, WalkingRoute  # noqa: E402
from safezone.shelter.pipeline import find_shelters  # noqa: E402
from safezone.app import FEMA_HOST, HostSplit  # noqa: E402
from safezone.transport import (NETWORK_FAILURE, RecordingTransport, ReplayTransport, Request,  # noqa: E402
                                Response, Transport)
from tools.samples import building, room, route, shelter  # noqa: E402
from tools.samples.geo import DEMO_ADDRESS, OUTSIDE_ADDRESS  # noqa: E402

FIXTURES = ROOT / "fixtures" / "demo"
PHOTO = ROOT / "demo" / "living_room.jpg"
PLAN = ROOT / "demo" / "plan.json"
DEMO_HOUSEHOLD = Household(children=True, wheelchair=True, medical=False, pets=True)
DEMO_ROOM_NAME = "Bedroom"


@dataclass(frozen=True)
class SampleResponder:
    def send(self, request: Request) -> Response:
        for area in (room, building, route, shelter):
            answer = area.respond(request)
            if answer is not None:
                return answer
        return Response(599, f"no sample for {request.url}", "sample")


@dataclass(frozen=True)
class ReplayOrSample:
    """Replays saved fixtures; a request with no fixture is answered and recorded from the samples."""
    replay: Transport
    sample: Transport

    def send(self, request: Request) -> Response:
        resp = self.replay.send(request)
        return self.sample.send(request) if resp.status == NETWORK_FAILURE else resp


def build_plan(transport: Transport, shelter_replay: bool, now: datetime) -> dict:
    settings = load_settings()
    profile = build_profile(DEMO_ADDRESS, transport)
    scan = scan_room(prepare_image(PHOTO.read_bytes()), DEMO_ROOM_NAME, MetaClient(transport, settings))
    evac_route = plan_route(profile, transport, now)
    origin = evac_route.destination if isinstance(evac_route, (WalkingRoute, DirectionOnly)) else (profile.lon, profile.lat)
    shelters = find_shelters(origin, profile, DEMO_HOUSEHOLD, transport,
                             lambda p: in_hazard_area(transport, p), now, shelter_replay)
    plan = Plan(building=profile, household=DEMO_HOUSEHOLD, rooms=[scan], route=evac_route,
                shelters=shelters, generated_at=now)
    return {"plan": plan.model_dump(mode="json"), "images": {scan.id: "/demo/living_room.jpg"}}


def exercise_outside_address(transport: Transport, now: datetime) -> None:
    """Records the out-of-zone address too, so the offline demo can show the stay-put branch."""
    profile = build_profile(OUTSIDE_ADDRESS, transport)
    evac_route = plan_route(profile, transport, now)
    find_shelters((profile.lon, profile.lat), profile, Household(), transport,
                  lambda p: in_hazard_area(transport, p), now, True)
    assert evac_route is not None and evac_route.kind == "not_in_zone"



def write_plan(payload: dict) -> None:
    if any(note == MASKS_NOT_DECODED for room in payload["plan"]["rooms"] for note in room["notes"]):
        raise SystemExit("Not writing demo/plan.json: masks did not decode here (pip install meta-sam-parser), "
                         "so the room would show boxes instead of the recorded outlines.")
    PLAN.write_text(json.dumps(payload, indent=1))
    plan = payload["plan"]
    print(f"wrote {PLAN.relative_to(ROOT)}: {len(plan['rooms'][0]['classified'])} objects, "
          f"route {plan['route']['kind']}, {len(plan['shelters']['matches'])} shelters")


def main(mode: str) -> None:
    now = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
    if mode == "samples":
        if FIXTURES.exists():
            shutil.rmtree(FIXTURES)
        recorder = RecordingTransport(SampleResponder(), FIXTURES, provenance="sample")
        build_plan(recorder, True, now)
        exercise_outside_address(recorder, now)
    elif mode == "fill-samples":
        sample = RecordingTransport(SampleResponder(), FIXTURES, provenance="sample")
        replay = ReplayTransport(FIXTURES)
        filled = HostSplit(urlsplit(OVERPASS_URL).hostname, replay, ReplayOrSample(replay, sample))
        transport = HostSplit(FEMA_HOST, sample, filled)
        build_plan(transport, True, now)
        exercise_outside_address(transport, now)
    elif mode != "replay":
        raise SystemExit("usage: python tools/demo.py samples|replay|fill-samples")
    write_plan(build_plan(ReplayTransport(FIXTURES), True, now))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "replay")
