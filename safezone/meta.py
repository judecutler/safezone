"""Meta Model API client: SAM 3.1 segmentation and Muse Spark vision, on one key.

SAM 3.1 runs on the Responses endpoint with one noun phrase per request and
streams its answer as text in the SAM wire grammar (parsed in room/segment.py).
Muse Spark runs on the OpenAI-compatible chat completions endpoint with a JSON
schema response format.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .shapes import Provenance
from .transport import Transport, get_json, post_json, post_raw


class MetaUnavailable(RuntimeError):
    """No API key, or the API did not answer. Callers degrade instead of failing the scan."""


@dataclass(frozen=True)
class MetaClient:
    transport: Transport
    settings: Settings

    def _headers(self) -> dict[str, str]:
        if not self.settings.meta_api_key:
            return {}
        return {"Authorization": f"Bearer {self.settings.meta_api_key}"}

    def list_models(self) -> list[str]:
        data, _ = get_json(self.transport, f"{self.settings.meta_api_base}/models", headers=self._headers())
        return sorted(m["id"] for m in data.get("data", []))

    def segment(self, jpeg: bytes, phrase: str) -> tuple[str, Provenance]:
        """Raw SAM 3.1 output text for one concept phrase. Empty text means no match."""
        body = {
            "model": self.settings.segment_model,
            "stream": True,
            "metadata": {"include_confidence": "true"},
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": phrase},
                    {"type": "input_image", "image_url": data_url(jpeg)},
                ],
            }],
        }
        headers = {**self._headers(), "Accept": "text/event-stream"}
        resp = post_raw(self.transport, f"{self.settings.meta_api_base}/responses", body, headers, timeout_s=90)
        return responses_output_text(resp.text), resp.provenance

    def vision_json(self, jpeg: bytes, system: str, user: str, schema_name: str,
                    schema: dict[str, Any], effort: str = "low") -> tuple[Any, Provenance]:
        """One Muse Spark call with an image, constrained to `schema`. Returns the parsed JSON."""
        body = {
            "model": self.settings.vision_model,
            "reasoning_effort": effort,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": data_url(jpeg)}},
                ]},
            ],
        }
        data, provenance = post_json(self.transport, f"{self.settings.meta_api_base}/chat/completions",
                                     body, self._headers(), timeout_s=180)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content), provenance


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def responses_output_text(sse: str) -> str:
    """Collect output text from a Responses API event stream (or a plain JSON response)."""
    stripped = sse.lstrip()
    if stripped.startswith("{"):
        return _completed_text(json.loads(stripped))
    deltas: list[str] = []
    completed: str | None = None
    for line in sse.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        event = json.loads(payload)
        kind = event.get("type")
        if kind == "response.output_text.delta":
            deltas.append(event.get("delta", ""))
        elif kind == "response.completed":
            completed = _completed_text(event.get("response", {}))
        elif kind in ("response.failed", "error"):
            raise MetaUnavailable(f"SAM stream failed: {payload[:200]}")
    return "".join(deltas) if deltas else (completed or "")


def _completed_text(response: dict[str, Any]) -> str:
    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)
