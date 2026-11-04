"""Japan's Hazard Map Portal tsunami inundation raster, read one pixel at a time.

Tiles: https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png, zoom 2 to 17, the
integrated layer of every prefecture's 津波浸水想定 (opendata page in rules.SOURCES["portal_tiles"]). A transparent
pixel, or a tile the server does not have, is no mapped inundation. Any coloured pixel is inside the
inundation area; its colour gives the depth class from MLIT's standard depth colours. A colour that matches no
class still counts as inside, at the deepest class, so a legend mismatch can only make SafeZone more cautious.

The transport stores text and records only answers below 400, so `live_transport` carries tile images
base64-encoded and turns "no tile here" (404) into a 200 with an empty body, for the raster and the GSI site
tiles alike. Recorded fixtures then replay both.
"""
from __future__ import annotations

import base64
import binascii
import io
import math
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests
from PIL import Image, UnidentifiedImageError

from ..shapes import LonLat, Provenance, weakest
from ..transport import NETWORK_FAILURE, USER_AGENT, LiveTransport, Request, Response, Transport

TILE_HOST = "disaportaldata.gsi.go.jp"
TILE_TEMPLATE = f"https://{TILE_HOST}/raster/04_tsunami_newlegend_data/{{z}}/{{x}}/{{y}}.png"
ZOOM = 15
"""About 3.9 m per pixel at Kamakura's latitude; one tile spans about 1 km."""
TILE_PX = 256
NOT_FOUND = 404
COLOUR_TOLERANCE = 12
"""Largest per-channel difference still read as a legend colour (PNG palette rounding)."""


@dataclass(frozen=True)
class DepthClass:
    rgb: tuple[int, int, int]
    en: str
    ja: str


DEPTH_CLASSES: tuple[DepthClass, ...] = (
    # MLIT 水害ハザードマップ作成の手引き (2016), p.38 fig. 3-5 for the classes up to 3 m and p.37 fig. 3-3 above.
    # p.37 says the same classes serve flood, inland flooding, storm surge and tsunami.
    DepthClass((255, 255, 179), "under 0.3 m", "0.3m未満"),
    DepthClass((247, 245, 169), "0.3 m to 0.5 m", "0.3m～0.5m"),
    DepthClass((248, 225, 166), "0.5 m to 1 m", "0.5m～1m"),
    DepthClass((255, 216, 192), "1 m to 3 m", "1m～3m"),
    DepthClass((255, 183, 183), "3 m to 5 m", "3m～5m"),
    DepthClass((255, 145, 145), "5 m to 10 m", "5m～10m"),
    DepthClass((242, 133, 201), "10 m to 20 m", "10m～20m"),
    DepthClass((220, 122, 220), "20 m or more", "20m以上"),
)
UNREAD = len(DEPTH_CLASSES)
"""Class index for a coloured pixel that matches no legend colour: inside, treated as the deepest."""

Depth = int | None
"""None is no mapped inundation; 0..UNREAD index DEPTH_CLASSES (UNREAD = coloured but unrecognised)."""


def depth_label(depth: Depth) -> str:
    if depth is None:
        return "no mapped inundation"
    return DEPTH_CLASSES[depth].en if depth < UNREAD else "depth not read from the map"


class TileUnavailable(RuntimeError):
    """The tile server did not answer, or answered with something that is not a tile. The depth is unknown."""


def tile_of(p: LonLat, z: int) -> tuple[int, int, float, float]:
    """(x, y, px, py): the Web Mercator tile holding p and p's pixel position inside it."""
    lon, lat = p
    n = 2 ** z
    fx = (lon + 180.0) / 360.0 * n
    phi = math.radians(lat)
    fy = (1.0 - math.log(math.tan(phi) + 1.0 / math.cos(phi)) / math.pi) / 2.0 * n
    x, y = int(fx), int(fy)
    return x, y, (fx - x) * TILE_PX, (fy - y) * TILE_PX


def tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) in degrees."""
    n = 2 ** z

    def lat(yy: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))

    return x / n * 360.0 - 180.0, lat(y + 1), (x + 1) / n * 360.0 - 180.0, lat(y)


def classify_rgba(rgba: tuple[int, int, int, int]) -> Depth:
    r, g, b, a = rgba
    if a == 0:
        return None
    best, best_d = UNREAD, COLOUR_TOLERANCE + 1
    for i, cls in enumerate(DEPTH_CLASSES):
        d = max(abs(r - cls.rgb[0]), abs(g - cls.rgb[1]), abs(b - cls.rgb[2]))
        if d < best_d:
            best, best_d = i, d
    return best


def decode_tile(text: str) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(base64.b64decode(text, validate=True)))
        img.load()
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError) as exc:
        raise TileUnavailable(f"not a PNG tile: {exc}") from exc
    if img.size != (TILE_PX, TILE_PX):
        raise TileUnavailable(f"tile is {img.size}, not {TILE_PX}x{TILE_PX}")
    return img.convert("RGBA")


@dataclass
class InundationMap:
    """Reads depth classes at points, fetching each tile once."""
    transport: Transport
    zoom: int = ZOOM
    _tiles: dict[tuple[int, int], Image.Image | None] = field(default_factory=dict)
    provenances: list[Provenance] = field(default_factory=list)

    def tile(self, x: int, y: int) -> Image.Image | None:
        """None when the server has no tile there, which is no mapped inundation."""
        if (x, y) not in self._tiles:
            url = TILE_TEMPLATE.format(z=self.zoom, x=x, y=y)
            resp = self.transport.send(Request("GET", url, timeout_s=30.0))
            self.provenances.append(resp.provenance)
            if resp.status == NOT_FOUND or (resp.status < 400 and not resp.text):
                self._tiles[(x, y)] = None
            elif resp.status >= 400:
                raise TileUnavailable(f"{url} -> {resp.status}: {resp.text[:200]}")
            else:
                self._tiles[(x, y)] = decode_tile(resp.text)
        return self._tiles[(x, y)]

    def depth(self, p: LonLat) -> Depth:
        x, y, px, py = tile_of(p, self.zoom)
        img = self.tile(x, y)
        if img is None:
            return None
        return classify_rgba(img.getpixel((min(int(px), TILE_PX - 1), min(int(py), TILE_PX - 1))))

    def depth_near(self, p: LonLat, radius_m: float) -> Depth:
        """The deepest class at p and at eight points radius_m around it, so a point on the edge reads inside."""
        lon, lat = p
        dlat = radius_m / 111_320.0
        dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
        probes = [p] + [(lon + dlon * math.cos(a), lat + dlat * math.sin(a))
                        for a in (k * math.pi / 4 for k in range(8))]
        found = [d for d in (self.depth(q) for q in probes) if d is not None]
        return max(found, default=None)

    def provenance(self) -> Provenance:
        return weakest(*self.provenances)


# Live transport ----------------------------------------------------------------

SITES_HOST = "cyberjapandata.gsi.go.jp"


@dataclass
class GsiTiles:
    """Fetches GSI tiles. Images come back base64-encoded; a missing tile comes back as 200 with an empty body."""
    _session: requests.Session = field(default_factory=requests.Session)

    def send(self, request: Request) -> Response:
        try:
            r = self._session.get(request.url, headers={"User-Agent": USER_AGENT, **dict(request.headers)},
                                  timeout=request.timeout_s)
        except requests.RequestException as exc:
            return Response(NETWORK_FAILURE, str(exc), "live")
        if r.status_code == NOT_FOUND:
            return Response(200, "", "live")
        if r.status_code >= 400:
            return Response(r.status_code, r.text[:300], "live")
        if urlsplit(request.url).hostname == TILE_HOST:
            return Response(r.status_code, base64.b64encode(r.content).decode("ascii"), "live")
        return Response(r.status_code, r.content.decode("utf-8"), "live")


@dataclass(frozen=True)
class TileSplit:
    tiles: Transport
    default: Transport

    def send(self, request: Request) -> Response:
        host = urlsplit(request.url).hostname
        return (self.tiles if host in (TILE_HOST, SITES_HOST) else self.default).send(request)


def live_transport(default: Transport | None = None) -> Transport:
    return TileSplit(GsiTiles(), default or LiveTransport())
