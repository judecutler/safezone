"""Scan one room photo and print the ranked safe spots and fixes.

  python run.py PHOTO                          live Meta Model API (needs MODEL_API_KEY)
  python run.py PHOTO --fixtures DIR           replay saved responses, no network
  python run.py PHOTO --record-samples DIR     answer from tools/samples and save the exchanges to DIR
  python run.py PHOTO --record DIR             live, and save the exchanges to DIR
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from safezone.config import load_settings
from safezone.meta import MetaClient
from safezone.room.pipeline import prepare_image, scan_room
from safezone.shapes import RoomScan
from safezone.transport import (NETWORK_FAILURE, LiveTransport, RecordingTransport, ReplayTransport, Request,
                                Response, Transport)
from tools.samples import room as room_samples


@dataclass
class SampleResponder:
    """Answers from hand-authored sample responders; anything none of them answers reads as a network failure."""
    responders: list[Callable[[Request], Response | None]]

    def send(self, request: Request) -> Response:
        for respond in self.responders:
            resp = respond(request)
            if resp is not None:
                return resp
        return Response(NETWORK_FAILURE, f"no sample for {request.describe()}", "sample")


def transport_for(args: argparse.Namespace) -> Transport:
    if args.fixtures:
        return ReplayTransport(Path(args.fixtures))
    if args.record_samples:
        return RecordingTransport(SampleResponder([room_samples.respond]), Path(args.record_samples), provenance="sample")
    if args.record:
        return RecordingTransport(LiveTransport(), Path(args.record))
    return LiveTransport()


def render(scan: RoomScan) -> str:
    lines = [f"Room scan {scan.id} '{scan.name}' {scan.image_size[0]}x{scan.image_size[1]}  "
             f"[{scan.provenance.upper()}]",
             f"Models: {scan.models.segmenter} + {scan.models.classifier or 'none'}"
             f"{'' if scan.models.classifier_ok else ' (classifier failed)'}", ""]
    lines.append("Objects:")
    for c in scan.classified:
        kind = f" {c.hazard_kind}" if c.hazard_kind else ""
        lines.append(f"  {c.segment.id:<18} {c.role}{kind}: {c.reason}")
    lines += ["", "Safe spots (best first):"]
    for i, s in enumerate(scan.spots, 1):
        where = f" at {s.point}" if s.point else (f" ({s.anchor_id})" if s.anchor_id else "")
        lines.append(f"  {i}. [{s.kind} {s.score:.2f}]{where} {s.instruction}")
        lines += [f"       - {c}" for c in s.cautions]
    if scan.exit_note:
        lines += ["", f"Way out (Muse Spark): {scan.exit_note}"]
    lines += ["", "Fixes:"]
    for f in scan.fixes:
        cost = "free" if f.cost_usd == (0, 0) else f"${f.cost_usd[0]}-{f.cost_usd[1]}"
        lines.append(f"  [ ] {f.target_label} ({f.target_id}): {f.action}  [{f.effort}, {cost}]")
    if scan.notes:
        lines += ["", "Notes:"] + [f"  {n}" for n in scan.notes]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("photo")
    parser.add_argument("--name", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixtures", metavar="DIR")
    mode.add_argument("--record-samples", metavar="DIR")
    mode.add_argument("--record", metavar="DIR")
    args = parser.parse_args(argv)

    try:
        jpeg = prepare_image(Path(args.photo).read_bytes())
    except (OSError, ValueError) as exc:
        print(f"Cannot read {args.photo}: {exc}", file=sys.stderr)
        return 2
    client = MetaClient(transport_for(args), load_settings())
    name = args.name or Path(args.photo).stem.replace("_", " ")
    print(render(scan_room(jpeg, name, client)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
