"""Pure scoring: ranked safe spots, the open-floor guard and the fix list. Distances are image pixels."""
from __future__ import annotations

import math

from ..rules import DURING_SPECIAL, FIX_TABLE, HAZARD_LABELS
from ..shapes import BBox, Classified, Fix, ImagePoint, SafeSpot
from .classify import FloorProposal

EFFORT_ORDER = {"minutes": 0, "hour": 1, "pro": 2}
KIND_ORDER = {kind: i for i, kind in enumerate(FIX_TABLE)}
UNDER_KINDS = {"heavy_up_high", "overhead_fixture", "hanging_object"}
OPEN_FLOOR_FACTOR = 0.6
"""Open floor is never as good as sturdy cover."""
TALL_LABELS = {"wardrobe", "bookshelf", "cabinet"}
GLASS_LABELS = {"window", "glass door", "mirror"}
FLOOR_TOP = 0.45
"""A floor spot higher than this fraction of the image is on a wall or the ceiling, not the floor."""


def box_gap(a: BBox, b: BBox) -> float:
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


def point_gap(p: ImagePoint, b: BBox) -> float:
    return box_gap((p[0], p[1], p[0], p[1]), b)


def _diag(image_size: tuple[int, int]) -> float:
    return math.hypot(*image_size)


def tip_zone(box: BBox) -> BBox:
    """Image-space heuristic: furniture can land up to its height to either side and half its height toward the camera."""
    l, t, r, b = box
    h = b - t
    return (l - h, t, r + h, b + h / 2)


def _inside(p: ImagePoint, box: BBox) -> bool:
    return box[0] <= p[0] < box[2] and box[1] <= p[1] < box[3]


def hazard_name(c: Classified) -> str:
    """SAM's "door" phrase also hits wardrobe and cabinet doors; named "door" they read as the room's exit."""
    return "cabinet door" if c.hazard_kind == "cabinet_doors" and c.segment.label == "door" else c.segment.label


def hazard_caution(c: Classified) -> str | None:
    # A bed under a window is fixed by moving the bed; "stay clear of the bed" would contradict in-bed guidance.
    if c.hazard_kind is None or c.hazard_kind == "bed_under_window":
        return None
    return f"{HAZARD_LABELS[c.hazard_kind]}. Stay clear of the {hazard_name(c)}."


def floor_rejection(floor: FloorProposal, classified: list[Classified], image_size: tuple[int, int]) -> str | None:
    """Why the model's open-floor spot is unsafe, or None if it passes every guard."""
    w, h = image_size
    p = floor.point
    if not (0 <= p[0] < w and 0 <= p[1] < h):
        return "it is outside the photo"
    for c in classified:
        if c.segment.label.lower() != "door":
            continue
        l, t, r, b = c.segment.bbox
        mx, my = 0.1 * (r - l), 0.1 * (b - t)
        if _inside(p, (l - mx, t - my, r + mx, b + my)):
            return "it is in a doorway"
    for c in classified:
        if c.segment.label.lower() != "door" and _inside(p, c.segment.bbox):
            return f"it is on or inside the {c.segment.label}"
    if p[1] < FLOOR_TOP * h:
        return "it is not on the floor"
    # These guards go by what the object is, not by the model's role for it, so a hazard the model
    # called neutral still blocks the spot.
    for c in classified:
        if _is_tall(c) and _inside(p, tip_zone(c.segment.bbox)):
            return f"it is where the {c.segment.label} could land if it tips"
    for c in classified:
        l, _, r, b = c.segment.bbox
        if _is_up_high(c) and l <= p[0] < r and p[1] >= b:
            return f"it is below the {c.segment.label}"
    for c in classified:
        if _is_glass(c) and point_gap(p, c.segment.bbox) < 0.1 * _diag(image_size):
            return f"it is close to glass ({c.segment.label})"
    return None


def _is_tall(c: Classified) -> bool:
    return c.hazard_kind == "tall_furniture" or c.segment.label.lower() in TALL_LABELS


def _is_glass(c: Classified) -> bool:
    return c.hazard_kind == "glass" or c.segment.label.lower() in GLASS_LABELS


def _is_up_high(c: Classified) -> bool:
    if c.hazard_kind in UNDER_KINDS:
        return True
    label = c.segment.label.lower()
    return not c.segment.touches_floor and label not in GLASS_LABELS | {"door", "ceiling light"}


def _touches_glass(cover: Classified, classified: list[Classified], image_size: tuple[int, int]) -> bool:
    """The rule set says cover is away from windows; a table within 5% of the diagonal of glass is not cover."""
    limit = 0.05 * _diag(image_size)
    return any(_is_glass(c) and box_gap(cover.segment.bbox, c.segment.bbox) < limit for c in classified)


