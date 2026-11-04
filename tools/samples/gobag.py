"""Hand-authored SAMPLE answer from Muse Spark for the go-bag check. Not a real photo; the app labels it sample.

Record a real one with `python tools/record_fixtures.py --gobag <photo>`.
"""
from __future__ import annotations

import json

from safezone.transport import Request, Response

from .room import chat_completion

SCHEMA_NAME = "go_bag_check"

SEEN = {
    "water": "two 1-litre water bottles",
    "flashlight": "a small flashlight",
    "first_aid": "a red first aid pouch",
    "whistle": "a whistle on a cord",
    "batteries": "a pack of AA batteries",
    "phone_power": "a charging cable and a power bank",
}
NOT_SEEN = ["food", "radio", "dust_mask", "sheeting_tape", "sanitation", "wrench", "can_opener", "maps"]

ANSWER = {"items": [{"id": i, "seen": True, "note": n} for i, n in SEEN.items()]
          + [{"id": i, "seen": False, "note": ""} for i in NOT_SEEN]}


def respond(request: Request) -> Response | None:
    if request.method != "POST" or not request.body or not request.url.endswith("/chat/completions"):
        return None
    body = json.loads(request.body)
    if body.get("response_format", {}).get("json_schema", {}).get("name") != SCHEMA_NAME:
        return None
    return Response(200, chat_completion(ANSWER), "sample")
