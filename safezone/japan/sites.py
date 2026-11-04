"""Designated emergency evacuation sites for tsunami (指定緊急避難場所, 津波) from GSI vector tiles.

Layer skhb05 is the tsunami list (skhb01..08 are one hazard type each), served as GeoJSON tiles at zoom 10 only:
https://cyberjapandata.gsi.go.jp/xyz/skhb05/{z}/{x}/{y}.geojson. Being in this layer is the tsunami designation.
The property names are not documented by GSI; `name` and `address` are what public clients read, and the
Japanese column names of the downloadable data are accepted too. A feature without a point is dropped.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from .. import geo
from ..shapes import LonLat, Provenance, weakest
from ..transport import Request, Transport
from .tiles import NOT_FOUND, TileUnavailable, tile_bounds, tile_of

SITES_TEMPLATE = "https://cyberjapandata.gsi.go.jp/xyz/skhb05/{z}/{x}/{y}.geojson"
SITES_ZOOM = 10
SEARCH_RADIUS_M = 3000.0
NAME_KEYS = ("name", "施設・場所名", "facility_name_ja")
ADDRESS_KEYS = ("address", "住所", "address_ja")
REMARKS_KEYS = ("remarks", "備考")


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    address: str
    lon: float
    lat: float
    remarks: str | None
    source_url: str


def _first(props: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = props.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def parse_sites(data: Any, source_url: str) -> list[Site]:
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise ValueError("not a GeoJSON FeatureCollection")
    sites = []
    for f in data["features"]:
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates")
        if geom.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        props = f.get("properties") or {}
        name = _first(props, NAME_KEYS) or "Unnamed designated site"
        sites.append(Site(id=f"{lon:.6f},{lat:.6f}", name=name, address=_first(props, ADDRESS_KEYS) or "",
                          lon=lon, lat=lat, remarks=_first(props, REMARKS_KEYS), source_url=source_url))
    return sites


def tiles_near(home: LonLat, radius_m: float) -> list[tuple[int, int]]:
    """Home's zoom-10 tile plus every neighbour whose area comes within radius_m of home."""
    x0, y0, _, _ = tile_of(home, SITES_ZOOM)
    dlat = radius_m / 111_320.0
    dlon = dlat / math.cos(math.radians(home[1]))
    out = []
    for x in (x0 - 1, x0, x0 + 1):
        for y in (y0 - 1, y0, y0 + 1):
            w, s, e, n = tile_bounds(x, y, SITES_ZOOM)
            if w - dlon <= home[0] <= e + dlon and s - dlat <= home[1] <= n + dlat:
                out.append((x, y))
    return out


def fetch_sites(transport: Transport, home: LonLat, radius_m: float = SEARCH_RADIUS_M) -> tuple[list[Site], Provenance]:
    """Tsunami-designated sites within radius_m, nearest first. Raises TileUnavailable when a tile fails."""
    sites: dict[str, Site] = {}
    provenances: list[Provenance] = []
    for x, y in tiles_near(home, radius_m):
        url = SITES_TEMPLATE.format(z=SITES_ZOOM, x=x, y=y)
        resp = transport.send(Request("GET", url, timeout_s=30.0))
        provenances.append(resp.provenance)
        if resp.status == NOT_FOUND or (resp.status < 400 and not resp.text):
            continue
        if resp.status >= 400:
            raise TileUnavailable(f"{url} -> {resp.status}: {resp.text[:200]}")
        try:
            parsed = parse_sites(json.loads(resp.text), url)
        except (ValueError, TypeError) as exc:
            raise TileUnavailable(f"{url}: {exc}") from exc
        for site in parsed:
            sites.setdefault(site.id, site)
    near = [s for s in sites.values() if geo.haversine_m(home, (s.lon, s.lat)) <= radius_m]
    near.sort(key=lambda s: geo.haversine_m(home, (s.lon, s.lat)))
    return near, weakest(*provenances)
