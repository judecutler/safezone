"""HTTP server: the PWA's static files plus a thin JSON API over the pipelines.

The server stores nothing: photos and addresses live only for the request.
Configuration comes from the environment:
- MODEL_API_KEY etc.: see config.py.
- SAFEZONE_FIXTURES=<dir>: answer outside calls from saved fixtures instead of
  the network (offline demo, tests).
- SAFEZONE_SHELTER_SNAPSHOT=<dir>: take FEMA shelter data from a saved snapshot
  and label it replay, for quiet days when no shelters are open.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.requests import Request as HttpRequest
from starlette.responses import JSONResponse, Response as HttpResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import regions
from .building.geocode import GeocodeNotFound
from .config import ROOT, Settings, load_settings
from .gobag import check_gobag
from .meta import MetaClient, MetaUnavailable
from .room.pipeline import prepare_image, scan_room
from .shapes import BuildingProfile, Household
from .transport import HttpError, ReplayTransport, Request, Response, Transport

MAX_PHOTO_BYTES = 20 * 1024 * 1024
FEMA_HOST = "gis.fema.gov"
DEMO_EXTRAS = ("exit", "gas", "gobag")
"""Optional extra demo photos, served from demo/<kind>.jpg when present."""


@dataclass(frozen=True)
class HostSplit:
    """Sends one host's requests to `special` and everything else to `default`."""
    host: str
    special: Transport
    default: Transport

    def send(self, request: Request) -> Response:
        target = self.special if urlsplit(request.url).hostname == self.host else self.default
        return target.send(request)


@dataclass(frozen=True)
class Services:
    settings: Settings
    transport: Transport
    shelter_transport: Transport
    shelter_replay: bool
    demo_plan: Path

    @property
    def demo_dir(self) -> Path:
        return self.demo_plan.parent

    @property
    def demo_plan_jp(self) -> Path:
        return self.demo_dir / "plan_jp.json"

    @classmethod
    def from_env(cls) -> Services:
        settings = load_settings()
        fixtures = os.environ.get("SAFEZONE_FIXTURES")
        transport: Transport = ReplayTransport(Path(fixtures)) if fixtures else regions.live_transport()
        snapshot = os.environ.get("SAFEZONE_SHELTER_SNAPSHOT")
        shelter_transport = HostSplit(FEMA_HOST, ReplayTransport(Path(snapshot)), transport) if snapshot else transport
        return cls(settings, transport, shelter_transport, bool(snapshot or fixtures), ROOT / "demo" / "plan.json")


class EvacRequest(BaseModel):
    building: BuildingProfile
    household: Household

    @classmethod
    def parse(cls, body: Any) -> EvacRequest:
        """/api/profile adds `region` to the profile it returns; the region is re-derived from the point here."""
        if isinstance(body, dict) and isinstance(body.get("building"), dict):
            body = {**body, "building": {k: v for k, v in body["building"].items() if k != "region"}}
        return cls.model_validate(body)


def dump(model: BaseModel | None) -> Any:
    return None if model is None else model.model_dump(mode="json")


def error(status: int, code: str, detail: str = "") -> JSONResponse:
    return JSONResponse({"error": code, "detail": detail}, status_code=status)


