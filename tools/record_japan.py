"""Record real responses for the Japan demo address and add them to fixtures/demo.

Run on a machine with internet access (no key needed; every Japan source is public):
    python tools/record_japan.py
It runs the Japan region live (Nominatim, the Hazard Map Portal tsunami tiles, GSI's tsunami evacuation site
tiles, Overpass and OSRM), prints one line per call and every failed call, saves each exchange to a fresh
fixtures/demo.recording-jp-<time>/ folder, then copies the files into fixtures/demo next to the US ones.

tools/record_fixtures.py empties fixtures/demo before it copies, so run this one after it.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safezone.building import osm  # noqa: E402
from safezone import regions  # noqa: E402
from safezone.shapes import Household, LonLat  # noqa: E402
from safezone.transport import RecordingTransport, ReplayTransport, Transport  # noqa: E402
from tools.demo import build_plan_jp, write_plan_jp  # noqa: E402
from tools.record_fixtures import FailureLog  # noqa: E402
from tools.samples.japan import JP_DEMO_HOME  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "demo"
JP_HOUSEHOLD = Household(children=True, wheelchair=False, medical=False, pets=True)


def run(transport: Transport, place: LonLat, now: datetime) -> dict:
    # By coordinates: Nominatim answered 200 with no match for the written address 鎌倉市御成町18-10.
    found = regions.profile_for_point(*place, transport)
    if isinstance(found, regions.NoCoverage):
        raise SystemExit(f"{place} is outside every region: {found.reason}")
    region, profile = found
    if region.id != "jp":
        raise SystemExit(f"{place} is in region {region.id}, not jp")
    evac = regions.evacuate(profile, JP_HOUSEHOLD, transport, transport, now, False)
    assert isinstance(evac, regions.Evacuation)
    return {"profile": profile.model_dump(mode="json"), "route": evac.route and evac.route.model_dump(mode="json"),
            "shelters": evac.shelters and evac.shelters.model_dump(mode="json"), "shelters_error": evac.shelters_error}


def summarize(result: dict) -> None:
    profile, route, shelters = result["profile"], result["route"], result["shelters"]
    print(f"\naddress: {profile['display_name']} ({profile['lat']:.5f}, {profile['lon']:.5f})")
    for flag in profile["flags"]:
        print(f"  flag: {flag['value']} [{flag['provenance']}]")
    if route is None:
        print("  route: none (the tsunami map could not be read)")
    elif route["kind"] == "site_route":
        site = route["site"]
        print(f"  route: {route['walk_min']:.0f} min, {route['distance_m']:.0f} m to {site['name']} "
              f"({site['kind']}, {site['depth']}); home depth {route['home_depth']}")
    else:
        print(f"  route: {route['kind']}: {route.get('reason', '')}")
    if shelters is None:
        print(f"  sites: unavailable ({result['shelters_error']})")
    else:
        print(f"  sites outside the inundation area: {len(shelters['matches'])}; excluded {shelters['excluded']}")
        for m in shelters["matches"][:5]:
            print(f"    {m['walk_min']:.0f} min  {m['shelter']['name']}  {m['shelter']['address']}")


def main() -> None:
    osm.OVERPASS_BUDGET_S = 180.0  # nobody is waiting on a screen; give every Overpass instance its full wait
    parser = argparse.ArgumentParser()
    parser.add_argument("--lon", type=float, default=JP_DEMO_HOME[0])
    parser.add_argument("--lat", type=float, default=JP_DEMO_HOME[1])
    args = parser.parse_args()
    log = FailureLog(regions.live_transport())
    # A fresh folder per run: on Windows, OneDrive or an editor can hold an old one locked.
    staging = ROOT / "fixtures" / f"demo.recording-jp-{datetime.now():%Y%m%d-%H%M%S}"
    now = datetime.now(timezone.utc)
    place = (args.lon, args.lat)
    print(f"Recording the Japan demo place at {args.lat:.5f}, {args.lon:.5f}. Tiles are small; this takes about a minute.")
    try:
        result = run(RecordingTransport(log, staging, provenance="recorded"), place, now)
    finally:
        print(f"\n{len(log.failures)} failed calls" + (":" if log.failures else "."))
        for line in log.failures:
            print("  " + line)
    summarize(result)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in staging.glob("*.json"):
        shutil.copy2(path, FIXTURES / path.name)
        copied += 1
    shutil.rmtree(staging, ignore_errors=True)
    assert run(ReplayTransport(FIXTURES), place, now) == result, "replay differs from the recording"
    print(f"\ncopied {copied} recorded files into {FIXTURES.relative_to(ROOT)}; replay matches.")
    if log.failures or result["route"] is None:
        print("Kept the SAMPLE Kamakura demo (demo/plan_jp.json): the recording is incomplete. Paste this output to Claude.")
        return
    write_plan_jp(build_plan_jp(ReplayTransport(FIXTURES), now))


if __name__ == "__main__":
    main()
