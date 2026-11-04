"""Find where Kamakura's mapped tsunami inundation is, so the Japan demo place sits inside it.

Reads only the Hazard Map Portal tiles (about 10 small downloads, no key). Prints a map of the coast
(digits are depth classes, '.' is no mapped inundation) and three commands for tools/record_japan.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from safezone import regions  # noqa: E402
from safezone.japan.tiles import DEPTH_CLASSES, InundationMap  # noqa: E402

LON0, LON1, LAT0, LAT1 = 139.525, 139.560, 35.298, 35.324
STEP_LON, STEP_LAT = 0.0016, 0.0012  # about 150 m
REFERENCE = (139.5420, 35.3115)  # Yuigahama-dori, near Kamakura Station's south side


def main() -> None:
    depth_map = InundationMap(regions.live_transport())
    cols = int((LON1 - LON0) / STEP_LON) + 1
    rows = int((LAT1 - LAT0) / STEP_LAT) + 1
    grid: dict[tuple[int, int], int | None] = {}
    for r in range(rows):
        for c in range(cols):
            grid[(r, c)] = depth_map.depth((LON0 + c * STEP_LON, LAT1 - r * STEP_LAT))
    print("North is up. Digits: depth class (0 shallow ... 7 deep). '.': no mapped inundation.\n")
    for r in range(rows):
        print("".join("." if grid[(r, c)] is None else str(min(grid[(r, c)], 9)) for c in range(cols)))
    print()
    for i, d in enumerate(DEPTH_CLASSES):
        print(f"  {i} = {d.en}")

    def point(r: int, c: int) -> tuple[float, float]:
        return LON0 + c * STEP_LON, LAT1 - r * STEP_LAT

    inside = [(r, c) for (r, c), d in grid.items() if d is not None and 2 <= d <= 5
              and all(grid.get((r + dr, c + dc)) is not None for dr in (-1, 0, 1) for dc in (-1, 0, 1))]
    inside.sort(key=lambda rc: (point(*rc)[0] - REFERENCE[0]) ** 2 + (point(*rc)[1] - REFERENCE[1]) ** 2)
    if not inside:
        print("\nNo interior point found. Paste this output to Claude.")
        return
    print("\nCandidates inside the mapped area (nearest the station first). Run one:")
    for r, c in inside[:3]:
        lon, lat = point(r, c)
        print(f"  python tools/record_japan.py --lon {lon:.4f} --lat {lat:.4f}    # depth {DEPTH_CLASSES[grid[(r, c)]].en}")


if __name__ == "__main__":
    main()
