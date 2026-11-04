"""Muse Spark boundary: one vision call labels each segment and reasons about the room.

The model proposes roles, relations, a floor spot and an exit note. Code drops
anything that names unknown segments or breaks a safety rule.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, get_args

from pydantic import BaseModel, ValidationError

from ..meta import MetaClient, MetaUnavailable
from ..rules import CLASSIFIER_RULES
from ..shapes import Classified, HazardKind, ImagePoint, Provenance, Relation, RelationKind, Segment
from ..transport import HttpError

HAZARD_KINDS: tuple[str, ...] = get_args(HazardKind)
RELATION_KINDS: tuple[str, ...] = get_args(RelationKind)
COVER_LABELS = {"table", "desk"}
GLASS_LABELS = {"window", "glass door", "mirror"}
CLASSIFIER_UNAVAILABLE = "Hazard classification unavailable; showing general guidance."

RELATION_HAZARDS: dict[str, set[str]] = {
    "in_tip_zone": {"tall_furniture"},
    "under_stored_items": {"heavy_up_high", "overhead_fixture", "hanging_object"},
    "near_glass": {"glass"},
    "blocks_exit": set(HAZARD_KINDS),
}

SYSTEM_PROMPT = CLASSIFIER_RULES + """

You get one room photo and a list of segments found in it by an object segmenter, each with an id,
a label and a normalized box (left, top, right, bottom; 0..1 of the image).
1. segments: for every listed id, a role. cover only for a sturdy table or desk clear of windows and
   hanging objects. hazard with exactly one hazard_kind. Otherwise neutral. hazard_kind is null unless
   role is hazard. reason: one short line about what is visible.
2. relations: spatial relations you can see between a segment at risk (subject_id) and a hazard
   (hazard_id), one short line each. in_tip_zone: within reach of tall furniture if it tips.
   under_stored_items: below heavy items, fixtures or hanging objects. near_glass: next to glass.
   blocks_exit: the hazard could block the way to the door.
3. best_spot: if there is no sturdy table, a point on open floor (x, y normalized 0..1) where a person
   should drop, cover and hold on: by an interior wall, away from windows, out of every tall object's
   tipping zone, not under anything stored up high, not in a doorway, never inside or behind
   furniture. description says where it is; reason says why. null if no such floor is visible.
