"""
city_profiles/city_profile.py

CityProfile — the single config object that makes the engine city-agnostic.

HOW SCALABILITY WORKS:
  To add a NEW city, you only need to:
  1. Create a new file in city_profiles/  (e.g. mysore_profile.py)
  2. Define a CityProfile object with the city's bbox, name variants,
     local foods, landmarks, wikipedia articles, and RSS feeds
  3. Run: python -m data_collector.city_bootstrap --city mysore

  Everything else (OSM queries, normalization, trend collection,
  specialty collector, bootstrap pipeline) reads from the CityProfile
  and runs automatically. Zero code changes needed in any engine file.

WHAT A CityProfile CONTAINS:
  - Identity: names, country, state, timezone
  - Geography: bounding box (always works), known OSM relation ID (faster)
  - Local foods: what a tour guide would list as must-eat
  - Landmark seeds: curated places OSM alone won't fully capture
  - Wikipedia articles: which articles to track for trend signals
  - RSS feeds: local news sources for event collection
  - Language: local script names (Kannada, Tamil, Telugu, etc.)
  - Seasons: when to visit, monsoon dates, peak tourist season
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ============================================================
# LANDMARK SEED — a curated place the engine should know about
# ============================================================

@dataclass
class LandmarkSeed:
    """A single curated place entry."""
    name: str
    lat: float
    lon: float
    subcategory: str           # e.g. "Beach", "Hindu Temple", "Must-Eat Restaurant"
    domain: str                # places / food / explore / activities / local / stay
    notes: str = ""            # tour guide tip — what makes this special
    wikipedia_title: str = ""  # Wikipedia article title (underscores) for enrichment
    best_time: str = ""        # e.g. "sunrise", "evening", "monsoon season"
    tags: List[str] = field(default_factory=list)  # searchable tags


# ============================================================
# RSS FEED CONFIG
# ============================================================

@dataclass
class RSSFeedConfig:
    name: str
    url: str
    language: str = "en"        # en, kn, ml, ta, te, hi etc.
    relevance_keywords: List[str] = field(default_factory=list)


# ============================================================
# CITY PROFILE — the master config
# ============================================================

@dataclass
class CityProfile:
    """
    Complete configuration for one city.

    This is the ONLY thing you need to define to add a new city.
    All collectors, normalizers, and bootstrap scripts read from this.
    """

    # ── IDENTITY ──────────────────────────────────────────────
    city_id: str                    # unique slug: "mangalore", "mysore", "goa"
    display_name: str               # "Mangalore"
    full_name: str                  # "Mangalore, Karnataka, India"
    state: str                      # "Karnataka"
    country: str                    # "India"
    country_code: str               # "IN"
    timezone: str                   # "Asia/Kolkata"

    # ── GEOGRAPHY ─────────────────────────────────────────────
    bbox: Tuple[float, float, float, float]
    # (south, west, north, east) — always works, no API needed
    # Find your city's bbox: https://boundingbox.klokantech.com/

    center_lat: float               # city center latitude
    center_lon: float               # city center longitude

    osm_relation_id: Optional[int] = None
    # Known OSM relation ID — faster than dynamic lookup.
    # Find at: https://www.openstreetmap.org/relation/<id>
    # Leave None to use dynamic lookup (slower but universal)

    wikidata_qid: Optional[str] = None
    # Wikidata QID for the city — avoids wrong dynamic lookup.
    # Find at: https://www.wikidata.org — search city name, copy Q-number
    # e.g. Mangalore = "Q42941", Mysore = "Q3397", Goa = "Q1191"

    osm_admin_levels: List[str] = field(default_factory=lambda: ["6", "7", "8"])
    # OSM admin levels to try for area lookup
    # India cities: 6 = City Corp, 7 = CMC, 8 = Town Municipal

    # ── NAME VARIANTS ─────────────────────────────────────────
    name_variants: List[str] = field(default_factory=list)
    # All spellings OSM might use — old name, romanisation, official name
    # e.g. ["Mangaluru", "Mangalore", "ಮಂಗಳೂರು"]

    local_language_name: str = ""   # native script name
    local_language_code: str = ""   # "kn", "ml", "ta", "te", "hi"

    # ── CUISINE & FOOD IDENTITY ───────────────────────────────
    signature_foods: List[str] = field(default_factory=list)
    # Must-eat dishes unique to this city
    # e.g. ["Neer Dosa", "Kori Rotti", "Goli Baje", "Kane Fish Fry"]

    food_culture_notes: str = ""
    # One paragraph about the city's food culture for tour guide context

    local_ingredients: List[str] = field(default_factory=list)
    # Ingredients the city is known for — spices, seafood, produce
    # e.g. ["Coconut", "Ghee Roast Masala", "Kori (chicken)", "Neer (water)"]

    # ── CURATED LANDMARKS ─────────────────────────────────────
    landmarks: List[LandmarkSeed] = field(default_factory=list)
    # Curated places the engine should always know about.
    # These supplement OSM — cover famous spots that may be incomplete in OSM.

    # ── WIKIPEDIA TRACKING ────────────────────────────────────
    wikipedia_articles: List[str] = field(default_factory=list)
    # Wikipedia article titles (use underscores) to track pageviews.
    # Pick articles directly about this city's landmarks, culture, food.
    # e.g. ["Panambur_Beach", "Yakshagana", "Neer_dosa", "Kori_rotti"]

    # ── RSS / NEWS FEEDS ──────────────────────────────────────
    rss_feeds: List[RSSFeedConfig] = field(default_factory=list)
    # Local news sources — used for event and trend collection

    # ── SEASONS & TIMING ──────────────────────────────────────
    peak_season_months: List[int] = field(default_factory=list)
    # Months (1-12) with highest tourist activity
    # e.g. [10, 11, 12, 1, 2] for Oct-Feb

    monsoon_months: List[int] = field(default_factory=list)
    # Months when monsoon affects outdoor plans
    # e.g. [6, 7, 8, 9] for Jun-Sep (South India)

    best_visit_months: List[int] = field(default_factory=list)
    # Recommended months for tourists

    # ── LOCAL CONTEXT ─────────────────────────────────────────
    local_festivals: List[Dict] = field(default_factory=list)
    # Annual festivals — {"name": "Yaksha Utsava", "month": 11, "notes": "..."}

    day_trip_cities: List[Dict] = field(default_factory=list)
    # Nearby cities for day trips — {"name": "Udupi", "distance_km": 60, "notes": "..."}

    special_experiences: List[str] = field(default_factory=list)
    # Unique things only this city offers
    # e.g. ["Watch Yakshagana performance", "Dawn fish market walk"]

    # ── SEARCH KEYWORDS ───────────────────────────────────────
    search_keywords: List[str] = field(default_factory=list)
    # Keywords for trend tracking and relevance filtering
    # e.g. ["mangalore", "mangaluru", "tulu", "dakshina kannada"]

    # ── OUTPUT PATHS (auto-generated from city_id) ────────────
    @property
    def bbox_str(self) -> str:
        """Overpass bbox string: south,west,north,east"""
        s, w, n, e = self.bbox
        return f"{s},{w},{n},{e}"

    @property
    def osm_area_id(self) -> Optional[int]:
        """Computed Overpass area_id from relation_id."""
        if self.osm_relation_id:
            return self.osm_relation_id + 3600000000
        return None

    @property
    def raw_osm_path(self) -> str:
        return f"data_storage/{self.city_id}_raw.json"

    @property
    def data_hub_path(self) -> str:
        return f"data_storage/{self.city_id}_data_hub.json"

    @property
    def specialties_path(self) -> str:
        return f"data_core/{self.city_id}_specialties.json"

    @property
    def trends_path(self) -> str:
        return f"data_core/{self.city_id}_trends.json"

    @property
    def places_extended_path(self) -> str:
        return f"data_core/{self.city_id}_places_extended.json"

    @property
    def boundary_path(self) -> str:
        return f"config/{self.city_id}_boundary.geojson"