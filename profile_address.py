"""Print the building profile for an address.

    python profile_address.py "<address>"                          live network
    python profile_address.py "<address>" --fixtures fixtures/demo replay saved responses
    python profile_address.py --record-samples fixtures/demo       save the SAMPLE answers for both demo addresses
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from safezone.building.geocode import GeocodeNotFound
from safezone.building.pipeline import build_profile
from safezone.shapes import BuildingProfile
from safezone.transport import HttpError, LiveTransport, RecordingTransport, ReplayTransport, Transport
from tools.samples import building as samples
from tools.samples.geo import DEMO_ADDRESS, OUTSIDE_ADDRESS


def record_samples(directory: Path) -> None:
    recorder = RecordingTransport(samples.SampleTransport(), directory, provenance="sample")
    for address in (DEMO_ADDRESS, OUTSIDE_ADDRESS):
        build_profile(address, recorder)


def render(profile: BuildingProfile) -> str:
    lines = [profile.display_name, f"({profile.lat:.5f}, {profile.lon:.5f})  data: {profile.provenance}", ""]
    for f in profile.flags:
        lines += [f"[{f.tone.upper()}] {f.kind}: {f.value}", f"    {f.detail}"]
        if f.status:
            lines.append(f"    status: {f.status}")
        lines += [f"    source: {f.source_name} <{f.source_url}> ({f.provenance})", ""]
    area = profile.hazard_area
    lines.append(f"hazard polygons nearby: {len(area.polygons)}" if area else "hazard polygons nearby: unknown")
    lines.append(f"footprint: {len(profile.footprint)} points" if profile.footprint else "footprint: not mapped")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="SafeZone building profile")
    parser.add_argument("address", nargs="?")
    parser.add_argument("--fixtures", type=Path, help="replay saved responses from this directory")
    parser.add_argument("--record-samples", type=Path, metavar="DIR", help="save the SAMPLE answers into DIR")
    args = parser.parse_args(argv)
    if args.record_samples:
        record_samples(args.record_samples)
        print(f"recorded SAMPLE building responses into {args.record_samples}")
        if not args.address:
            return 0
    if not args.address:
        parser.error("an address is required")
    transport: Transport = ReplayTransport(args.fixtures) if args.fixtures else LiveTransport()
    try:
        print(render(build_profile(args.address, transport)))
    except GeocodeNotFound:
        print(f"Address not found: {args.address}", file=sys.stderr)
        return 1
    except HttpError as exc:
        print(f"Address lookup could not be reached: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
