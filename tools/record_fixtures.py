"""Record real responses for the demo household, replacing the SAMPLE fixtures.

Run on a machine with internet access and MODEL_API_KEY in .env:
    python tools/record_fixtures.py
It lists the Meta models your key can call, runs every pipeline live while
saving each exchange to fixtures/demo, then rebuilds demo/plan.json from them.
FEMA's open-shelter layer is empty on quiet days; pass --keep-sample-shelters
to keep the sample shelter data (it stays labelled SAMPLE in the app).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safezone.app import FEMA_HOST, HostSplit  # noqa: E402
from safezone.config import load_settings  # noqa: E402
from safezone.meta import MetaClient  # noqa: E402
from safezone.transport import (LiveTransport, RecordingTransport, ReplayTransport, Request,  # noqa: E402
                                Response, Transport)
from tools.demo import FIXTURES, ROOT, SampleResponder, build_plan, write_plan  # noqa: E402


@dataclass
class FailureLog:
    """Passes requests through and remembers every one that failed, so the run can say what went wrong."""
    inner: Transport
    failures: list[str] = field(default_factory=list)

    def send(self, request: Request) -> Response:
        started = time.monotonic()
        resp = self.inner.send(request)
        if resp.status >= 400:
            took = time.monotonic() - started
            self.failures.append(f"{resp.status} after {took:.0f}s  {request.method} {request.url}\n      {resp.text[:300]!r}")
        return resp


@dataclass
class SampleWhenDown:
    """FEMA's open-shelter layer is often empty or unreachable; fall back to labelled SAMPLE shelters."""
    live: Transport
    sample: Transport

    def send(self, request: Request) -> Response:
        resp = self.live.send(request)
        if resp.status >= 400:
            print("FEMA shelter layer failed; using SAMPLE shelters (labelled in the app).")
            return self.sample.send(request)
        return resp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-sample-shelters", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.meta_api_key:
        raise SystemExit("MODEL_API_KEY is not set (put it in .env)")
    log = FailureLog(LiveTransport())
    live = log
    models = MetaClient(live, settings).list_models()
    (ROOT / "fixtures").mkdir(exist_ok=True)
    (ROOT / "fixtures" / "models.json").write_text(json.dumps(models, indent=1))
    print("models your key can call:", ", ".join(models))
    for wanted in (settings.vision_model, settings.segment_model):
        if wanted not in models:
            raise SystemExit(f"{wanted} is not in your model list; set META_VISION_MODEL / META_SEGMENT_MODEL in .env")

    staging = ROOT / "fixtures" / "demo.recording"
    if staging.exists():
        shutil.rmtree(staging)
    recorder = RecordingTransport(live, staging, provenance="recorded")
    sample_shelters = RecordingTransport(SampleResponder(), staging, "sample")
    fema = sample_shelters if args.keep_sample_shelters else SampleWhenDown(recorder, sample_shelters)
    transport = HostSplit(FEMA_HOST, fema, recorder)
    try:
        payload = build_plan(transport, shelter_replay=True, now=datetime.now(timezone.utc))
    finally:
        print(f"\n{len(log.failures)} failed calls" + (":" if log.failures else "."))
        for line in log.failures:
            print("  " + line)
    notes = payload["plan"]["rooms"][0]["notes"]
    if notes:
        print("room notes:", *notes, sep="\n  ")
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    staging.rename(FIXTURES)
    write_plan(build_plan(ReplayTransport(FIXTURES), True, datetime.now(timezone.utc)))


if __name__ == "__main__":
    main()
