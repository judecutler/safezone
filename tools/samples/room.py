"""Hand-authored SAMPLE answers from SAM 3.1 and Muse Spark for the demo photo only.

Boxes were drawn by looking at demo/living_room.jpg (1600x900). SAM records are
box-only because masks cannot be authored by hand. The Muse answer is what a
careful model should say under rules.CLASSIFIER_RULES: no table or desk, so no
cover. Record real responses with a key to replace these.
"""
from __future__ import annotations

import json

from safezone.config import ROOT
from safezone.meta import data_url
from safezone.transport import Request, Response

DEMO_IMAGE = ROOT / "demo" / "living_room.jpg"
W, H = 1600, 900


def _box(obj_id: int, l: int, t: int, r: int, b: int, c: float) -> str:
    # The wire grammar's x2/y2 are inclusive.
    return f"{obj_id}<|box;x1={l};y1={t};x2={r - 1};y2={b - 1};w={W};h={H};c={c}|>"


LEFT_WARDROBE = (164, 188, 668, 812)
MIDDLE_WARDROBE = (708, 252, 868, 788)

SAM: dict[str, list[str]] = {
    "bookshelf": [_box(0, 1136, 238, 1378, 548, 0.84)],
    "cabinet": [
        _box(0, 168, 192, 664, 806, 0.71),
        _box(2, 710, 256, 866, 786, 0.68),
        _box(5, 576, 140, 854, 256, 0.63),
    ],
    "wardrobe": [_box(1, *LEFT_WARDROBE, 0.91), _box(3, *MIDDLE_WARDROBE, 0.89)],
    "ceiling light": [_box(0, 774, 4, 804, 44, 0.77)],
    "bed": [_box(0, 0, 552, 544, 900, 0.93), _box(1, 1040, 512, 1600, 900, 0.92)],
    "box": [
        _box(0, 1220, 130, 1356, 310, 0.9),
        _box(1, 1182, 164, 1224, 308, 0.72),
        _box(4, 194, 166, 270, 216, 0.55),
    ],
    "door": [_box(0, 884, 232, 1108, 744, 0.88)],
}

# Ids after dedupe: bookshelf-0, cabinet-0 (the open hutch above the wardrobes), wardrobe-0 (left, open),
# wardrobe-1 (middle, closed), ceiling-light-0, bed-0 (left), bed-1 (right), box-0, box-1, box-2 (basket), door-0.
SEGMENTS = [
    ("bookshelf-0", "hazard", "tall_furniture", "Tall wire shelf with cartons on top; no wall anchor is visible."),
    ("cabinet-0", "hazard", "heavy_up_high", "Open shelf above the wardrobes holds bottles and bags."),
    ("wardrobe-0", "hazard", "tall_furniture", "Tall wooden wardrobe, door open, no wall anchor visible."),
    ("wardrobe-1", "hazard", "tall_furniture", "Tall wooden wardrobe next to the door, no wall anchor visible."),
    ("ceiling-light-0", "hazard", "overhead_fixture", "Ceiling light fixture with a wire cage."),
    ("bed-0", "neutral", None, "A bed is not cover."),
    ("bed-1", "neutral", None, "A bed is not cover."),
    ("box-0", "hazard", "heavy_up_high", "Large carton stored on top of the wire shelf."),
    ("box-1", "hazard", "heavy_up_high", "Carton stored on top of the wire shelf."),
    ("box-2", "hazard", "heavy_up_high", "Basket with bottles on top of the left wardrobe."),
    ("door-0", "neutral", None, "The room's door; not a safe spot."),
]

RELATIONS = [
    ("in_tip_zone", "bed-0", "wardrobe-0", "The left bed is right in front of the open wardrobe; if it tips it lands on the bed."),
    ("in_tip_zone", "bed-1", "bookshelf-0", "The wire shelf stands at the head of the right bed and could fall onto it."),
    ("under_stored_items", "bed-1", "box-0", "The cartons on top of the wire shelf are above the head of the right bed."),
    ("blocks_exit", "door-0", "wardrobe-1", "The wardrobe beside the door could fall across the way out."),
]

ANSWER = {
    "segments": [{"id": i, "role": r, "hazard_kind": k, "reason": why} for i, r, k, why in SEGMENTS],
    "relations": [{"kind": k, "subject_id": s, "hazard_id": h, "note": n} for k, s, h, n in RELATIONS],
    # The only clear floor is the carpet between the beds. The code's tipping-zone guard rejects it,
    # which is the honest outcome for this room.
    "best_spot": {"x": 0.45, "y": 0.96, "description": "the open carpet between the two beds",
                  "reason": "Clear floor away from windows with nothing stored above it."},
    "exit_note": "The way to the door runs between the beds, past the middle wardrobe and the wire shelf; either could fall across it.",
}


def sam_stream(text: str) -> str:
    events = [{"type": "response.created", "response": {"status": "in_progress"}}]
    half = len(text) // 2
    events += [{"type": "response.output_text.delta", "delta": part} for part in (text[:half], text[half:]) if part]
    events.append({"type": "response.completed", "response": {
        "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}})
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def chat_completion(content: dict) -> str:
    return json.dumps({
        "id": "chatcmpl-sample", "object": "chat.completion", "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": json.dumps(content)}}],
    })


def respond(request: Request) -> Response | None:
    if request.method != "POST" or not request.body:
        return None
    body = json.loads(request.body)
    demo = data_url(DEMO_IMAGE.read_bytes())
    if request.url.endswith("/responses"):
        content = body["input"][0]["content"]
        phrase = next(c["text"] for c in content if c["type"] == "input_text")
        if not any(c.get("image_url") == demo for c in content):
            return None
        records = SAM.get(phrase, [])
        return Response(200, sam_stream("<0f>" + ",".join(records) if records else ""), "sample")
    if request.url.endswith("/chat/completions"):
        parts = body["messages"][-1]["content"]
        if not any(p.get("image_url", {}).get("url") == demo for p in parts):
            return None
        return Response(200, chat_completion(ANSWER), "sample")
    return None