def create_app(services: Services | None = None) -> Starlette:
    svc = services or Services.from_env()

    async def health(_: HttpRequest) -> JSONResponse:
        return JSONResponse({"meta_key": bool(svc.settings.meta_api_key), "demo_available": svc.demo_plan.exists()})

    async def guidance(request: HttpRequest) -> JSONResponse:
        return JSONResponse(regions.guidance(request.query_params.get("region")))

    async def profile(request: HttpRequest) -> JSONResponse:
        if "lat" in request.query_params or "lon" in request.query_params:
            point = parse_point(request.query_params.get("lon", ""), request.query_params.get("lat", ""))
            if point is None:
                return error(400, "bad_location")
            lookup, args, not_found = regions.profile_for_point, point, "location_not_found"
        else:
            address = request.query_params.get("address", "").strip()
            if not address or len(address) > 300:
                return error(400, "bad_address")
            lookup, args, not_found = regions.profile_for_address, (address,), "address_not_found"
        try:
            result = await run_in_threadpool(lookup, *args, svc.transport)
        except GeocodeNotFound:
            return error(404, not_found)
        except HttpError as exc:
            return error(502, "geocoder_unavailable", str(exc))
        if isinstance(result, regions.NoCoverage):
            return JSONResponse(dump(result))
        region, building = result
        return JSONResponse({**dump(building), "region": region.id})

    async def photo(request: HttpRequest) -> bytes | JSONResponse:
        raw = await request.body()
        if not raw:
            return error(400, "empty_photo")
        if len(raw) > MAX_PHOTO_BYTES:
            return error(413, "photo_too_large")
        try:
            return await run_in_threadpool(prepare_image, raw)
        except ValueError:
            return error(400, "unreadable_photo")

    async def scan(request: HttpRequest) -> JSONResponse:
        jpeg = await photo(request)
        if isinstance(jpeg, JSONResponse):
            return jpeg
        name = request.query_params.get("name", "Room").strip()[:60] or "Room"
        client = MetaClient(svc.transport, svc.settings)
        try:
            result = await run_in_threadpool(scan_room, jpeg, name, client)
        except MetaUnavailable as exc:
            return error(502, "meta_unavailable", str(exc))
        return JSONResponse(dump(result))

    async def gobag(request: HttpRequest) -> JSONResponse:
        jpeg = await photo(request)
        if isinstance(jpeg, JSONResponse):
            return jpeg
        try:
            result = await run_in_threadpool(check_gobag, jpeg, MetaClient(svc.transport, svc.settings))
        except MetaUnavailable as exc:
            return error(502, "meta_unavailable", str(exc))
        return JSONResponse(dump(result))

    async def evac(request: HttpRequest) -> JSONResponse:
        try:
            body = EvacRequest.parse(await request.json())
        except (ValidationError, json.JSONDecodeError) as exc:
            return error(400, "bad_request", str(exc)[:300])
        evac = await run_in_threadpool(regions.evacuate, body.building, body.household, svc.transport,
                                       svc.shelter_transport, datetime.now(timezone.utc), svc.shelter_replay)
        if isinstance(evac, regions.NoCoverage):
            return JSONResponse({"route": None, "shelters": None, "shelters_error": evac.reason})
        return JSONResponse({"route": dump(evac.route), "shelters": dump(evac.shelters),
                             "shelters_error": evac.shelters_error})

    async def demo(request: HttpRequest) -> JSONResponse:
        if request.query_params.get("region") == "jp":
            if not svc.demo_plan_jp.exists():
                return error(404, "no_demo")
            return JSONResponse({**json.loads(svc.demo_plan_jp.read_text(encoding="utf-8")), "region": "jp", "gobag": None,
                                 "extras": {}})
        if not svc.demo_plan.exists():
            return error(404, "no_demo")
        payload = json.loads(svc.demo_plan.read_text(encoding="utf-8"))
        gobag_path = svc.demo_dir / "gobag.json"
        payload["gobag"] = json.loads(gobag_path.read_text(encoding="utf-8")) if gobag_path.exists() else None
        payload["extras"] = {kind: f"/demo/{kind}.jpg" for kind in DEMO_EXTRAS
                             if (svc.demo_dir / f"{kind}.jpg").exists()}
        payload["region"] = "us-ca"
        return JSONResponse(payload)

    routes = [
        Route("/api/health", health),
        Route("/api/guidance", guidance),
        Route("/api/profile", profile),
        Route("/api/scan", scan, methods=["POST"]),
        Route("/api/gobag", gobag, methods=["POST"]),
        Route("/api/evac", evac, methods=["POST"]),
        Route("/api/demo", demo),
        Mount("/demo", StaticFiles(directory=ROOT / "demo"), name="demo"),
        Mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web"),
    ]
    return Starlette(routes=routes, middleware=[Middleware(NoCache)])


def parse_point(lon: str, lat: str) -> tuple[float, float] | None:
    try:
        x, y = float(lon), float(lat)
    except ValueError:
        return None
    if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
        return None
    return x, y


class NoCache:
    """Forces revalidation of the service worker, the page shell and the API, so phones pick up new versions."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path in ("/", "/index.html", "/sw.js") or path.startswith("/api/")):
            await self.app(scope, receive, send)
            return

        async def send_no_cache(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_no_cache)
