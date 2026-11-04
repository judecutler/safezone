"""Add a demo photo for the way-out or gas-shutoff step, with location data removed.

    python tools/demo_photo.py exit "$HOME\\Downloads\\exit.jpg"
    python tools/demo_photo.py gas "$HOME\\Downloads\\gas.jpg"

Writes demo/exit.jpg or demo/gas.jpg. The photo is turned upright, resized to at most 1600 px on the long side,
and saved without any metadata, so no GPS position or camera details reach the public repo. These steps make no
model call, so nothing else needs recording. (The go-bag photo goes through `tools/record_fixtures.py --gobag`.)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("exit", "gas")
MAX_SIDE = 1600


def clean_photo(source: Path, target: Path) -> tuple[int, int]:
    with Image.open(source) as im:
        upright = ImageOps.exif_transpose(im).convert("RGB")
    upright.thumbnail((MAX_SIDE, MAX_SIDE))
    target.parent.mkdir(parents=True, exist_ok=True)
    upright.save(target, "JPEG", quality=85, optimize=True)
    return upright.size


def main(argv: list[str]) -> None:
    if len(argv) != 2 or argv[0] not in KINDS:
        raise SystemExit(f"usage: python tools/demo_photo.py {'|'.join(KINDS)} <photo.jpg>")
    source = Path(argv[1])
    if not source.is_file():
        raise SystemExit(f"no photo at {source}")
    target = ROOT / "demo" / f"{argv[0]}.jpg"
    w, h = clean_photo(source, target)
    print(f"wrote {target.relative_to(ROOT)} ({w}x{h}, no location data)")


if __name__ == "__main__":
    main(sys.argv[1:])
