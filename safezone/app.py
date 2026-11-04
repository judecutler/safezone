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

from . import rules
from .building.cgs import in_hazard_area
from .building.geocode import GeocodeNotFound
from .building.pipeline import build_profile
from .config import ROOT, Settings, load_settings
from .meta import MetaClient, MetaUnavailable
from .room.pipeline import prepare_image, scan_room
from .route.pipeline import plan_route
from .shapes import BuildingProfile, DirectionOnly, Household, WalkingRoute
from .shelter.pipeline import find_shelters
from .transport import HttpError, LiveTransport, ReplayTransport, Request, Response, Transport

MAX_PHOTO_BYTES = 20 * 1024 * 1024
FEMA_HOST = "gis.fema.gov"


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

    @classmethod
    def from_env(cls) -> Services:
        settings = load_settings()
        fixtures = os.environ.get("SAFEZONE_FIXTURES")
        transport: Transport = ReplayTransport(Path(fixtures)) if fixtures else LiveTransport()
        snapshot = os.environ.get("SAFEZONE_SHELTER_SNAPSHOT")
        shelter_transport = HostSplit(FEMA_HOST, ReplayTransport(Path(snapshot)), transport) if snapshot else transport
        return cls(settings, transport, shelter_transport, bool(snapshot or fixtures), ROOT / "demo" / "plan.json")


class EvacRequest(BaseModel):
    building: BuildingProfile
    household: Household


def dump(model: BaseModel | None) -> Any:
    return None if model is None else model.model_dump(mode="json")


def error(status: int, code: str, detail: str = "") -> JSONResponse:
    return JSONResponse({"error": code, "detail": detail}, status_code=status)


def create_app(services: Services | None = None) -> Starlette:
    svc = services or Services.from_env()

    async def health(_: HttpRequest) -> JSONResponse:
        return JSONResponse({"meta_key": bool(svc.settings.meta_api_key), "demo_available": svc.demo_plan.exists()})

    async def guidance(_: HttpRequest) -> JSONResponse:
        return JSONResponse({
            "during": rules.DURING_SHAKING,
            "during_special": rules.DURING_SPECIAL,
            "after": rules.AFTER_SHAKING,
            "go_now": rules.GO_NOW,
            "stay_away": rules.STAY_AWAY,
            "not_in_zone": rules.NOT_IN_ZONE,
            "disclaimers": rules.DISCLAIMERS,
            "sources": rules.SOURCES,
            "hazard_labels": rules.HAZARD_LABELS,
        })

    async def profile(request: HttpRequest) -> JSONResponse:
        address = request.query_params.get("address", "").strip()
        if not address or len(address) > 300:
            return error(400, "bad_address")
        try:
            result = await run_in_threadpool(build_profile, address, svc.transport)
        except GeocodeNotFound:
            return error(404, "address_not_found")
        except HttpError as exc:
            return error(502, "geocoder_unavailable", str(exc))
        return JSONResponse(dump(result))

    async def scan(request: HttpRequest) -> JSONResponse:
        raw = await request.body()
        if not raw:
            return error(400, "empty_photo")
        if len(raw) > MAX_PHOTO_BYTES:
            return error(413, "photo_too_large")
        name = request.query_params.get("name", "Room").strip()[:60] or "Room"
        try:
            jpeg = await run_in_threadpool(prepare_image, raw)
        except ValueError:
            return error(400, "unreadable_photo")
        client = MetaClient(svc.transport, svc.settings)
        try:
            result = await run_in_threadpool(scan_room, jpeg, name, client)
        except MetaUnavailable as exc:
            return error(502, "meta_unavailable", str(exc))
        return JSONResponse(dump(result))

    async def evac(request: HttpRequest) -> JSONResponse:
        try:
            body = EvacRequest.model_validate(await request.json())
        except (ValidationError, json.JSONDecodeError) as exc:
            return error(400, "bad_request", str(exc)[:300])
        now = datetime.now(timezone.utc)
        route = await run_in_threadpool(plan_route, body.building, svc.transport, now)
        origin = (route.destination if isinstance(route, (WalkingRoute, DirectionOnly))
                  else (body.building.lon, body.building.lat))
        shelters, shelters_error = None, None
        try:
            shelters = await run_in_threadpool(
                find_shelters, origin, body.building, body.household, svc.shelter_transport,
                lambda point: in_hazard_area(svc.transport, point), now, svc.shelter_replay)
        except (HttpError, ValueError, KeyError) as exc:
            shelters_error = f"Shelter data was unavailable ({type(exc).__name__})."
        return JSONResponse({"route": dump(route), "shelters": dump(shelters), "shelters_error": shelters_error})

    async def demo(_: HttpRequest) -> HttpResponse:
        if not svc.demo_plan.exists():
            return error(404, "no_demo")
        return HttpResponse(svc.demo_plan.read_bytes(), media_type="application/json")

    routes = [
        Route("/api/health", health),
        Route("/api/guidance", guidance),
        Route("/api/profile", profile),
        Route("/api/scan", scan, methods=["POST"]),
        Route("/api/evac", evac, methods=["POST"]),
        Route("/api/demo", demo),
        Mount("/demo", StaticFiles(directory=ROOT / "demo"), name="demo"),
        Mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web"),
    ]
    return Starlette(routes=routes, middleware=[Middleware(NoCache)])


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
