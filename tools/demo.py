"""Build the demo household's plan by running every pipeline through one transport.

`python tools/demo.py samples` regenerates the hand-authored SAMPLE fixtures and
rebuilds demo/plan.json from them. `python tools/demo.py replay` rebuilds the plan
from whatever fixtures/demo holds (after tools/record_fixtures.py, real ones).
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from safezone.building.cgs import in_hazard_area  # noqa: E402
from safezone.building.pipeline import build_profile  # noqa: E402
from safezone.config import load_settings  # noqa: E402
from safezone.meta import MetaClient  # noqa: E402
from safezone.room.pipeline import prepare_image, scan_room  # noqa: E402
from safezone.route.pipeline import plan_route  # noqa: E402
from safezone.shapes import DirectionOnly, Household, Plan, WalkingRoute  # noqa: E402
from safezone.shelter.pipeline import find_shelters  # noqa: E402
from safezone.transport import RecordingTransport, ReplayTransport, Request, Response, Transport  # noqa: E402
from tools.samples import building, room, route, shelter  # noqa: E402
from tools.samples.geo import DEMO_ADDRESS  # noqa: E402

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


def write_plan(payload: dict) -> None:
    PLAN.write_text(json.dumps(payload, indent=1))
    plan = payload["plan"]
    print(f"wrote {PLAN.relative_to(ROOT)}: {len(plan['rooms'][0]['classified'])} objects, "
          f"route {plan['route']['kind']}, {len(plan['shelters']['matches'])} shelters")


def main(mode: str) -> None:
    now = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
    if mode == "samples":
        if FIXTURES.exists():
            shutil.rmtree(FIXTURES)
        build_plan(RecordingTransport(SampleResponder(), FIXTURES, provenance="sample"), True, now)
    elif mode != "replay":
        raise SystemExit("usage: python tools/demo.py samples|replay")
    write_plan(build_plan(ReplayTransport(FIXTURES), True, now))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "replay")
