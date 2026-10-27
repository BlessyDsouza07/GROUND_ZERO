"""Experience knowledge layer.

Turns a raw Place record into what HIVE reasons about: which kinds of
experience it offers (and how strongly), what we actually know about it,
and — kept strictly apart — three different things people tend to blur:

  * authenticity evidence   - is there evidence it is locally used?
  * verification confidence - how sure are we the record is correct today?
  * commercialisation       - signs it is tourist-oriented / promoted

Rule: a missing fact is None (unknown), never False. Several fields in the
master data are filled with defaults (crowd "moderate", media_mentions 0,
local_percentage guesses). A default is treated as unknown here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

EXPERIENCES = {
    "coastal": "Coastal life",
    "food": "Food & everyday local life",
    "heritage": "Living heritage",
    "nature": "Nature & quiet",
    "neighbourhood": "Neighbourhood discovery",
}

# category -> {experience: strength}. Category is weak evidence, so strengths
# stay moderate and the basis is recorded as "category".
_CAT: dict[str, dict[str, float]] = {
    "beach": {"coastal": 0.95, "nature": 0.5},
    "viewpoint": {"coastal": 0.4, "nature": 0.7},
    "lake": {"nature": 0.8},
    "park": {"nature": 0.7, "neighbourhood": 0.3},
    "garden": {"nature": 0.75},
    "nature_spot": {"nature": 0.9},
    "heritage_site": {"heritage": 0.7},
    "temple": {"heritage": 0.8, "neighbourhood": 0.3},
    "church": {"heritage": 0.8, "neighbourhood": 0.3},
    "mosque": {"heritage": 0.75, "neighbourhood": 0.3},
    "museum": {"heritage": 0.85},
    "art_gallery": {"heritage": 0.5, "neighbourhood": 0.3},
    "library": {"heritage": 0.3, "nature": 0.2},
    "market": {"food": 0.6, "neighbourhood": 0.9},
    "local_shop": {"neighbourhood": 0.7},
    "street_food": {"food": 0.9, "neighbourhood": 0.6},
    "local_kitchen": {"food": 0.95, "neighbourhood": 0.5},
    "restaurant": {"food": 0.6},
    "cafe": {"food": 0.4, "neighbourhood": 0.3},
    "coffee_shop": {"food": 0.4, "neighbourhood": 0.3},
    "bakery": {"food": 0.6, "neighbourhood": 0.5},
    "dessert_shop": {"food": 0.55},
    "ice_cream": {"food": 0.5},
    "food_court": {"food": 0.3},
    "shopping_mall": {"neighbourhood": 0.1},
    "theatre": {"heritage": 0.4, "neighbourhood": 0.4},
    "tourist_attraction": {"heritage": 0.3, "nature": 0.3},
    "attraction": {"heritage": 0.3, "nature": 0.3},
}

# keyword in name/tags -> (experience, strength)
_KEYWORDS: list[tuple[tuple[str, ...], str, float]] = [
    (("beach", "bay", "estuary", "harbour", "harbor", "jetty", "backwater", "sea", "coast", "lighthouse", "fish"), "coastal", 0.85),
    (("seafood", "kori", "ghee roast", "neer dosa", "tiffin", "udupi", "bunts", "mangalorean", "local-food", "meals", "bun"), "food", 0.8),
    (("basadi", "jain", "palace", "fort", "mutt", "kambala", "bhuta", "daivasthana", "old", "heritage", "gudi", "temple", "church", "mosque"), "heritage", 0.7),
    (("lake", "kere", "garden", "trail", "forest", "hill", "waterfall", "nature", "park"), "nature", 0.7),
    (("bazaar", "bazar", "market", "road", "circle", "lane", "pete", "kankanady", "bunder"), "neighbourhood", 0.6),
]

COMMERCIAL_NAME_HINTS = ("resort", "mall", "inn", "suites", "residency", "plaza", "pvt", "ltd", "franchise")
UTILITY_CATEGORIES = {"lodging", "transit_point", "bus_stand", "railway", "pharmacy", "fire_station", "ev_charger", "uncategorized"}
FOOD_CATEGORIES = {"restaurant", "local_kitchen", "cafe", "coffee_shop", "bakery", "dessert_shop", "ice_cream", "street_food", "food_court"}


def _v(x) -> Optional[str]:
    if x is None:
        return None
    return getattr(x, "value", x)


@dataclass
class Evidence:
    """What we can actually say about a place, with unknowns left as None."""
    sources: list[str] = field(default_factory=list)
    has_description: bool = False
    # verification confidence (is the record right?) 0..1
    verification: float = 0.0
    verification_note: str = ""
    # authenticity (is it locally used?) 0..1 or None; basis explains why
    authenticity: Optional[float] = None
    authenticity_basis: str = "none"      # none | heuristic | community | local_listing
    # commercialisation 0..1 or None
    commercialisation: Optional[float] = None
    commercial_signals: list[str] = field(default_factory=list)
    # facts that may be unknown
    crowd: Optional[str] = None           # low | high | variable | None
    kid_friendly: Optional[bool] = None
    wheelchair: Optional[bool] = None
    stairs: Optional[bool] = None
    washrooms: Optional[bool] = None
    parking: Optional[bool] = None
    photography_allowed: Optional[bool] = None
    price_band: Optional[str] = None
    estimated_cost: Optional[float] = None
    energy: Optional[str] = None
    dwell_minutes: int = 45
    outdoor: bool = False
    tide_dependent: bool = False
    seasons: list[str] = field(default_factory=list)
    etiquette: Optional[str] = None
    best_time: Optional[str] = None
    # how many of the key facts are known (0..1) - drives confidence
    completeness: float = 0.0


@dataclass
class PlaceKnowledge:
    place_id: str
    name: str
    category: str
    experiences: dict[str, float]          # key -> strength
    experience_basis: dict[str, str]       # key -> category | name | tag
    role: str                              # anchor | food | quiet | wildcard | utility
    evidence: Evidence
    lat: float
    lon: float


def _freshness(place, now: datetime) -> tuple[float, str]:
    last = getattr(place, "last_verified_at", None)
    if last is None:
        return 0.2, "no verification date on record"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = max(0, (now - last).days)
    if days <= 30:
        return 0.6, f"record checked {days} days ago"
    if days <= 180:
        return 0.45, f"record checked {days} days ago"
    return 0.25, f"record last checked {days} days ago"


def build_evidence(place, now: Optional[datetime] = None) -> Evidence:
    now = now or datetime.now(timezone.utc)
    ev = Evidence()
    ev.sources = [str(_v(s)) for s in (place.source or [])]
    ev.has_description = bool((place.description or "").strip() or (place.wiki_summary or "").strip())

    # verification confidence: sources agreeing + freshness; one OSM record is
    # modest evidence, not proof.
    fresh, note = _freshness(place, now)
    n_src = len(set(ev.sources))
    ver = fresh * 0.6 + min(n_src, 3) / 3 * 0.3 + (0.1 if ev.has_description else 0.0)
    if "community_submission" in ev.sources and "openstreetmap" not in ev.sources and n_src == 1:
        ver = min(ver, 0.35)
    ev.verification = round(min(ver, 0.95), 2)
    ev.verification_note = f"{n_src} source(s); {note}"

    # authenticity evidence
    b = place.bias_signals
    if "community_submission" in ev.sources:
        ev.authenticity, ev.authenticity_basis = 0.7, "community"
    elif "local_listing" in ev.sources and (b.local_percentage or 0) > 0:
        ev.authenticity, ev.authenticity_basis = min(1.0, b.local_percentage), "local_listing"
    elif (b.local_percentage or 0) > 0:
        # the master-data value is a heuristic estimate, not a measurement
        ev.authenticity, ev.authenticity_basis = min(0.5, b.local_percentage), "heuristic"

    # commercialisation: only what we can point to
    sig: list[str] = []
    if b.sponsored_indicator:
        sig.append("sponsored listing")
    if (b.commercial_flags or 0) > 0:
        sig.append(f"{b.commercial_flags} commercial flag(s)")
    if (b.media_mentions or 0) > 0:
        sig.append(f"{b.media_mentions} media mention(s)")
    lname = (place.name or "").lower()
    if any(h in lname for h in COMMERCIAL_NAME_HINTS):
        sig.append("chain/commercial style name")
    ev.commercial_signals = sig
    if sig or place.bias_index is not None:
        base = float(place.bias_index) if place.bias_index is not None else 0.0
        ev.commercialisation = round(min(1.0, base + 0.15 * len(sig)), 2)

    crowd = _v(place.crowd_level)
    ev.crowd = crowd if crowd in ("low", "high", "variable") else None   # "moderate" is the default
    ev.kid_friendly = place.kid_friendly if place.kid_friendly is not None else place.family_friendly
    ev.wheelchair = place.accessibility.wheelchair
    ev.stairs = place.accessibility.stairs
    ev.washrooms, ev.parking, ev.photography_allowed = place.washrooms, place.parking, place.photography_allowed
    ev.price_band = _v(place.price_band)
    ev.estimated_cost = place.estimated_cost
    ev.energy = _v(place.energy_requirement)
    ev.dwell_minutes = place.dwell_time_typical_minutes or 45
    ev.outdoor = place.is_outdoor()
    ev.tide_dependent = bool(place.tide_dependency)
    ev.seasons = list(place.season_suitability or [])
    ev.etiquette = place.etiquette_tag
    ev.best_time = place.best_time

    known = [ev.crowd, ev.kid_friendly, ev.wheelchair, ev.washrooms, ev.parking,
             ev.has_description or None, place.opening_hours.opens_at or place.opening_hours.raw or None]
    ev.completeness = round(sum(1 for k in known if k not in (None, "")) / len(known), 2)
    return ev


def classify(place, now: Optional[datetime] = None) -> PlaceKnowledge:
    cat = place.category or "uncategorized"
    exp: dict[str, float] = {}
    basis: dict[str, str] = {}
    for k, s in _CAT.get(cat, {}).items():
        exp[k], basis[k] = s, "category"
    hay = " ".join([(place.name or "").lower()] + [t.lower() for t in place.tags])
    for words, key, s in _KEYWORDS:
        if any(w in hay for w in words):
            # keyword evidence on top of the category lifts the score a little
            new = s if key not in exp else min(1.0, max(exp[key], s) + 0.1)
            if new > exp.get(key, 0):
                exp[key] = round(new, 2)
                basis[key] = "name/tag" if key not in basis else "category+name/tag"
    if cat in UTILITY_CATEGORIES:
        role = "utility"
        exp = {k: v for k, v in exp.items() if v >= 0.6}
    elif cat in FOOD_CATEGORIES:
        role = "food"
    else:
        role = "anchor"
    ev = build_evidence(place, now)
    if role == "anchor" and ev.crowd == "low" and exp.get("nature", 0) >= 0.5:
        role = "quiet"
    return PlaceKnowledge(
        place_id=str(place.id), name=place.name, category=cat,
        experiences={k: round(v, 2) for k, v in exp.items()},
        experience_basis=basis, role=role, evidence=ev,
        lat=place.coordinates.latitude, lon=place.coordinates.longitude,
    )
