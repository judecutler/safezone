"""City soft-story inventories. Each city is one registry entry; only San Francisco ships."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..shapes import BuildingFlag, FlagTone, Provenance
from ..transport import Transport, get_json

SUFFIXES = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "PLACE": "PL", "COURT": "CT",
    "TERRACE": "TER", "HIGHWAY": "HWY", "ROAD": "RD", "LANE": "LN", "WAY": "WAY", "ALLEY": "ALY",
    "CIRCLE": "CIR", "PARKWAY": "PKWY", "PLAZA": "PLZ", "SQUARE": "SQ", "EXPRESSWAY": "EXPY",
    "FREEWAY": "FWY", "TRAIL": "TRL", "WALK": "WALK", "ROW": "ROW", "LOOP": "LOOP", "HILL": "HL",
    "HEIGHTS": "HTS", "CRESCENT": "CRES", "GARDENS": "GDNS", "GREEN": "GRN", "PARK": "PARK", "PATH": "PATH",
    "STAIRWAY": "STWY", "CENTER": "CTR", "AV": "AVE",
}
ABBREVIATIONS = set(SUFFIXES.values())
UNIT_WORDS = {"APT", "APARTMENT", "UNIT", "STE", "SUITE", "FL", "FLOOR", "RM", "ROOM", "BLDG", "NO"}
NUMBER = re.compile(r"^(\d+)([A-Z]?)(?:-(\d+)([A-Z]?))?$")
COMPLETE = re.compile(r"\bcompleted?\b", re.IGNORECASE)
NEGATION = re.compile(r"\bnot\b", re.IGNORECASE)


@dataclass(frozen=True)
class StreetAddress:
    lo: int
    hi: int
    """Equal to `lo` for one number; a listed range like "998-1002" sets both ends."""
    letter: str
    street: str
    """Uppercase street core with a USPS suffix abbreviation, e.g. "GREAT HWY"."""

    def query_text(self) -> str:
        """Number plus street name without its suffix: San Francisco writes "24TH AV" where USPS says "24TH AVE"."""
        number = f"{self.lo}{self.letter}" if self.lo == self.hi else f"{self.lo}-{self.hi}"
        words = self.street.split()
        if len(words) > 1 and words[-1] in ABBREVIATIONS:
            words = words[:-1]
        return f"{number} {' '.join(words)}"


def normalize_address(text: str) -> StreetAddress | None:
    tokens = [t for t in text.split(",")[0].upper().replace(".", " ").split() if any(ch.isalnum() for ch in t)]
    m = NUMBER.match(tokens[0]) if tokens else None
    if not m:
        return None
    street: list[str] = []
    for tok in tokens[1:]:
        if tok.startswith("#") or (street and tok in UNIT_WORDS):
            break
        if len(street) >= 2 and SUFFIXES.get(street[-1], street[-1]) in ABBREVIATIONS and NUMBER.match(tok):
            break
        street.append(tok)
    if not street:
        return None
    street[-1] = SUFFIXES.get(street[-1], street[-1])
    lo = int(m.group(1))
    return StreetAddress(lo, int(m.group(3) or lo), m.group(2), " ".join(street))


def same_street(a: str, b: str) -> bool:
    """Equal streets. DataSF sometimes leaves the suffix off ("1230 LA PLAYA"); then the names alone decide.
    Two different suffixes never match: San Francisco has both a 24th Street and a 24th Avenue."""
    if a == b:
        return True
    core_a, core_b = _core(a), _core(b)
    return core_a == core_b and (core_a == a or core_b == b)


def _core(street: str) -> str:
    words = street.split()
    return " ".join(words[:-1]) if len(words) > 1 and words[-1] in ABBREVIATIONS else street


def same_building(ours: StreetAddress, theirs: StreetAddress) -> bool:
    if not same_street(ours.street, theirs.street):
        return False
    if ours.lo == ours.hi and theirs.lo == theirs.hi:
        return (ours.lo, ours.letter) == (theirs.lo, theirs.letter)
    # A range covers the numbers between its ends on the same side of the street.
    return max(ours.lo, theirs.lo) <= min(ours.hi, theirs.hi) and ours.lo % 2 == theirs.lo % 2


def is_complete(status: str | None) -> bool:
    return bool(status and COMPLETE.search(status) and not NEGATION.search(status))


# San Francisco ---------------------------------------------------------------

SF_ENDPOINT = "https://data.sfgov.org/resource/beah-shgi.json"
SF_PAGE = "https://data.sfgov.org/d/beah-shgi"
SF_LIMIT = 50
"""Generous so that short numbers ("1 MAIN ST" also matches "101 MAIN ST") cannot crowd out the real match."""


class _SfRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    property_address: str | None = None
    address: str | None = None
    status: str | None = None


def parse_sf(ours: StreetAddress, data: Any) -> list[str | None]:
    """Statuses of the rows that are exactly this building."""
    rows = [_SfRow.model_validate(r) for r in data]
    statuses = []
    for row in rows:
        theirs = normalize_address(row.property_address or row.address or "")
        if theirs and same_building(ours, theirs):
            statuses.append(row.status)
    return statuses


def lookup_sf(transport: Transport, ours: StreetAddress) -> tuple[list[str | None], Provenance]:
    like = ours.query_text().replace("'", "''")
    data, provenance = get_json(transport, SF_ENDPOINT, {
        "$where": f"upper(property_address) like '%{like}%'", "$limit": SF_LIMIT,
    })
    return parse_sf(ours, data), provenance


# Registry --------------------------------------------------------------------

@dataclass(frozen=True)
class Inventory:
    city: str
    program: str
    source_name: str
    source_url: str
    lookup: Callable[[Transport, StreetAddress], tuple[list[str | None], Provenance]]


INVENTORIES: dict[str, Inventory] = {
    "san francisco": Inventory(
        city="San Francisco", program="Mandatory Soft Story Program",
        source_name="DataSF: Soft-Story Properties (Mandatory Soft Story Program)", source_url=SF_PAGE,
        lookup=lookup_sf,
    ),
}
COVERAGE = INVENTORIES["san francisco"]


def inventory_for(city: str | None) -> Inventory | None:
    return INVENTORIES.get((city or "").strip().casefold())


def _flag(inv: Inventory, tone: FlagTone, value: str, detail: str, status: str | None,
          provenance: Provenance) -> BuildingFlag:
    return BuildingFlag(kind="soft_story", tone=tone, value=value, detail=detail, status=status,
                        source_name=inv.source_name, source_url=inv.source_url, provenance=provenance)


def result_flag(inv: Inventory, statuses: list[str | None], provenance: Provenance) -> BuildingFlag:
    if not statuses:
        return _flag(inv, "info", f"Not found in {inv.city}'s soft-story list",
                     "Not being on the list is not proof the building is not soft-story; "
                     "the list covers the city's mandatory program only.", None, provenance)
    # When records disagree, the one with work still open decides.
    status = next((s for s in statuses if not is_complete(s)), statuses[0])
    shown = status.strip().rstrip(".") if status and status.strip() else "not given in the city's data"
    return _flag(inv, "info" if is_complete(status) else "alert", f"On {inv.city}'s soft-story list",
                 f"The city lists this building in its {inv.program} (wood-frame, with a weak ground floor "
                 f"such as garages or open storefronts). City status: {shown}.", status, provenance)


def no_inventory_flag(city: str | None, provenance: Provenance) -> BuildingFlag:
    return _flag(COVERAGE, "unknown", f"No soft-story inventory for {city or 'this area'}",
                 "SafeZone has soft-story data for San Francisco only so far.", None, provenance)


def unreachable_flag(inv: Inventory, provenance: Provenance) -> BuildingFlag:
    return _flag(inv, "unknown", "Soft-story list could not be reached",
                 f"Check {inv.city}'s soft-story list directly before relying on this plan.", None, provenance)


def unparsed_flag(inv: Inventory, provenance: Provenance) -> BuildingFlag:
    return _flag(inv, "unknown", "Soft-story list not checked",
                 f"SafeZone needs a street number and street name to look this address up in {inv.city}'s list.",
                 None, provenance)