def _cover_spot(cover: Classified, hazards: list[Classified], image_size: tuple[int, int]) -> SafeSpot:
    diag = _diag(image_size)
    box = cover.segment.bbox
    gaps = [(box_gap(box, h.segment.bbox), h) for h in hazards]
    nearest = min((g for g, _ in gaps), default=None)
    score = 1.0 if nearest is None else min(1.0, nearest / (0.25 * diag))
    costly: list[Classified] = []
    for gap, h in gaps:
        hb = h.segment.bbox
        if h.hazard_kind == "glass" and gap < 0.1 * diag:
            score *= 0.5
            costly.append(h)
        elif h.hazard_kind in ("overhead_fixture", "hanging_object") and hb[0] < box[2] and box[0] < hb[2]:
            score *= 0.7
            costly.append(h)
        elif h.hazard_kind == "tall_furniture":
            dx = max(0.0, box[0] - hb[2], hb[0] - box[2])
            if dx < hb[3] - hb[1]:
                score *= 0.6
                costly.append(h)
    return SafeSpot(kind="cover", anchor_id=cover.segment.id, point=None, nearest_hazard_px=nearest,
                    score=round(score, 2), instruction=f"Get under the {cover.segment.label}. Hold on to a leg.",
                    cautions=_unique(hazard_caution(h) for h in costly))


def _floor_spot(floor: FloorProposal, hazards: list[Classified], image_size: tuple[int, int]) -> SafeSpot:
    reach = 0.25 * _diag(image_size)
    gaps = [(point_gap(floor.point, h.segment.bbox), h) for h in hazards]
    nearest = min((g for g, _ in gaps), default=None)
    proximity = 1.0 if nearest is None else min(1.0, nearest / reach)
    point = (round(floor.point[0], 1), round(floor.point[1], 1))
    # The instruction read during shaking is fixed text; the model's words appear only as attributed context.
    return SafeSpot(kind="open_floor", anchor_id=None, point=point, nearest_hazard_px=nearest,
                    score=round(proximity * OPEN_FLOOR_FACTOR, 2),
                    instruction="Drop on the open floor at the marked spot. Cover your head and neck with your arms.",
                    cautions=_unique([f"Muse Spark: {floor.description.rstrip('. ')}. {floor.reason.rstrip('. ')}.",
                                      *(hazard_caution(h) for g, h in sorted(gaps, key=lambda x: x[0]) if g < reach)]))


def rank_spots(classified: list[Classified], floor: FloorProposal | None,
               image_size: tuple[int, int]) -> tuple[list[SafeSpot], list[str]]:
    """Cover first (best score first), then a guarded open-floor spot, else one no_cover spot."""
    hazards = [c for c in classified if c.role == "hazard"]
    notes: list[str] = []
    set_aside: list[str] = []
    covers = [c for c in classified if c.role == "cover"]
    against_glass = [c for c in covers if _touches_glass(c, classified, image_size)]
    set_aside.extend(f"The {c.segment.label} is next to glass, so SafeZone does not use it as cover."
                     for c in against_glass)
    spots = sorted((_cover_spot(c, hazards, image_size) for c in covers if c not in against_glass),
                   key=lambda s: -s.score)
    if floor is not None:
        why = floor_rejection(floor, classified, image_size)
        if why:
            set_aside.append(f"Muse Spark suggested a spot on the floor. SafeZone set it aside: {why}.")
        else:
            spots.append(_floor_spot(floor, hazards, image_size))
    if not spots:
        spots.append(SafeSpot(kind="no_cover", anchor_id=None, point=None, nearest_hazard_px=None, score=0,
                              instruction=DURING_SPECIAL["no_cover"],
                              cautions=_unique(hazard_caution(h) for h in hazards)))

    first = spots[0]
    has_bed = any(c.segment.label.lower() == "bed" for c in classified)
    extra: list[str] = []
    if has_bed:
        extra.append(DURING_SPECIAL["in_bed"])
    extra.append(DURING_SPECIAL["doorway"])
    spots[0] = first.model_copy(update={"cautions": _unique([*set_aside, *first.cautions, *extra])})
    return spots, notes


def fixes_for(classified: list[Classified]) -> list[Fix]:
    fixes = []
    for c in classified:
        if c.hazard_kind is None:
            continue
        action, effort, cost = FIX_TABLE[c.hazard_kind]
        fixes.append(Fix(id=f"fix-{c.segment.id}", target_id=c.segment.id, target_label=hazard_name(c),
                         hazard_kind=c.hazard_kind, action=action, effort=effort, cost_usd=cost))
    return sorted(fixes, key=lambda f: (EFFORT_ORDER[f.effort], KIND_ORDER[f.hazard_kind]))


def _unique(items) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item:
            seen.setdefault(item, None)
    return list(seen)
