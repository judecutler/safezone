"""HTTP boundary. Every outside call goes through a Transport.

`LiveTransport` talks to the network. `RecordingTransport` saves each exchange
to a fixture directory and `ReplayTransport` answers from it, so the pipelines
run end to end offline with the same code they run live. Fixture files are
keyed by a hash of the request, minus auth headers.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from .shapes import Provenance

USER_AGENT = "SafeZone/0.1 (Meta hackathon earthquake and tsunami prep; github.com/safezone-app)"


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    params: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    headers: tuple[tuple[str, str], ...] = ()
    timeout_s: float = 30.0

    def key(self) -> str:
        h = hashlib.sha256()
        h.update(self.method.encode())
        h.update(self.url.encode())
        h.update(json.dumps(sorted(self.params)).encode())
        h.update(self.body or b"")
        return h.hexdigest()[:24]

    def describe(self) -> dict[str, Any]:
        return {"method": self.method, "url": self.url, "params": dict(self.params)}


@dataclass(frozen=True)
class Response:
    status: int
    text: str
    provenance: Provenance


NETWORK_FAILURE = 599
"""Status used when no HTTP response arrived at all (DNS, timeout, no fixture)."""


class HttpError(RuntimeError):
    def __init__(self, request: Request, status: int, text: str):
        super().__init__(f"{request.method} {request.url} -> {status}: {text[:200]}")
        self.status = status


class Transport(Protocol):
    def send(self, request: Request) -> Response: ...


def get_json(transport: Transport, url: str, params: dict[str, Any] | None = None,
             headers: dict[str, str] | None = None, timeout_s: float = 30.0) -> tuple[Any, Provenance]:
    req = Request("GET", url, _pairs(params), None, _pairs(headers), timeout_s)
    resp = _ok(transport, req)
    return json.loads(resp.text), resp.provenance


def post_json(transport: Transport, url: str, body: Any, headers: dict[str, str] | None = None,
              timeout_s: float = 60.0) -> tuple[Any, Provenance]:
    resp = post_raw(transport, url, body, headers, timeout_s)
    return json.loads(resp.text), resp.provenance


def post_raw(transport: Transport, url: str, body: Any, headers: dict[str, str] | None = None,
             timeout_s: float = 60.0) -> Response:
    data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    return _ok(transport, Request("POST", url, (), data, _pairs(hdrs), timeout_s))


def _pairs(d: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, str(v)) for k, v in (d or {}).items()))


def _ok(transport: Transport, req: Request) -> Response:
    resp = transport.send(req)
    if resp.status >= 400:
        raise HttpError(req, resp.status, resp.text)
    return resp


@dataclass
class LiveTransport:
    """Real network. Spaces requests per host where the provider's usage policy asks for it."""
    min_interval_s: dict[str, float] = field(default_factory=lambda: {"nominatim.openstreetmap.org": 1.1})
    _last: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _session: requests.Session = field(default_factory=requests.Session)

    def send(self, request: Request) -> Response:
        self._pace(urlsplit(request.url).hostname or "")
        headers = {"User-Agent": USER_AGENT, **dict(request.headers)}
        try:
            r = self._session.request(request.method, request.url, params=dict(request.params) or None,
                                      data=request.body, headers=headers, timeout=request.timeout_s)
        except requests.RequestException as exc:
            return Response(NETWORK_FAILURE, str(exc), "live")
        return Response(r.status_code, r.text, "live")

    def _pace(self, host: str) -> None:
        gap = self.min_interval_s.get(host)
        if not gap:
            return
        with self._lock:
            wait = self._last.get(host, 0.0) + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()


@dataclass
class RecordingTransport:
    """Passes requests to `inner` and saves each successful exchange under `directory`."""
    inner: Transport
    directory: Path
    provenance: Provenance = "recorded"

    def send(self, request: Request) -> Response:
        resp = self.inner.send(request)
        if resp.status < 400:
            self.directory.mkdir(parents=True, exist_ok=True)
            record = {"request": request.describe(), "status": resp.status,
                      "provenance": self.provenance, "text": resp.text}
            (self.directory / f"{request.key()}.json").write_text(json.dumps(record, indent=1))
        return Response(resp.status, resp.text, self.provenance)


@dataclass
class ReplayTransport:
    """Answers from saved exchanges. An unrecorded request reads as a network failure."""
    directory: Path

    def send(self, request: Request) -> Response:
        path = self.directory / f"{request.key()}.json"
        if not path.exists():
            return Response(NETWORK_FAILURE, f"no fixture for {request.describe()}", "sample")
        record = json.loads(path.read_text())
        return Response(record["status"], record["text"], record["provenance"])
