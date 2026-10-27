"""Mood -> tag-weight tables, and Explore-by-Experience category
definitions, over the REAL tags that exist in this dataset today
(checked against layer0/data_output/master_data_core.json — categories
are FOOD / SPIRITUAL / DEFAULT / NATURE / EXPLORE / SHOPPING; the tags
below, e.g. "heritage_site", "beach", "local_kitchen", are the ones that
actually appear).

Why tag-level, not category-level: `PersonalFitScoreService`'s
curiosity-affinity lookup (layer1/application/curiosity_extractor.py's
`affinity_for_category`) matches a CuriosityVector's weight keys against
EITHER `place.category` (exact string) OR `place.tags` (also exact
string). This dataset's categories are upper-case bucket labels
("SPIRITUAL", "FOOD") while the engine's own worked examples assume
lower-case descriptive categories ("heritage_site", "restaurant") — a
pre-existing mismatch in the inherited engine, not something this module
introduces or fixes. Matching mood weights against the lower-case TAGS
(which are populated correctly and consistently) is what actually works
today without touching layer1/layer2 at all.
"""
from __future__ import annotations

from dataclasses import dataclass

# mood slug -> { tag: weight }, used to build a synthetic CuriosityVector
# for PersonalFitScoreService, and also used directly for the plain
# "did this place's tags match the chosen mood" boolean behind the
# "WHY THIS PICK? matches your selected mood" checklist line.
MOOD_TAG_WEIGHTS: dict[str, dict[str, float]] = {
    "slow": {"park": 1.0, "garden": 0.9, "lake": 0.85, "cafe": 0.75, "library": 0.6},
    "adventure": {"viewpoint": 1.0, "offbeat": 0.9, "beach": 0.7, "lake": 0.55},
    "quiet": {"garden": 1.0, "park": 0.9, "library": 0.85, "lake": 0.8, "heritage_site": 0.5},
    "local_life": {"street_food": 1.0, "local_kitchen": 1.0, "market": 0.9, "local_shop": 0.85, "local": 0.9, "local-food": 0.9},
    "food": {"restaurant": 1.0, "local_kitchen": 0.95, "street_food": 0.9, "bakery": 0.8, "cafe": 0.7, "dessert_shop": 0.8, "seafood": 0.85},
    "culture": {"heritage_site": 1.0, "temple": 0.9, "church": 0.85, "museum": 0.9, "theatre": 0.7, "heritage": 0.9},
    "nature": {"park": 1.0, "garden": 0.9, "lake": 0.9, "beach": 0.55},
    "the_sea": {"beach": 1.0, "seafood": 0.6, "viewpoint": 0.5},
    "unexpected": {"offbeat": 1.0, "uncategorized": 0.45},
}

MOOD_LABELS: dict[str, str] = {
    "slow": "Slow Mangaluru",
    "adventure": "Adventure",
    "quiet": "Quiet Mangaluru",
    "local_life": "Local Life",
    "food": "Food",
    "culture": "Culture",
    "nature": "Nature",
    "the_sea": "The Sea",
    "unexpected": "Something Unexpected",
}

MOOD_TAGLINES: dict[str, str] = {
    "slow": "Places where nothing is rushed.",
    "adventure": "Places that ask a little more of you.",
    "quiet": "Places where the city slows down.",
    "local_life": "How Mangaluru actually lives.",
    "food": "Eat the way the city eats.",
    "culture": "Heritage, faith, and old stone.",
    "nature": "Green, water, open air.",
    "the_sea": "The coast, on its own terms.",
    "unexpected": "Worth finding, hard to search for.",
}


@dataclass(frozen=True)
class ExperienceCategory:
    slug: str
    label: str
    tags: tuple[str, ...]
    categories: tuple[str, ...] = ()


# "Explore by Experience" — large visual sections, positioned BELOW mood
# discovery per Carol's spec (never the primary navigation).
EXPERIENCE_CATEGORIES: list[ExperienceCategory] = [
    ExperienceCategory("coast", "Coast", ("beach", "seafood")),
    ExperienceCategory("food_flavours", "Food & Flavours", ("restaurant", "street_food", "local_kitchen", "bakery", "dessert_shop", "cafe"), ("FOOD",)),
    ExperienceCategory("culture_heritage", "Culture & Heritage", ("heritage_site", "heritage", "museum", "theatre", "library")),
    ExperienceCategory("nature", "Nature", ("park", "garden", "lake"), ("NATURE",)),
    ExperienceCategory("local_life", "Local Life", ("local", "local_shop", "local_kitchen", "market", "street_food")),
    ExperienceCategory("faith_architecture", "Faith & Architecture", ("temple", "church", "hindu", "muslim", "christian", "heritage_site"), ("SPIRITUAL",)),
    ExperienceCategory("quiet_places", "Quiet Places", ("garden", "park", "library", "lake")),
]
