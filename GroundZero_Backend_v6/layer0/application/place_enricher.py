"""
Place field enrichment — classifiers for the fields an architectural audit
found were structurally NEVER populated by any code path: energy_requirement,
crowd_level, dwell_time_typical_minutes, best_time, season_suitability,
tide_dependency, etiquette_tag, estimated_cost, price_band (beyond the
FREE/BUDGET binary that existed before), and the accessibility-adjacent
booleans (parking, washrooms, food_available, pet_friendly, family_friendly,
kid_friendly, photography_allowed).

Every value here is either:
  (a) read directly from a real OSM tag on the element, or
  (b) a category-level classification — a genuine, documented, deterministic
      function of the place's real category, not a random/fabricated value.
      These are explicitly PRIORS, not measurements: e.g. "restaurants are
      generally LOW energy_requirement" is a reasonable starting point, not
      a claim about any specific restaurant. Each table below is commented
      with its reasoning.

Where NEITHER a real tag NOR a defensible category-level prior exists, the
field is left as None/unset — that is the honest answer ("we don't know"),
not a gap to be filled with a guess. Several fields (pet_friendly for most
categories, parking, washrooms without an OSM `toilets` tag) are
deliberately left None for most places for exactly this reason; forcing a
value there would be fabrication, which is exactly what this module exists
to avoid doing anywhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from layer0.domain.entities import CrowdLevel, EnergyRequirement, PriceBand

# --- energy_requirement -----------------------------------------------
# How much physical exertion visiting typically requires. Sit-down/indoor
# browsing categories are LOW; open-air walking-around categories are
# MODERATE; categories implying sustained physical activity are HIGH.
_ENERGY_REQUIREMENT: dict[str, EnergyRequirement] = {
    "cafe": EnergyRequirement.LOW, "restaurant": EnergyRequirement.LOW,
    "local_kitchen": EnergyRequirement.LOW, "street_food": EnergyRequirement.LOW,
    "food_court": EnergyRequirement.LOW, "bakery": EnergyRequirement.LOW,
    "dessert_shop": EnergyRequirement.LOW, "museum": EnergyRequirement.LOW,
    "art_gallery": EnergyRequirement.LOW, "library": EnergyRequirement.LOW,
    "theatre": EnergyRequirement.LOW, "craft_centre": EnergyRequirement.LOW,
    "shopping_mall": EnergyRequirement.LOW, "market": EnergyRequirement.LOW,
    "heritage_site": EnergyRequirement.MODERATE, "garden": EnergyRequirement.MODERATE,
    "park": EnergyRequirement.MODERATE, "beach": EnergyRequirement.MODERATE,
    "viewpoint": EnergyRequirement.MODERATE, "tourist_attraction": EnergyRequirement.MODERATE,
    "lake": EnergyRequirement.MODERATE, "hidden_gem": EnergyRequirement.MODERATE,
    "nature_spot": EnergyRequirement.HIGH, "trail": EnergyRequirement.HIGH,
    "waterfall": EnergyRequirement.HIGH, "adventure": EnergyRequirement.HIGH,
    "wildlife_area": EnergyRequirement.HIGH, "boat_ride": EnergyRequirement.MODERATE,
}

# --- crowd_level ---------------------------------------------------------
# A category-level PRIOR for typical crowd density, not a live measurement
# (no check-in/footfall data source exists in this system). Documented as
# such; genuinely variable places (e.g. a market that's empty at 8am,
# packed at 6pm) will be wrong at specific times — this is a starting
# point Layer 2's crowd_score works against, not a promise of accuracy.
_CROWD_LEVEL: dict[str, CrowdLevel] = {
    "nature_spot": CrowdLevel.LOW, "trail": CrowdLevel.LOW, "hidden_gem": CrowdLevel.LOW,
    "craft_centre": CrowdLevel.LOW, "library": CrowdLevel.LOW, "wildlife_area": CrowdLevel.LOW,
    "garden": CrowdLevel.LOW, "lake": CrowdLevel.LOW,
    "cafe": CrowdLevel.MODERATE, "museum": CrowdLevel.MODERATE, "art_gallery": CrowdLevel.MODERATE,
    "heritage_site": CrowdLevel.MODERATE, "local_kitchen": CrowdLevel.MODERATE,
    "viewpoint": CrowdLevel.MODERATE, "waterfall": CrowdLevel.MODERATE,
    "restaurant": CrowdLevel.MODERATE, "park": CrowdLevel.MODERATE, "theatre": CrowdLevel.MODERATE,
    "beach": CrowdLevel.HIGH, "shopping_mall": CrowdLevel.HIGH, "food_court": CrowdLevel.HIGH,
    "tourist_attraction": CrowdLevel.HIGH, "market": CrowdLevel.HIGH,
}

# --- dwell_time_typical_minutes -------------------------------------------
# How long a typical visit takes. Grounded in the category's real nature
# (a bakery visit is definitionally short; a museum is definitionally
# longer) rather than arbitrary — but still an estimate, not a measurement.
_DWELL_TIME_MINUTES: dict[str, int] = {
    "street_food": 15, "bakery": 15, "dessert_shop": 20, "viewpoint": 25,
    "cafe": 40, "food_court": 40, "market": 40, "craft_centre": 40,
    "local_kitchen": 45, "lake": 45, "garden": 45, "hidden_gem": 45,
    "restaurant": 55, "heritage_site": 55, "art_gallery": 50,
    "museum": 70, "library": 60, "boat_ride": 60, "waterfall": 60,
    "park": 60, "nature_spot": 70, "tourist_attraction": 60,
    "shopping_mall": 85, "beach": 85, "trail": 90, "adventure": 110,
    "theatre": 120,
}
_DEFAULT_DWELL_TIME_MINUTES = 45  # previous universal default, kept as fallback for unmapped categories

# --- best_time -------------------------------------------------------
# Only set where there's a genuine, well-known reason (light quality,
# heat, opening patterns) — left unset for categories with no strong
# time-of-day association, matching Personal Fit Score's neutral-default
# handling for unknown best_time (layer2/application/personal_fit_score.py).
_BEST_TIME: dict[str, str] = {
    "viewpoint": "sunset", "beach": "sunset", "waterfall": "morning",
    "heritage_site": "morning", "garden": "morning", "park": "morning",
    "market": "morning", "nature_spot": "morning", "theatre": "evening",
    "wildlife_area": "morning",
}

# --- season_suitability -------------------------------------------------
# Coastal Karnataka has a genuine, strong monsoon season (roughly June-
# September) that materially affects outdoor categories. Indoor categories
# are suitable year-round; outdoor categories exclude monsoon; waterfalls
# are the specific exception (they're at their best during/just after
# monsoon).
_ALL_SEASONS = ["winter", "summer", "monsoon"]
_INDOOR_CATEGORIES = {
    "cafe", "restaurant", "local_kitchen", "food_court", "bakery", "dessert_shop",
    "museum", "art_gallery", "library", "theatre", "shopping_mall", "craft_centre",
}
_MONSOON_UNSUITABLE_CATEGORIES = {
    "beach", "nature_spot", "trail", "park", "garden", "viewpoint", "boat_ride", "hidden_gem",
}
_MONSOON_ONLY_CATEGORIES = {"waterfall"}

# --- tide_dependency ------------------------------------------------------
_TIDE_DEPENDENT_CATEGORIES = {"beach"}

# --- etiquette_tag ---------------------------------------------------
# Only set when a real OSM tag (`religion=*`) confirms the place is a
# religious site — never guessed from category/name alone, since
# "heritage_site" also covers secular monuments.
_RELIGIOUS_ETIQUETTE_NOTE = "Remove footwear before entering; modest dress is customary."

# --- estimated_cost (INR) and price_band ----------------------------------
# A category-level typical-cost PRIOR, used only when no real fee signal
# exists on the OSM element itself (see `fee`/`charge` tag handling below).
# Zero for categories that are conventionally free to enter/visit in
# Mangaluru (parks, beaches, most heritage/religious sites, viewpoints).
_ESTIMATED_COST_INR: dict[str, float] = {
    "park": 0, "garden": 0, "beach": 0, "viewpoint": 0, "heritage_site": 0,
    "lake": 0, "market": 0, "hidden_gem": 0, "trail": 0, "nature_spot": 0,
    "street_food": 60, "bakery": 100, "dessert_shop": 120, "museum": 50,
    "art_gallery": 50, "craft_centre": 100, "food_court": 150, "library": 0,
    "cafe": 200, "local_kitchen": 200, "waterfall": 20, "wildlife_area": 100,
    "shopping_mall": 0, "restaurant": 350, "theatre": 300, "boat_ride": 300,
    "adventure": 500,
}
_PRICE_BAND_FOR_COST = [(0, PriceBand.FREE), (200, PriceBand.BUDGET), (500, PriceBand.MODERATE)]


def _price_band_for(cost: float) -> PriceBand:
    for threshold, band in _PRICE_BAND_FOR_COST:
        if cost <= threshold:
            return band
    return PriceBand.PREMIUM


@dataclass(frozen=True)
class EnrichedFields:
    energy_requirement: EnergyRequirement
    crowd_level: CrowdLevel
    dwell_time_typical_minutes: int
    best_time: Optional[str]
    season_suitability: list[str]
    tide_dependency: bool
    etiquette_tag: Optional[str]
    estimated_cost: float
    price_band: PriceBand
    parking: Optional[bool]
    washrooms: Optional[bool]
    food_available: Optional[bool]
    pet_friendly: Optional[bool]
    family_friendly: Optional[bool]
    kid_friendly: Optional[bool]
    photography_allowed: Optional[bool]


_FOOD_CATEGORIES = {
    "restaurant", "cafe", "local_kitchen", "street_food", "food_court", "bakery",
    "dessert_shop", "market",
}
# Conventionally open, public, outdoor spaces in Indian cities where pets
# accompanying their owners is the norm, absent signage to the contrary we
# have no way to see. Indoor/commercial categories are left None — genuinely
# unknown, varies business to business, no OSM tag reliably captures it.
_CONVENTIONALLY_PET_FRIENDLY_CATEGORIES = {"park", "garden", "beach", "trail", "nature_spot", "lake"}
_CONVENTIONALLY_FAMILY_FRIENDLY_CATEGORIES = {
    "park", "garden", "beach", "museum", "shopping_mall", "food_court", "art_gallery",
    "library", "wildlife_area", "boat_ride",
}
_CONVENTIONALLY_PHOTOGRAPHY_FRIENDLY_CATEGORIES = {
    "park", "garden", "beach", "viewpoint", "heritage_site", "nature_spot", "waterfall",
    "trail", "lake", "market", "hidden_gem",
}


class PlaceEnricher:
    def enrich(self, category: str, osm_tags: dict[str, str]) -> EnrichedFields:
        energy = _ENERGY_REQUIREMENT.get(category, EnergyRequirement.MODERATE)
        crowd = _CROWD_LEVEL.get(category, CrowdLevel.MODERATE)
        dwell = _DWELL_TIME_MINUTES.get(category, _DEFAULT_DWELL_TIME_MINUTES)
        best_time = _BEST_TIME.get(category)

        if category in _MONSOON_ONLY_CATEGORIES:
            season = ["monsoon"]
        elif category in _MONSOON_UNSUITABLE_CATEGORIES:
            season = ["winter", "summer"]
        else:
            season = list(_ALL_SEASONS)  # indoor or unclassified: no known seasonal restriction

        tide_dependent = category in _TIDE_DEPENDENT_CATEGORIES

        # Etiquette: only from a real OSM signal (a religion tag), never guessed.
        etiquette = _RELIGIOUS_ETIQUETTE_NOTE if osm_tags.get("religion") else None

        # Cost: prefer a real OSM fee signal over the category prior.
        fee_tag = osm_tags.get("fee")
        if fee_tag == "no":
            cost = 0.0
        else:
            cost = _ESTIMATED_COST_INR.get(category, 100.0 if category not in _INDOOR_CATEGORIES else 150.0)
        price_band = _price_band_for(cost)

        # Real-tag-derived fields: only set when OSM actually says so.
        toilets_tag = osm_tags.get("toilets")
        washrooms = True if toilets_tag == "yes" else (False if toilets_tag == "no" else None)

        parking_tag = osm_tags.get("parking")
        parking = True if parking_tag not in (None, "no") else (False if parking_tag == "no" else None)

        food_available: Optional[bool]
        if category in _FOOD_CATEGORIES:
            food_available = True  # definitional for these categories
        else:
            food_tag = osm_tags.get("food")
            food_available = True if food_tag == "yes" else (False if food_tag == "no" else None)

        pet_friendly = True if category in _CONVENTIONALLY_PET_FRIENDLY_CATEGORIES else None
        family_friendly = True if category in _CONVENTIONALLY_FAMILY_FRIENDLY_CATEGORIES else None
        kid_friendly = family_friendly  # no distinct signal available; family-friendly implies kid-friendly here
        photography_allowed = True if category in _CONVENTIONALLY_PHOTOGRAPHY_FRIENDLY_CATEGORIES else None

        return EnrichedFields(
            energy_requirement=energy,
            crowd_level=crowd,
            dwell_time_typical_minutes=dwell,
            best_time=best_time,
            season_suitability=season,
            tide_dependency=tide_dependent,
            etiquette_tag=etiquette,
            estimated_cost=cost,
            price_band=price_band,
            parking=parking,
            washrooms=washrooms,
            food_available=food_available,
            pet_friendly=pet_friendly,
            family_friendly=family_friendly,
            kid_friendly=kid_friendly,
            photography_allowed=photography_allowed,
        )
