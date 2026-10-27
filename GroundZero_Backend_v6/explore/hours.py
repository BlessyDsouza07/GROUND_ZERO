"""Is a place open right now? Real listed hours first, typical hours second.

Only ~7% of the place records carry opening hours. For the rest we use the
usual local timings for that kind of place (a tiffin restaurant, a temple,
a beach...). Those are labelled "typically" so the app never states them
as fact. A place is only recommended when it is open, or at least
plausibly open, at the current Mangaluru time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# (start_minute, end_minute) windows; Mon=0. None = all week.
_ALL = [(0, 24 * 60)]
_TYPICAL: dict[str, list[tuple[int, int]]] = {
    "restaurant": [(8 * 60, 22 * 60 + 30)],
    "local_kitchen": [(7 * 60, 21 * 60 + 30)],
    "cafe": [(8 * 60, 22 * 60)],
    "coffee_shop": [(8 * 60, 22 * 60)],
    "bakery": [(8 * 60, 21 * 60)],
    "dessert_shop": [(11 * 60, 22 * 60 + 30)],
    "ice_cream": [(11 * 60, 22 * 60 + 30)],
    "street_food": [(16 * 60, 22 * 60 + 30)],
    "food_court": [(10 * 60, 22 * 60)],
    "market": [(7 * 60, 21 * 60)],
    "local_shop": [(9 * 60 + 30, 21 * 60)],
    "shopping_mall": [(10 * 60, 22 * 60)],
    "temple": [(5 * 60 + 30, 12 * 60 + 30), (16 * 60, 20 * 60 + 30)],
    "church": [(6 * 60, 19 * 60)],
    "mosque": [(5 * 60, 21 * 60)],
    "museum": [(10 * 60, 17 * 60 + 30)],
    "art_gallery": [(10 * 60, 18 * 60)],
    "library": [(9 * 60, 18 * 60)],
    "theatre": [(10 * 60, 23 * 60)],
    "park": [(5 * 60 + 30, 20 * 60)],
    "garden": [(6 * 60, 19 * 60)],
    "lake": [(6 * 60, 19 * 60)],
    "beach": [(6 * 60, 19 * 60 + 30)],
    "viewpoint": [(6 * 60, 19 * 60)],
    "nature_spot": [(6 * 60, 18 * 60 + 30)],
    "heritage_site": [(8 * 60, 18 * 60)],
    "tourist_attraction": [(9 * 60, 18 * 60)],
    "attraction": [(9 * 60, 18 * 60)],
    "lodging": _ALL,
    "transit_point": [(5 * 60, 23 * 60 + 30)],
    "bus_stand": [(4 * 60 + 30, 23 * 60 + 59)],
}
_MUSEUM_CLOSED_DAY = {"museum", "art_gallery"}  # Monday

# Kinds that are sensible to recommend as "somewhere to go" at all.
EAT = {"restaurant", "local_kitchen", "cafe", "coffee_shop", "bakery", "dessert_shop", "ice_cream", "street_food", "food_court"}
STAY = {"lodging"}
TRANSIT = {"transit_point", "bus_stand"}


@dataclass(frozen=True)
class OpenInfo:
    state: str          # "open" | "closed" | "unknown"
    source: str         # "listed" | "typical" | "none"
    label: str          # short human text, e.g. "Open · typically until 10:30 pm"


def _fmt(minute: int) -> str:
    h, m = divmod(minute % (24 * 60), 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def _now_local(now: Optional[datetime]) -> datetime:
    n = now or datetime.now(IST)
    return n.astimezone(IST) if n.tzinfo else n.replace(tzinfo=IST)


def open_info(place, parser, now: Optional[datetime] = None) -> OpenInfo:
    local = _now_local(now)
    raw = (getattr(place.opening_hours, "raw", "") or "").strip()
    if raw and not raw.lower().startswith("http"):
        got = parser.is_open_at(raw, local)
        if got is True:
            return OpenInfo("open", "listed", "Open now")
        if got is False:
            return OpenInfo("closed", "listed", "Closed right now")

    cats = {place.category, *[t for t in (place.tags or []) if t in _TYPICAL]}
    cat = place.category if place.category in _TYPICAL else next((c for c in cats if c in _TYPICAL), None)
    if cat is None:
        return OpenInfo("unknown", "none", "Hours not listed")
    if cat in _MUSEUM_CLOSED_DAY and local.weekday() == 0:
        return OpenInfo("closed", "typical", "Usually closed on Mondays")
    minute = local.hour * 60 + local.minute
    windows = _TYPICAL[cat]
    for start, end in windows:
        if start <= minute < end:
            if cat in STAY:
                return OpenInfo("open", "typical", "Reception usually 24 hours")
            return OpenInfo("open", "typical", f"Usually open until {_fmt(end)}")
    nxt = next((s for s, _ in windows if s > minute), windows[0][0])
    return OpenInfo("closed", "typical", f"Usually closed now · opens about {_fmt(nxt)}")


def minutes_open_left(place, now: Optional[datetime] = None) -> Optional[int]:
    """Minutes until typical closing — used to avoid sending someone to a
    place that shuts in 10 minutes."""
    local = _now_local(now)
    cat = place.category if place.category in _TYPICAL else None
    if not cat:
        return None
    minute = local.hour * 60 + local.minute
    for start, end in _TYPICAL[cat]:
        if start <= minute < end:
            return end - minute
    return None
