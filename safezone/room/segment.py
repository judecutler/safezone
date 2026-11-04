"""SAM 3.1 boundary: one concept phrase per request, wire grammar parsed into Segments."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..meta import MetaClient, MetaUnavailable
from ..shapes import BBox, ImagePoint, Provenance, Segment, weakest
from ..transport import HttpError

PHRASES = [
    "table", "desk", "bookshelf", "cabinet", "wardrobe", "window", "glass door", "mirror",
    "ceiling light", "TV", "bed", "box", "door",
]

FLOOR_LINE = 0.62
"""Heuristic: a box whose bottom edge sits in the lower 38% of a level, eye-height photo reaches the floor."""

DEDUPE_IOU = 0.7
MASKS_NOT_DECODED = "Masks not decoded (install meta-sam-parser); showing boxes."


@dataclass(frozen=True)
class SamMask:
    encoding: str
    payload: str
    """Exactly as received, encoding marker included."""
    width: int
    height: int
    x: int
    y: int


@dataclass(frozen=True)
class SamRecord:
    obj_id: int
    box: BBox
    """Half-open, in the pixels of the image the model saw."""
    seen_size: tuple[int, int] | None
    confidence: float | None
    mask: SamMask | None


@dataclass(frozen=True)
class Segmentation:
    segments: list[Segment]
    notes: list[str]
    provenance: Provenance


_FRAME = re.compile(r"<(\d+)f>")
_RECORD = re.compile(r"\s*,?\s*(\d+)((?:<\|[^|]*\|>)+)")
_TOKEN = re.compile(r"<\|([^|]*)\|>")


def parse_sam_output(text: str) -> list[SamRecord]:
    """Parse SAM wire grammar. Records are keyed by object id; a later record for an id replaces it."""
    by_id: dict[int, SamRecord] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        frame = _FRAME.match(line)
        if not frame:
            raise ValueError(f"SAM line without a frame marker: {line[:60]!r}")
        pos = frame.end()
        while pos < len(line):
            m = _RECORD.match(line, pos)
            if not m:
                if line[pos:].strip(" ,"):
                    raise ValueError(f"unparseable SAM record at {line[pos:pos + 60]!r}")
                break
            record = _record(int(m.group(1)), m.group(2))
            if record:
                by_id[record.obj_id] = record
            pos = m.end()
    return list(by_id.values())


def _record(obj_id: int, tokens: str) -> SamRecord | None:
    box: dict[str, str] | None = None
    mask: dict[str, str] | None = None
    for body in _TOKEN.findall(tokens):
        kind, _, rest = body.partition(";")
        if kind == "box":
            box = _fields(rest)
        elif kind == "mask":
            mask = _fields(rest)
    if box is None:
        return None
    seen = (int(box["w"]), int(box["h"])) if "w" in box and "h" in box else None
    bbox = (float(box["x1"]), float(box["y1"]), float(box["x2"]) + 1, float(box["y2"]) + 1)
    confidence = float(box["c"]) if "c" in box else None
    return SamRecord(obj_id, bbox, seen, confidence, _mask(mask) if mask else None)


def _fields(rest: str) -> dict[str, str]:
    # The base85 mask payload may contain ';' and '=', so `data=` is split off before the rest.
    head, sep, data = rest.partition("data=")
    out = dict(part.split("=", 1) for part in head.split(";") if "=" in part)
    if sep:
        out["data"] = data
    return out


def _mask(fields: dict[str, str]) -> SamMask | None:
    parts = fields.get("data", "").split(",", 2)
    if len(parts) != 3:
        return None
    height, width, payload = parts
    encoding = {"~": "lossless", "!": "one_bit"}.get(payload[:1])
    if encoding is None:
        return None
    return SamMask(encoding, payload, int(width), int(height), int(fields.get("x", 0)), int(fields.get("y", 0)))


def segment_image(jpeg: bytes, image_size: tuple[int, int], client: MetaClient) -> Segmentation:
    """Run every phrase in parallel. Raises MetaUnavailable only when no phrase got an answer."""
    def run(phrase: str):
        try:
            text, provenance = client.segment(jpeg, phrase)
            return phrase, parse_sam_output(text), provenance
        except (HttpError, MetaUnavailable, ValueError, KeyError):
            return phrase, None, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, PHRASES))

    answered = [(p, recs, prov) for p, recs, prov in results if recs is not None]
    if not answered:
        raise MetaUnavailable("every SAM 3.1 request failed")
    notes = []
    failed = [p for p, recs, _ in results if recs is None]
    if failed:
        notes.append(f"Could not segment: {', '.join(failed)}.")
    segments, decoded_all = build_segments([(p, recs) for p, recs, _ in answered], image_size)
    if not decoded_all:
        notes.append(MASKS_NOT_DECODED)
    return Segmentation(segments, notes, weakest(*(prov for _, _, prov in answered)))


def build_segments(per_phrase: list[tuple[str, list[SamRecord]]],
                   image_size: tuple[int, int]) -> tuple[list[Segment], bool]:
    """Dedupe across phrases, then number ids per label. Returns (segments, every mask decoded)."""
    candidates = [(i, j, phrase, rec) for i, (phrase, recs) in enumerate(per_phrase) for j, rec in enumerate(recs)]
    kept = _dedupe(candidates, image_size)
    kept.sort(key=lambda c: (c[0], c[1]))

    counts: dict[str, int] = {}
    segments = []
    decoded_all = True
    for _, _, phrase, rec in kept:
        slug = re.sub(r"[^a-z0-9]+", "-", phrase.lower()).strip("-")
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        seg, decoded = _segment(f"{slug}-{n}", phrase, rec, image_size)
        decoded_all &= decoded
        segments.append(seg)
    return segments, decoded_all


def _dedupe(candidates, image_size):
    ranked = sorted(candidates, key=lambda c: -1.0 if c[3].confidence is None else c[3].confidence, reverse=True)
    kept = []
    for cand in ranked:
        box = _scaled_box(cand[3], image_size)
        if all(iou(box, _scaled_box(k[3], image_size)) <= DEDUPE_IOU for k in kept):
            kept.append(cand)
    return kept


def _scale(rec: SamRecord, image_size: tuple[int, int]) -> tuple[float, float]:
    if rec.seen_size is None:
        return 1.0, 1.0
    return image_size[0] / rec.seen_size[0], image_size[1] / rec.seen_size[1]


def _scaled_box(rec: SamRecord, image_size: tuple[int, int]) -> BBox:
    sx, sy = _scale(rec, image_size)
    w, h = image_size
    l, t, r, b = rec.box
    return (max(0.0, l * sx), max(0.0, t * sy), min(float(w), r * sx), min(float(h), b * sy))


def _segment(seg_id: str, label: str, rec: SamRecord, image_size: tuple[int, int]) -> tuple[Segment, bool]:
    w, h = image_size
    box = _scaled_box(rec, image_size)
    l, t, r, b = box
    outline, area, centroid = None, (r - l) * (b - t), ((l + r) / 2, (t + b) / 2)
    decoded = rec.mask is None
    if rec.mask is not None:
        sx, sy = _scale(rec, image_size)
        # SAM 3.1 sends the mask downscaled so its long side is at most 1024 px (a 1794 x 1567 box came back
        # as a 1024 x 894 mask in a recorded response), so mask pixels are stretched over the box. x and y are
        # taken to be offsets in mask pixels.
        kx = (rec.box[2] - rec.box[0]) / rec.mask.width
        ky = (rec.box[3] - rec.box[1]) / rec.mask.height
        mask_out = _decode_mask(rec.mask, rec.box[0] / kx + rec.mask.x, rec.box[1] / ky + rec.mask.y, kx * sx, ky * sy)
        if mask_out is not None:
            outline, area, centroid = mask_out
            decoded = True
    seg = Segment(id=seg_id, label=label, bbox=box, outline=outline, area_px=round(area, 1),
                  centroid=(round(centroid[0], 1), round(centroid[1], 1)),
                  touches_floor=b >= FLOOR_LINE * h, height_ratio=round((b - t) / h, 3),
                  confidence=rec.confidence)
    return seg, decoded


def _decode_mask(mask: SamMask, ox: float, oy: float, sx: float, sy: float
                 ) -> tuple[str, float, ImagePoint] | None:
    try:
        import numpy as np
        from meta_sam_parser import SegmentationMask, decode_mask_to_raster, decode_mask_to_svg_path
    except ImportError:
        return None
    for payload in (mask.payload, mask.payload[1:]):
        try:
            m = SegmentationMask(encoding=mask.encoding, payload=payload, width=mask.width, height=mask.height)
            raster = np.asarray(decode_mask_to_raster(m), dtype=bool)
            path = decode_mask_to_svg_path(m)
        except Exception:
            continue
        ys, xs = np.nonzero(raster)
        if len(xs) == 0:
            return None
        centroid = ((ox + float(xs.mean()) + 0.5) * sx, (oy + float(ys.mean()) + 0.5) * sy)
        return offset_path(path, ox, oy, sx, sy), float(raster.sum()) * sx * sy, centroid
    return None


_PATH_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def offset_path(path: str, ox: float, oy: float, sx: float = 1.0, sy: float = 1.0) -> str:
    """Move an SVG path from mask pixels into image pixels: (x, y) -> ((ox + x) * sx, (oy + y) * sy)."""
    out: list[str] = []
    cmd, idx, commands = "", 0, 0
    for tok in _PATH_TOKEN.findall(path):
        if tok.isalpha():
            cmd, idx = tok, 0
            commands += 1
            out.append(tok)
            continue
        upper = cmd.upper()
        # The first pair of a path-opening relative moveto is absolute per the SVG spec.
        absolute = cmd.isupper() or (cmd == "m" and commands == 1 and idx < 2)
        if upper == "H":
            axis = "x"
        elif upper == "V":
            axis = "y"
        elif upper == "A":
            axis = {5: "x", 6: "y"}.get(idx % 7, "")
        else:
            axis = "x" if idx % 2 == 0 else "y"
        v = float(tok)
        if axis == "x":
            v = ((ox + v) if absolute else v) * sx
        elif axis == "y":
            v = ((oy + v) if absolute else v) * sy
        out.append(f"{v:g}")
        idx += 1
    return " ".join(out)


def iou(a: BBox, b: BBox) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
