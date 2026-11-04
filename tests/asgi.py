"""Calls the Starlette app in-process. Starlette's TestClient needs httpx, which this project does not ship."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Reply:
    status: int
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


def call(app, method: str, url: str, body: bytes = b"", content_type: str = "application/octet-stream") -> Reply:
    parts = urlsplit(url)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(),
             "query_string": parts.query.encode(), "root_path": "", "server": ("test", 80), "client": ("test", 1),
             "headers": [(b"host", b"test"), (b"content-type", content_type.encode()),
                         (b"content-length", str(len(body)).encode())]}
    sent = {"done": False}
    out: dict[str, Any] = {"body": b""}

    async def receive():
        if sent["done"]:
            await asyncio.sleep(3600)
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return Reply(out["status"], out["body"])
