"""One room photo to a RoomScan: SAM 3.1 segments, Muse Spark classifies and reasons, code scores and guards."""
from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from ..meta import MetaClient, MetaUnavailable
from ..shapes import ModelUse, RoomScan, weakest
from .classify import classify
from .score import fixes_for, rank_spots
from .segment import segment_image

MAX_SIDE = 1600
SEGMENTATION_UNAVAILABLE = "Segmentation unavailable; showing general guidance."


def prepare_image(raw: bytes) -> bytes:
    """Upright RGB JPEG, longest side at most 1600 px. Re-encoding also strips EXIF, including GPS."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"not a decodable image: {exc}") from exc
    # Re-encoding is not byte-stable across libjpeg builds, and replay fixtures are keyed on these bytes,
    # so an already clean JPEG (no EXIF to strip or apply, in size) passes through untouched.
    if img.format == "JPEG" and img.mode == "RGB" and max(img.size) <= MAX_SIDE and not img.getexif():
        return raw
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def scan_room(jpeg: bytes, name: str, client: MetaClient) -> RoomScan:
    with Image.open(io.BytesIO(jpeg)) as img:
        size = img.size
    settings = client.settings
    try:
        seg = segment_image(jpeg, size, client)
    except MetaUnavailable:
        spots, notes = rank_spots([], [], None, size)
        return RoomScan(
            id=_scan_id(jpeg), name=name, image_size=size, classified=[], spots=spots, fixes=[],
            models=ModelUse(segmenter=settings.segment_model, classifier=None, classifier_ok=False),
            notes=[SEGMENTATION_UNAVAILABLE, *notes], provenance=weakest(), relations=[], exit_note=None,
        )

    cls = classify(jpeg, seg.segments, size, client)
    spots, spot_notes = rank_spots(cls.classified, cls.relations, cls.floor, size)
    provenances = [seg.provenance] + ([cls.provenance] if cls.provenance else [])
    return RoomScan(
        id=_scan_id(jpeg), name=name, image_size=size, classified=cls.classified, spots=spots,
        fixes=fixes_for(cls.classified),
        models=ModelUse(segmenter=settings.segment_model,
                        classifier=settings.vision_model if cls.called else None,
                        classifier_ok=cls.ok),
        notes=[*seg.notes, *cls.notes, *spot_notes], provenance=weakest(*provenances),
        relations=cls.relations, exit_note=cls.exit_note,
    )


def _scan_id(jpeg: bytes) -> str:
    return hashlib.sha1(jpeg).hexdigest()[:12]