4. exit_note: one line on what could block the way to the door, or null.
Use only the listed ids. Do not invent objects."""

_NULLABLE_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["segments", "relations", "best_spot", "exit_note"],
    "properties": {
        "segments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "role", "hazard_kind", "reason"],
            "properties": {
                "id": {"type": "string"},
                "role": {"type": "string", "enum": ["cover", "hazard", "neutral"]},
                "hazard_kind": {"anyOf": [{"type": "string", "enum": list(HAZARD_KINDS)}, {"type": "null"}]},
                "reason": {"type": "string"},
            }}},
        "relations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "subject_id", "hazard_id", "note"],
            "properties": {
                "kind": {"type": "string", "enum": list(RELATION_KINDS)},
                "subject_id": {"type": "string"},
                "hazard_id": {"type": "string"},
                "note": {"type": "string"},
            }}},
        "best_spot": {"anyOf": [{
            "type": "object", "additionalProperties": False,
            "required": ["x", "y", "description", "reason"],
            "properties": {"x": {"type": "number"}, "y": {"type": "number"},
                           "description": {"type": "string"}, "reason": {"type": "string"}},
        }, {"type": "null"}]},
        "exit_note": _NULLABLE_STR,
    },
}


class _WireSegment(BaseModel):
    id: str
    role: str
    hazard_kind: str | None
    reason: str


class _WireRelation(BaseModel):
    kind: str
    subject_id: str
    hazard_id: str
    note: str


class _WireSpot(BaseModel):
    x: float
    y: float
    description: str
    reason: str


class _WireAnswer(BaseModel):
    segments: list[_WireSegment]
    relations: list[_WireRelation] = []
    best_spot: _WireSpot | None = None
    exit_note: str | None = None


@dataclass(frozen=True)
class FloorProposal:
    point: ImagePoint
    """Image pixels; may lie outside the frame if the model said so."""
    description: str
    reason: str


@dataclass(frozen=True)
class Classification:
    classified: list[Classified]
    relations: list[Relation]
    floor: FloorProposal | None
    exit_note: str | None
    called: bool
    ok: bool
    provenance: Provenance | None
    notes: list[str]


def one_line(text: str, limit: int = 140) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


def user_prompt(segments: list[Segment], image_size: tuple[int, int]) -> str:
    w, h = image_size
    items = [{
        "id": s.id, "label": s.label,
        "bbox_norm": [round(s.bbox[0] / w, 3), round(s.bbox[1] / h, 3), round(s.bbox[2] / w, 3), round(s.bbox[3] / h, 3)],
        "height_ratio": s.height_ratio, "touches_floor": s.touches_floor,
    } for s in segments]
    return json.dumps({"image": {"width": w, "height": h}, "segments": items})


def parse_classification(data: Any, segments: list[Segment], image_size: tuple[int, int]
                         ) -> tuple[list[Classified], list[Relation], FloorProposal | None, str | None]:
    """Parse the model's answer against the SAM segment list. Raises ValueError on a malformed answer."""
    answer = _WireAnswer.model_validate(data)
    by_id: dict[str, _WireSegment] = {}
    for item in answer.segments:
        by_id.setdefault(item.id, item)
    classified = [_classify_one(seg, by_id.get(seg.id)) for seg in segments]

    kinds = {c.segment.id: c.hazard_kind for c in classified}
    relations = []
    for r in answer.relations:
        hazard_kind = kinds.get(r.hazard_id)
        if r.subject_id not in kinds or r.subject_id == r.hazard_id or hazard_kind is None:
            continue
        if hazard_kind not in RELATION_HAZARDS.get(r.kind, set()):
            continue
        relations.append(Relation(kind=r.kind, subject_id=r.subject_id, hazard_id=r.hazard_id, note=one_line(r.note)))

    floor = None
    if answer.best_spot is not None:
        s = answer.best_spot
        w, h = image_size
        floor = FloorProposal((s.x * w, s.y * h), one_line(s.description), one_line(s.reason))
    exit_note = one_line(answer.exit_note, 200) if answer.exit_note and answer.exit_note.strip() else None
    return classified, relations, floor, exit_note


def _classify_one(seg: Segment, item: _WireSegment | None) -> Classified:
    def neutral(reason: str) -> Classified:
        return Classified(segment=seg, role="neutral", hazard_kind=None, reason=reason)

    if item is None:
        return neutral("Not classified.")
    reason = one_line(item.reason)
    if item.role == "hazard":
        if item.hazard_kind not in HAZARD_KINDS:
            return neutral(f"Marked a hazard without a known kind. {reason}")
        return Classified(segment=seg, role="hazard", hazard_kind=item.hazard_kind, reason=reason)
    if item.hazard_kind is not None:
        return neutral(f"Hazard kind given without the hazard role. {reason}")
    if item.role == "cover":
        label = seg.label.lower()
        if label in GLASS_LABELS:
            return neutral("Glass is never cover.")
        if label not in COVER_LABELS:
            return neutral("Only a sturdy table or desk counts as cover.")
        return Classified(segment=seg, role="cover", hazard_kind=None, reason=reason)
    if item.role == "neutral":
        return neutral(reason)
    return neutral("Not classified.")


def classify(jpeg: bytes, segments: list[Segment], image_size: tuple[int, int], client: MetaClient) -> Classification:
    if not segments:
        return Classification([], [], None, None, called=False, ok=True, provenance=None, notes=[])
    user = user_prompt(segments, image_size)
    for _ in range(2):
        try:
            data, provenance = client.vision_json(jpeg, SYSTEM_PROMPT, user, "room_classification", SCHEMA)
            classified, relations, floor, exit_note = parse_classification(data, segments, image_size)
        except (HttpError, MetaUnavailable, ValueError, ValidationError, KeyError, IndexError, TypeError):
            continue
        return Classification(classified, relations, floor, exit_note, True, True, provenance, [])
    fallback = [Classified(segment=s, role="neutral", hazard_kind=None, reason="Not classified.") for s in segments]
    return Classification(fallback, [], None, None, called=True, ok=False, provenance=None,
                          notes=[CLASSIFIER_UNAVAILABLE])
