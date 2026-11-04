"""The safety rule set and every piece of fixed guidance text, with sources.

This module is the single source for the classifier prompt, the plan page,
the emergency screen and the README. Wording follows the cited sources; change
it only against a source.
"""
from __future__ import annotations

from .shapes import Effort, HazardKind

SOURCES = {
    "ready_gov": ("Ready.gov: Earthquakes", "https://www.ready.gov/earthquakes"),
    "shakeout": ("Earthquake Country Alliance / ShakeOut: Recommended Earthquake Safety Actions",
                 "https://www.shakeout.org/dropcoverholdon/"),
    "cgs_tsunami": ("California Geological Survey: What to do before, during and after a tsunami",
                    "https://conservation.ca.gov/cgs/tsunami/preparedness"),
    "cgs_survive": ("California Geological Survey: How to survive a tsunami",
                    "https://www.conservation.ca.gov/cgs/Documents/Tsunami/How-to-Survive-a-Tsunami.pdf"),
    "ready_gov_kit": ("Ready.gov: Build a Kit", "https://www.ready.gov/kit"),
    "pge": ("PG&E: Earthquake safety", "https://www.pge.com/assets/pge/docs/newsroom/safety-action-center/earthquake.pdf"),
}

CLASSIFIER_RULES = """\
Cover: a sturdy table or desk, away from windows and hanging objects. Nothing else counts as cover.
Hazards: unsecured tall furniture; glass (windows, glass doors, mirrors, glass tables); hanging or heavy overhead fixtures (pendant lights, chandeliers, ceiling fans) and hanging objects; heavy or breakable objects stored up high; a bed under a window; cabinet doors that can swing open and spill contents.
Not hazards: a small light fixture mounted flush to the ceiling, smoke detectors, soft items.
Doorways are not safe spots in modern buildings.
During shaking: Drop, Cover, Hold On. No movement.
You report only what is visible. You never judge the building's structure."""

DURING_SHAKING = [
    "DROP onto your hands and knees.",
    "COVER your head and neck with one arm. Get under sturdy cover if it is within a few steps.",
    "HOLD ON until the shaking stops. Do not run outside.",
]

DURING_SPECIAL = {
    "in_bed": "In bed: stay there. Lie face down and cover your head and neck with a pillow.",
    "wheelchair": "In a wheelchair or with a walker: LOCK your wheels, stay seated, COVER your head and neck, HOLD ON.",
    "no_cover": "No table nearby: get next to an interior wall, away from windows, and cover your head and neck.",
    "doorway": "Doorways are not safer than the rest of the room.",
}

AFTER_SHAKING = [
    "Expect aftershocks. Drop, Cover, Hold On again if the ground shakes.",
    "If the building is damaged, go outside and move away from it. Do not go back in.",
    "If you smell gas, get out and move far away.",
    "Use stairs, not elevators.",
]

GO_NOW = (
    "You are in a tsunami hazard area. Strong shaking, or shaking that lasts 20 seconds or more, "
    "means a tsunami may be coming. Go now, on foot, inland or to high ground. Do not wait for an official warning."
)
DIRECTION_ONLY = "No walking route passed SafeZone's checks. Head {compass}, inland and uphill, on foot."
NO_CHECKED_ROUTE = (
    "SafeZone could not check a route out of the hazard area from here. "
    "Walk inland and uphill, away from the water, and follow tsunami evacuation signs."
)
STAY_AWAY = "Waves can keep arriving for 8 hours or longer. Return only when officials say it is safe."
NOT_IN_ZONE = (
    "Your home address is outside the mapped tsunami hazard area. If you are there, stay unless the building "
    "is damaged or officials tell you to leave. If you are on a beach or in a harbor, go inland or to high ground now."
)

DISCLAIMERS = [
    "SafeZone shows hazards it can see in your photos and flags from official public data. "
    "It is not a structural assessment and it does not have your building's plans.",
    "Routes are planning aids computed from California's tsunami hazard map. They are not official evacuation routes.",
    "Shelter listings come from FEMA data that can lag behind reality. Call ahead and confirm with local officials.",
    "Official instructions and local evacuation signs always override this app.",
]

# Hazard kind -> the one fix SafeZone suggests. The model picks the kind; it never writes the fix.
FIX_TABLE: dict[HazardKind, tuple[str, Effort, tuple[int, int]]] = {
    "tall_furniture": ("Strap it to a wall stud. Renting? Ask housing first; most allow straps.", "hour", (10, 30)),
    "heavy_up_high": ("Move heavy or breakable items down low.", "minutes", (0, 0)),
    "tv": ("Strap the TV to the wall or its stand.", "minutes", (15, 40)),
    "glass": ("Apply safety film, or move beds and seating away from the glass.", "hour", (20, 60)),
    "overhead_fixture": ("Have the fixture checked and secured to the ceiling framing.", "pro", (100, 300)),
    "hanging_object": ("Hang it on closed hooks or move it away from beds and seating.", "minutes", (5, 15)),
    "bed_under_window": ("Move the bed away from the window.", "minutes", (0, 0)),
    "cabinet_doors": ("Add latches so the doors stay shut in shaking.", "hour", (10, 25)),
}

HAZARD_LABELS: dict[HazardKind, str] = {
    "tall_furniture": "Tall furniture can tip",
    "heavy_up_high": "Heavy items up high can fall",
    "tv": "TV can fall",
    "glass": "Glass can shatter",
    "overhead_fixture": "Overhead fixture can fall",
    "hanging_object": "Hanging object can fall",
    "bed_under_window": "Bed under a window",
    "cabinet_doors": "Doors can swing open",
}

# Ready.gov's Basic Disaster Supplies Kit, in its order. The model only says which ids it can see.
GO_BAG: list[tuple[str, str]] = [
    ("water", "Water, one gallon per person per day for several days"),
    ("food", "Non-perishable food, at least a several-day supply"),
    ("radio", "Battery-powered or hand crank radio"),
    ("flashlight", "Flashlight"),
    ("first_aid", "First aid kit"),
    ("batteries", "Extra batteries"),
    ("whistle", "Whistle to signal for help"),
    ("dust_mask", "Dust mask"),
    ("sheeting_tape", "Plastic sheeting, scissors and duct tape"),
    ("sanitation", "Moist towelettes, garbage bags and plastic ties"),
    ("wrench", "Wrench or pliers to turn off utilities"),
    ("can_opener", "Manual can opener"),
    ("maps", "Local maps"),
    ("phone_power", "Phone chargers and a backup battery"),
]
GO_BAG_SOURCE = "ready_gov_kit"
GO_BAG_SEEN = "Seen in the photo"
GO_BAG_NOT_SEEN = "Not seen"
GO_BAG_CAVEAT = (
    "This lists what the photo shows. It cannot tell whether your kit is enough for your household: "
    "items can be hidden, packed or out of frame. Check the full list at Ready.gov."
)
