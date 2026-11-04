"""One go-bag photo to a GoBagCheck: one Muse Spark call over the fixed Ready.gov checklist.

The model says, per checklist id, whether the item is visible. Code keeps the
checklist's own ids, labels and order, drops anything else the model says, and
never reports the kit as complete or adequate: it reports what the photo shows.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from . import rules
from .meta import MetaClient, MetaUnavailable
from .room.classify import one_line
from .shapes import GoBagCheck, GoBagItem, Provenance
from .transport import HttpError

ITEM_IDS = [item_id for item_id, _ in rules.GO_BAG]

SYSTEM_PROMPT = """You get one photo of an open emergency go bag and a fixed checklist of item ids.
For every checklist id, say whether that item is clearly visible in the photo (seen: true) or not (seen: false).
note: a few words on what you see for that item, such as "two 1-litre bottles", or "" when it is not seen.
Report only what is visible. Never say the kit is complete, enough, adequate or ready, and never judge
whether it suits the household. Use only the listed ids."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "seen", "note"],
            "properties": {
                "id": {"type": "string", "enum": ITEM_IDS},
                "seen": {"type": "boolean"},
                "note": {"type": "string"},
            }}},
    },
}

VERDICT = re.compile(r"\b(complete|completed|enough|adequate|sufficient|ready|all set|fully stocked|everything)\b",
                     re.IGNORECASE)
"""A note with any of these words reads as a judgment of the kit, which the app never makes."""


class _WireItem(BaseModel):
    id: str
    seen: bool
    note: str


class _WireAnswer(BaseModel):
    items: list[_WireItem]


def user_prompt() -> str:
    return json.dumps({"checklist": [{"id": i, "item": label} for i, label in rules.GO_BAG]})


def parse_gobag(data: Any, model: str, provenance: Provenance) -> GoBagCheck:
    """Guard the model's answer against the checklist. Raises ValueError on a malformed answer."""
    answer = _WireAnswer.model_validate(data)
    by_id: dict[str, _WireItem] = {}
    for item in answer.items:
        by_id.setdefault(item.id, item)
    items = [_item(item_id, label, by_id.get(item_id)) for item_id, label in rules.GO_BAG]
    name, url = rules.SOURCES[rules.GO_BAG_SOURCE]
    return GoBagCheck(items=items, seen_count=sum(i.seen for i in items), total=len(items), model=model,
                      caveat=rules.GO_BAG_CAVEAT, source_name=name, source_url=url, provenance=provenance)


def _item(item_id: str, label: str, wire: _WireItem | None) -> GoBagItem:
    seen = wire is not None and wire.seen
    note = one_line(wire.note, 80) if seen and wire.note.strip() else None
    if note and VERDICT.search(note):
        note = None
    return GoBagItem(id=item_id, label=label, seen=seen,
                     status=rules.GO_BAG_SEEN if seen else rules.GO_BAG_NOT_SEEN, note=note)


def check_gobag(jpeg: bytes, client: MetaClient) -> GoBagCheck:
    """Raises MetaUnavailable when Muse Spark did not give a usable answer."""
    try:
        data, provenance = client.vision_json(jpeg, SYSTEM_PROMPT, user_prompt(), "go_bag_check", SCHEMA)
        return parse_gobag(data, client.settings.vision_model, provenance)
    except (HttpError, ValueError, ValidationError, KeyError, IndexError, TypeError) as exc:
        raise MetaUnavailable(f"go-bag check failed: {type(exc).__name__}: {str(exc)[:300]}") from exc
