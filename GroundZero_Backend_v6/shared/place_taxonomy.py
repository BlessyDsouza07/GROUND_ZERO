"""
One place-category vocabulary shared by Layer 0 (ingest/ETL) and Layer 2
(recommendation), so a place means the same thing everywhere.

Why this exists — two real, verified problems it fixes:

1. **Spreadsheet rows kept whatever category word the curator typed.** The
   OSM path maps `place_of_worship` -> `heritage_site` (etl_orchestrator
   `_CATEGORY_MAP`), so temples, churches and mosques from OSM get the
   heritage priors (energy / crowd / dwell / etiquette) and count as
   "spiritual" matches in Personal Fit Score (`Purpose.SPIRITUAL` ->
   {"heritage_site"}). A CSV row typed as `temple` or `mosque` skipped all
   of that: it got generic default priors and scored 0.4 instead of 1.0 on
   the companion axis for a spiritual traveller. `canonical_category()`
   closes that gap for every source.

2. **Nothing stopped non-attractions from filling itinerary slots.**
   Personal slots were filled from *every* surviving candidate regardless
   of category, so hotels (`lodging`, 100+ rows), hospitals, EV chargers,
   bus stands or `uncategorized` rows could be scheduled as "stops" in a
   tourist's day. `is_itinerary_eligible()` is the single whitelist that
   decides what may be *recommended*. Ineligible places stay in the
   database (Ask Engine, geofence and "nearest X" features still want
   them) — they are just never proposed as a stop.

Nothing here invents data: it only renames categories and gates
eligibility.
"""
from __future__ import annotations

import re

# Raw category word (as typed by a curator / found in a research dataset)
# -> canonical Ground Zero category. Keys are matched after
# `_slug()` normalisation, so "Place of Worship" == "place_of_worship".
_ALIASES: dict[str, str] = {
    # places of worship and heritage -> heritage_site (matches OSM path)
    "temple": "heritage_site", "church": "heritage_site", "mosque": "heritage_site",
    "shrine": "heritage_site", "religious": "heritage_site", "place_of_worship": "heritage_site",
    "other_religious_site": "heritage_site", "basadi": "heritage_site", "gurudwara": "heritage_site",
    "heritage": "heritage_site", "monument": "heritage_site", "fort": "heritage_site",
    "heritage_nature": "heritage_site", "cave": "heritage_site",
    # food
    "seafood": "restaurant", "local_food": "local_kitchen", "food_market": "market",
    "fast_food": "street_food", "ice_cream": "dessert_shop", "sweet_shop": "dessert_shop",
    # nature / leisure
    "nature_park": "nature_spot", "nature": "nature_spot", "waterfront": "viewpoint",
    "lighthouse": "tourist_attraction", "zoo": "tourist_attraction", "amusement": "tourist_attraction",
    "planetarium": "museum", "science_and_education": "museum", "arboretum": "park",
    "attraction": "tourist_attraction",
    # stay / services / transit -> kept, but flagged non-itinerary below
    "hotel": "lodging", "resort": "lodging", "guest_house": "lodging", "hostel": "lodging",
    "railway_station": "railway", "ferry_point": "transit_point", "ferry_terminal": "transit_point",
    "jetty": "transit_point", "bus_station": "bus_stand", "bus_terminal": "bus_stand",
    "diagnostic_center": "hospital", "clinic": "hospital", "ambulance": "emergency_point",
    "charging_station": "ev_charger",
    "university": "institution", "college": "institution", "school": "institution",
    "sports": "sports_venue", "stadium": "sports_venue", "gym": "sports_venue",
    "bridge": "landmark_infrastructure",
    "local_life": "locality", "neighbourhood": "locality", "neighborhood": "locality", "area": "locality",
    "unknown": "uncategorized", "": "uncategorized",
}

# Categories that may be proposed as an itinerary stop. Anything else is
# stored but never scheduled. Kept as an explicit whitelist (not a
# blacklist) so a brand-new, unmapped category fails safe — it is not
# recommended until someone consciously decides it should be.
ITINERARY_ELIGIBLE_CATEGORIES: frozenset[str] = frozenset({
    # sights / culture
    "heritage_site", "museum", "art_gallery", "library", "theatre", "tourist_attraction",
    "craft_centre", "hidden_gem",
    # outdoors
    "beach", "viewpoint", "park", "garden", "lake", "nature_spot", "waterfall", "trail",
    "wildlife_area", "boat_ride", "adventure",
    # eating and browsing
    "restaurant", "cafe", "street_food", "local_kitchen", "food_court", "bakery",
    "dessert_shop", "market", "shopping_mall",
})

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str | None) -> str:
    return _SLUG_RE.sub("_", (value or "").strip().lower()).strip("_")


def canonical_category(raw: str | None) -> str:
    """Map any raw category word to the canonical vocabulary. Unknown words
    pass through unchanged (slugged) — never dropped, never guessed."""
    slug = _slug(raw)
    return _ALIASES.get(slug, slug or "uncategorized")


def is_itinerary_eligible(category: str | None) -> bool:
    return canonical_category(category) in ITINERARY_ELIGIBLE_CATEGORIES


# Types that get the same etiquette whisper the OSM path attaches when
# `religion=*` is present. Here the type itself (mosque/temple/church/...)
# is the curator's explicit statement, so it is equally grounded.
WORSHIP_TYPES: frozenset[str] = frozenset({
    "temple", "church", "mosque", "shrine", "religious", "other_religious_site",
    "place_of_worship", "basadi", "gurudwara",
})
RELIGIOUS_ETIQUETTE_NOTE = "Remove footwear before entering; modest dress is customary."
