"""Phase 1 probe: confirm the key works and save real responses as fixtures.

Costs at most 2 paid calls (one SAM 3.1, one Muse Spark). Rerunning with the same
photo is free because responses are cached. Use --dry-run to see the requests
without sending anything.

    python scripts/probe.py path/to/room.jpg
    python scripts/probe.py path/to/room.jpg --dry-run
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safezone import config  # noqa: E402
from safezone.meta_client import MetaClient  # noqa: E402

FIXTURES = config.ROOT / "fixtures" / "probe"


def data_url(photo: Path) -> str:
    mime = mimetypes.guess_type(photo.name)[0] or "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(photo.read_bytes()).decode()


def message(text: str, image: str) -> list:
    return [{
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": image},
        ],
    }]


def requests_for(photo: Path) -> dict:
    image = data_url(photo)
    config.load_env()
    return {
        "sam": {
            "model": "sam-3.1",
            "input": message("bookshelf", image),
            "stream": False,
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        },
        "muse": {
            "model": os.environ.get("MUSE_MODEL", "muse-spark-1.3"),
            "reasoning": {"effort": "low"},
            "input": message(
                "List up to 8 objects in this room that could fall, slide, or shatter in an "
                "earthquake. Reply with JSON only: "
                '[{"object": str, "hazard": "falls"|"slides"|"shatters", "near_bed_or_seat": bool}]',
                image,
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photo", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    requests = requests_for(args.photo)
    if args.dry_run:
        for name, body in requests.items():
            shown = json.dumps(body)
            print(name, shown[:300] + ("..." if len(shown) > 300 else ""))
        return

    client = MetaClient()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, body in requests.items():
        try:
            response = client.post("/responses", body)
        except Exception as error:
            print(f"{name}: FAILED {error}")
            continue
        (FIXTURES / f"{name}.json").write_text(json.dumps(response, indent=2))
        print(f"{name}: ok, saved fixtures/probe/{name}.json")
    print(f"paid calls used so far: {client.calls_used()} of {client.max_calls}")


if __name__ == "__main__":
    main()
