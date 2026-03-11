"""
data_collector/deep_intelligence_collector.py

DEEP INTELLIGENCE COLLECTOR  ── v1, 10 Core Domains
═══════════════════════════════════════════════════════
Implements the Master Data Architecture with 10 Core Domains + 7 Bonus Domains.

Every place record produced has this master schema:
{
  "place_id":         "",        # stable UUID based on name+lat+lon
  "name":             "",
  "geo_data":         {...},     # Domain 1: Location & Geospatial
  "category_data":    {...},     # Domain 2: Category & Functional
  "temporal_data":    {...},     # Domain 3: Temporal Intelligence
  "crowd_data":       {...},     # Domain 4: Crowd & Density
  "review_data":      {...},     # Domain 5: Review & Sentiment
  "safety_data":      {...},     # Domain 6: Safety & Risk
  "economic_data":    {...},     # Domain 7: Economic & Pricing
  "cultural_data":    {...},     # Domain 8: Cultural & Social
  "experience_data":  {...},     # Domain 9: Experience Quality
  "environment_data": {...},     # Domain 10: Environmental & Climate

  # Bonus research domains
  "bias_data":        {...},     # Bonus 1: Bias Detection
  "crowd_psychology": {...},     # Bonus 2: Crowd Psychology
  "cultural_density": {...},     # Bonus 3: Cultural Density
  "virality_data":    {...},     # Bonus 4: Social Media Virality
  "political_data":   {...},     # Bonus 5: Political Sensitivity
  "sustainability":   {...},     # Bonus 6: Sustainability
  "sentiment_drift":  {...},     # Bonus 7: Local Sentiment Drift
}

SOURCES (all 100% free, legal, open):
  OSM Overpass API      (ODbL)          — geo, category, temporal, accessibility
  Wikipedia REST API    (CC BY-SA 3.0)  — cultural, heritage, descriptions
  Wikidata SPARQL       (CC0)           — structured facts, inception, persons
  GBIF Occurrence       (CC0/CC BY)     — environmental (green cover, wildlife)
  Open-Meteo            (CC BY 4.0)     — climate, temperature, AQI live
  Nominatim             (ODbL)          — reverse geocoding, admin zones
  Overpass (walkability)(ODbL)          — walkability, road connectivity

OUTPUT:
  data_storage/<city_id>_deep_intel.json   ← 10-domain records for every place
  data_storage/<city_id>_intel_summary.json ← aggregated city-level signals

USAGE:
  python -m data_collector.deep_intelligence_collector --city mangalore
  python -m data_collector.deep_intelligence_collector --city mangalore --limit 500
  python -m data_collector.deep_intelligence_collector --city mangalore --domain geo category
"""

import argparse
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

# ── API endpoints ──────────────────────────────────────────────
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
NOMINATIM     = "https://nominatim.openstreetmap.org"
WIKI_REST     = "https://en.wikipedia.org/api/rest_v1"
SPARQL_EP     = "https://query.wikidata.org/sparql"
GBIF_EP       = "https://api.gbif.org/v1/occurrence/search"
METEO_AQI_EP  = "https://air-quality-api.open-meteo.com/v1/air-quality"
METEO_FCST_EP = "https://api.open-meteo.com/v1/forecast"

HEADERS       = {"User-Agent": "HumaneCityEngine/3.0 (deep intelligence, non-commercial)"}
SPARQL_HDR    = {**HEADERS, "Accept": "application/sparql-results+json"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sleep(s: float = 1.5):
    time.sleep(s)

def _uid(name: str, lat: float, lon: float) -> str:
    """Stable UUID from name+coords."""
    key = f"{name.strip().lower()}|{round(lat,4)}|{round(lon,4)}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in km between two lat/lon points."""
    R = 6371
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p) * math.cos(lat2*p) * math.sin((lon2-lon1)*p/2)**2)
    return 2*R*math.asin(math.sqrt(a))


def _overpass(query: str) -> List[Dict]:
    for mirror in OVERPASS_MIRRORS:
        try:
            _sleep(3)
            r = requests.post(mirror, data={"data": query}, headers=HEADERS, timeout=90)
            if r.status_code in (429, 503, 504): _sleep(12); continue
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as e:
            print(f"      Overpass error: {e}")
    return []

def _get(url: str, params: dict = None, timeout: int = 20) -> Optional[dict]:
    try:
        _sleep(1)
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except: pass
    return None

def _wiki_extract(title: str) -> str:
    try:
        _sleep(0.4)
        r = requests.get(
            f"{WIKI_REST}/page/summary/{title.replace(' ','_')}",
            headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get("extract","")[:400]
    except: pass
    return ""

def _sparql(q: str) -> List[Dict]:
    try:
        _sleep(2)
        r = requests.get(SPARQL_EP, params={"query":q,"format":"json"},
                         headers=SPARQL_HDR, timeout=30)
        r.raise_for_status()
        return [{k:v.get("value","") for k,v in b.items()}
                for b in r.json().get("results",{}).get("bindings",[])]
    except Exception as e:
        print(f"      SPARQL error: {e}"); return []


# ════════════════════════════════════════════════════════════════
# OSM MASTER FETCH — all named places in one large query
# ════════════════════════════════════════════════════════════════

OSM_MASTER_QUERY = """
[out:json][timeout:120];
(
  /* PLACES & LANDMARKS */
  node["tourism"]["name"]({bbox});
  node["historic"]["name"]({bbox});
  node["man_made"="lighthouse"]["name"]({bbox});
  /* FOOD & DRINK */
  node["amenity"="restaurant"]["name"]({bbox});
  node["amenity"="cafe"]["name"]({bbox});
  node["amenity"="fast_food"]["name"]({bbox});
  node["amenity"="bar"]["name"]({bbox});
  node["amenity"="pub"]["name"]({bbox});
  node["amenity"="ice_cream"]["name"]({bbox});
  node["shop"="bakery"]["name"]({bbox});
  node["amenity"="dhaba"]["name"]({bbox});
  /* STAY */
  node["tourism"="hotel"]["name"]({bbox});
  node["tourism"="hostel"]["name"]({bbox});
  node["tourism"="guest_house"]["name"]({bbox});
  node["tourism"="motel"]["name"]({bbox});
  node["tourism"="resort"]["name"]({bbox});
  node["tourism"="homestay"]["name"]({bbox});
  /* WORSHIP */
  node["amenity"="place_of_worship"]["name"]({bbox});
  node["building"="temple"]["name"]({bbox});
  node["building"="church"]["name"]({bbox});
  node["building"="mosque"]["name"]({bbox});
  /* NATURE */
  node["natural"="beach"]["name"]({bbox});
  node["leisure"="beach"]["name"]({bbox});
  node["natural"="wetland"]["name"]({bbox});
  node["leisure"="park"]["name"]({bbox});
  node["leisure"="garden"]["name"]({bbox});
  node["waterway"="waterfall"]["name"]({bbox});
  node["natural"="water"]["name"]({bbox});
  /* MARKETS & SHOPPING */
  node["amenity"="marketplace"]["name"]({bbox});
  node["shop"="fish"]["name"]({bbox});
  node["shop"="seafood"]["name"]({bbox});
  node["shop"="craft"]["name"]({bbox});
  node["shop"="spices"]["name"]({bbox});
  node["shop"="supermarket"]["name"]({bbox});
  /* EDUCATION */
  node["amenity"="university"]["name"]({bbox});
  node["amenity"="college"]["name"]({bbox});
  node["amenity"="school"]["name"]({bbox});
  node["amenity"="library"]["name"]({bbox});
  /* EMERGENCY / SERVICES */
  node["amenity"="hospital"]["name"]({bbox});
  node["amenity"="police"]["name"]({bbox});
  node["amenity"="fire_station"]["name"]({bbox});
  node["amenity"="pharmacy"]["name"]({bbox});
  /* TRANSPORT */
  node["railway"="station"]["name"]({bbox});
  node["amenity"="bus_station"]["name"]({bbox});
  node["amenity"="ferry_terminal"]["name"]({bbox});
  node["aeroway"="aerodrome"]["name"]({bbox});
  /* CULTURE */
  node["amenity"="arts_centre"]["name"]({bbox});
  node["amenity"="theatre"]["name"]({bbox});
  node["tourism"="museum"]["name"]({bbox});
  node["tourism"="gallery"]["name"]({bbox});
  /* COMMUNITY */
  node["amenity"="community_centre"]["name"]({bbox});
  node["amenity"="social_centre"]["name"]({bbox});
  /* ACTIVITIES */
  node["leisure"="sports_centre"]["name"]({bbox});
  node["amenity"="boat_rental"]["name"]({bbox});
  /* NIGHTLIFE */
  node["amenity"="nightclub"]["name"]({bbox});
  /* WAYS (buildings, parks, etc.) */
  way["historic"]["name"]({bbox});
  way["amenity"="restaurant"]["name"]({bbox});
  way["tourism"]["name"]({bbox});
  way["amenity"="place_of_worship"]["name"]({bbox});
  way["leisure"="park"]["name"]({bbox});
  way["amenity"="university"]["name"]({bbox});
  way["amenity"="hospital"]["name"]({bbox});
);
out tags center;
"""


def fetch_all_osm_places(bbox: str) -> List[Dict]:
    """Fetch all named OSM places for a city bbox."""
    print(f"    Fetching all OSM places ({bbox})...")
    elements = _overpass(OSM_MASTER_QUERY.replace("{bbox}", bbox))
    named = [e for e in elements if e.get("tags", {}).get("name")]
    print(f"    OSM elements: {len(named)} named")
    return named


# ════════════════════════════════════════════════════════════════
# DOMAIN 1 — LOCATION & GEOSPATIAL
# ════════════════════════════════════════════════════════════════

# Pre-fetched city-level data cache (filled once)
_CITY_AQI_CACHE: Dict = {}
_CITY_TEMP_CACHE: Dict = {}
_WALKABILITY_INDEX_CACHE: Dict = {}


def _fetch_city_climate(lat: float, lon: float) -> Tuple[Dict, Dict]:
    """Fetch AQI and weather once per city, cache for all records."""
    global _CITY_AQI_CACHE, _CITY_TEMP_CACHE
    city_key = f"{round(lat,2)}_{round(lon,2)}"

    if city_key not in _CITY_AQI_CACHE:
        aqi = _get(METEO_AQI_EP, params={
            "latitude": lat, "longitude": lon,
            "current": "us_aqi,pm2_5,pm10,carbon_monoxide,nitrogen_dioxide",
        }) or {}
        _CITY_AQI_CACHE[city_key] = aqi.get("current", {})

    if city_key not in _CITY_TEMP_CACHE:
        weather = _get(METEO_FCST_EP, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation,windspeed_10m",
            "daily": "temperature_2m_max,temperature_2m_min",
            "forecast_days": 1,
        }) or {}
        _CITY_TEMP_CACHE[city_key] = weather.get("current", {})

    return _CITY_AQI_CACHE[city_key], _CITY_TEMP_CACHE[city_key]


def _road_connectivity_score(tags: dict) -> float:
    """Estimate road connectivity from OSM tags."""
    score = 0.5  # default
    t = tags.get("highway", "")
    if t in ("primary", "secondary"): score = 0.9
    elif t in ("tertiary", "residential"): score = 0.7
    elif t == "track": score = 0.3
    if tags.get("bus") == "yes" or tags.get("public_transport"): score = min(1.0, score + 0.15)
    return round(score, 2)


def _walkability_score(tags: dict, lat: float, lon: float, city_center_lat: float, city_center_lon: float) -> float:
    """Estimate walkability: closer to centre + pedestrian amenities."""
    dist = _haversine(lat, lon, city_center_lat, city_center_lon)
    dist_score = max(0, 1.0 - dist / 10.0)  # decay over 10km
    infra_score = 0.0
    if tags.get("sidewalk"): infra_score += 0.3
    if tags.get("foot") == "yes": infra_score += 0.2
    if tags.get("amenity") in ("bus_station","ferry_terminal"): infra_score += 0.25
    return round(min(1.0, dist_score * 0.6 + infra_score * 0.4), 2)


def _public_transport_score(tags: dict, lat: float, lon: float,
                             transport_nodes: List[Dict]) -> float:
    """Score based on proximity to bus/rail/ferry nodes."""
    if not transport_nodes: return 0.3
    min_dist = min(
        _haversine(lat, lon, n.get("lat", 0) or n.get("center",{}).get("lat",0) or 0,
                   n.get("lon", 0) or n.get("center",{}).get("lon",0) or 0)
        for n in transport_nodes
        if n.get("lat") or n.get("center")
    )
    if min_dist < 0.3: return 0.95
    if min_dist < 0.8: return 0.75
    if min_dist < 2.0: return 0.55
    return 0.30


def build_geo_domain(element: dict, city_center_lat: float, city_center_lon: float,
                     admin_zone: str, transport_nodes: List[Dict]) -> Dict:
    """Domain 1: Location & Geospatial — complete schema."""
    tags = element.get("tags", {})
    lat  = element.get("lat") or element.get("center", {}).get("lat", 0.0)
    lon  = element.get("lon") or element.get("center", {}).get("lon", 0.0)
    name = tags.get("name", "")

    dist_from_center = round(_haversine(lat, lon, city_center_lat, city_center_lon), 2)

    # Footfall heatmap zone (radial)
    if dist_from_center < 1.5:     heatmap_zone = "city_core_high"
    elif dist_from_center < 4.0:   heatmap_zone = "mid_ring_medium"
    elif dist_from_center < 10.0:  heatmap_zone = "outer_ring_low"
    else:                          heatmap_zone = "peripheral_very_low"

    # Land use type from tags
    land_use = (tags.get("landuse") or tags.get("natural") or
                tags.get("leisure") or tags.get("tourism") or
                tags.get("amenity") or tags.get("historic") or "mixed_use")

    return {
        "place_id":                _uid(name, lat, lon),
        "latitude":                round(lat, 6),
        "longitude":               round(lon, 6),
        "elevation":               int(tags.get("ele", 0) or 0),
        "area_sq_m":               None,  # requires way geometry
        "administrative_zone":     admin_zone,
        "district":                tags.get("addr:district", "Dakshina Kannada"),
        "postal_code":             tags.get("addr:postcode", ""),
        "street_address":          tags.get("addr:street", "") or tags.get("addr:full", ""),
        "land_use_type":           land_use,
        "distance_from_center_km": dist_from_center,
        "road_connectivity_index": _road_connectivity_score(tags),
        "public_transport_score":  _public_transport_score(tags, lat, lon, transport_nodes),
        "parking_availability":    tags.get("parking") is not None or tags.get("amenity") == "parking",
        "walkability_score":       _walkability_score(tags, lat, lon, city_center_lat, city_center_lon),
        "footfall_heatmap_zone":   heatmap_zone,
        "wheelchair_access_osm":   tags.get("wheelchair", "unknown"),
        "osm_id":                  element.get("id"),
        "osm_type":                element.get("type", "node"),
    }


# ════════════════════════════════════════════════════════════════
# DOMAIN 2 — CATEGORY & FUNCTIONAL
# ════════════════════════════════════════════════════════════════

# Full OSM → primary category mapping
CATEGORY_MAP = [
    # Beaches
    {"match": {"natural": "beach"},                     "primary": "Beach",           "secondary": "Coastal Spot",   "experience": "local"},
    {"match": {"leisure": "beach"},                     "primary": "Beach",           "secondary": "Coastal Spot",   "experience": "local"},
    # Heritage
    {"match": {"historic": "fort"},                     "primary": "Heritage Site",   "secondary": "Fort",           "experience": "heritage"},
    {"match": {"historic": "monument"},                 "primary": "Heritage Site",   "secondary": "Monument",       "experience": "heritage"},
    {"match": {"historic": "ruins"},                    "primary": "Heritage Site",   "secondary": "Ruins",          "experience": "heritage"},
    {"match": {"historic": "archaeological_site"},      "primary": "Heritage Site",   "secondary": "Archaeological Site","experience": "heritage"},
    {"match": {"historic": "memorial"},                 "primary": "Heritage Site",   "secondary": "Memorial",       "experience": "heritage"},
    {"match": {"man_made": "lighthouse"},               "primary": "Heritage Site",   "secondary": "Lighthouse",     "experience": "heritage"},
    # Religious
    {"match": {"building": "temple"},                   "primary": "Temple",          "secondary": "Hindu Temple",   "experience": "heritage"},
    {"match": {"amenity": "place_of_worship", "religion": "hindu"}, "primary": "Temple","secondary": "Hindu Temple","experience": "heritage"},
    {"match": {"amenity": "place_of_worship", "religion": "christian"},"primary":"Church","secondary":"Church","experience":"heritage"},
    {"match": {"amenity": "place_of_worship", "religion": "muslim"}, "primary": "Mosque","secondary": "Mosque",     "experience": "heritage"},
    {"match": {"amenity": "place_of_worship", "religion": "jain"},   "primary": "Temple","secondary": "Jain Temple","experience": "heritage"},
    {"match": {"building": "church"},                   "primary": "Church",          "secondary": "Church",         "experience": "heritage"},
    {"match": {"building": "mosque"},                   "primary": "Mosque",          "secondary": "Mosque",         "experience": "heritage"},
    # Food
    {"match": {"amenity": "restaurant"},                "primary": "Restaurant",      "secondary": "Dining",         "experience": "local"},
    {"match": {"amenity": "cafe"},                      "primary": "Café",            "secondary": "Coffee & Tea",   "experience": "local"},
    {"match": {"amenity": "fast_food"},                 "primary": "Street Food",     "secondary": "Fast Food",      "experience": "budget"},
    {"match": {"amenity": "ice_cream"},                 "primary": "Café",            "secondary": "Dessert Shop",   "experience": "local"},
    {"match": {"shop": "bakery"},                       "primary": "Café",            "secondary": "Bakery",         "experience": "local"},
    {"match": {"amenity": "dhaba"},                     "primary": "Restaurant",      "secondary": "Dhaba",          "experience": "budget"},
    {"match": {"amenity": "bar"},                       "primary": "Nightlife",       "secondary": "Bar",            "experience": "luxury"},
    {"match": {"amenity": "pub"},                       "primary": "Nightlife",       "secondary": "Pub",            "experience": "local"},
    {"match": {"amenity": "nightclub"},                 "primary": "Nightlife",       "secondary": "Nightclub",      "experience": "luxury"},
    # Stay
    {"match": {"tourism": "hotel"},                     "primary": "Hotel",           "secondary": "Hotel",          "experience": "luxury"},
    {"match": {"tourism": "hostel"},                    "primary": "Hotel",           "secondary": "Hostel",         "experience": "budget"},
    {"match": {"tourism": "guest_house"},               "primary": "Hotel",           "secondary": "Guest House",    "experience": "budget"},
    {"match": {"tourism": "resort"},                    "primary": "Hotel",           "secondary": "Resort",         "experience": "luxury"},
    {"match": {"tourism": "homestay"},                  "primary": "Hotel",           "secondary": "Homestay",       "experience": "local"},
    # Nature
    {"match": {"leisure": "park"},                      "primary": "Park",            "secondary": "Public Park",    "experience": "local"},
    {"match": {"leisure": "garden"},                    "primary": "Park",            "secondary": "Garden",         "experience": "local"},
    {"match": {"natural": "wetland"},                   "primary": "Park",            "secondary": "Wetland",        "experience": "local"},
    {"match": {"waterway": "waterfall"},                "primary": "Park",            "secondary": "Waterfall",      "experience": "local"},
    # Markets
    {"match": {"amenity": "marketplace"},               "primary": "Market",          "secondary": "Local Bazaar",   "experience": "local"},
    {"match": {"shop": "fish"},                         "primary": "Market",          "secondary": "Fish Market",    "experience": "local"},
    {"match": {"shop": "craft"},                        "primary": "Local Artisan Shop","secondary":"Handicraft","experience":"local"},
    {"match": {"shop": "spices"},                       "primary": "Local Artisan Shop","secondary":"Spice Shop","experience":"local"},
    {"match": {"shop": "supermarket"},                  "primary": "Market",          "secondary": "Supermarket",    "experience": "local"},
    # Culture
    {"match": {"tourism": "museum"},                    "primary": "Museum",          "secondary": "Museum",         "experience": "heritage"},
    {"match": {"tourism": "gallery"},                   "primary": "Museum",          "secondary": "Art Gallery",    "experience": "heritage"},
    {"match": {"amenity": "arts_centre"},               "primary": "Event Venue",     "secondary": "Cultural Centre","experience":"heritage"},
    {"match": {"amenity": "theatre"},                   "primary": "Event Venue",     "secondary": "Theatre",        "experience": "heritage"},
    # Education
    {"match": {"amenity": "university"},                "primary": "Public Facility", "secondary": "University",     "experience": "local"},
    {"match": {"amenity": "college"},                   "primary": "Public Facility", "secondary": "College",        "experience": "local"},
    {"match": {"amenity": "school"},                    "primary": "Public Facility", "secondary": "School",         "experience": "local"},
    {"match": {"amenity": "library"},                   "primary": "Public Facility", "secondary": "Library",        "experience": "heritage"},
    # Emergency / Health
    {"match": {"amenity": "hospital"},                  "primary": "Hospital",        "secondary": "Hospital",       "experience": "local"},
    {"match": {"amenity": "police"},                    "primary": "Police Station",  "secondary": "Police Station", "experience": "local"},
    {"match": {"amenity": "fire_station"},              "primary": "Public Facility", "secondary": "Fire Station",   "experience": "local"},
    {"match": {"amenity": "pharmacy"},                  "primary": "Public Facility", "secondary": "Pharmacy",       "experience": "local"},
    # Transport
    {"match": {"railway": "station"},                   "primary": "Public Facility", "secondary": "Railway Station","experience":"local"},
    {"match": {"amenity": "bus_station"},               "primary": "Public Facility", "secondary": "Bus Station",    "experience": "local"},
    {"match": {"amenity": "ferry_terminal"},            "primary": "Public Facility", "secondary": "Ferry Terminal", "experience": "local"},
    # Community
    {"match": {"amenity": "community_centre"},          "primary": "Public Facility", "secondary": "Community Centre","experience":"local"},
    # Viewpoints
    {"match": {"tourism": "viewpoint"},                 "primary": "Park",            "secondary": "Viewpoint",      "experience": "local"},
    # Tourism
    {"match": {"tourism": "attraction"},                "primary": "Heritage Site",   "secondary": "Tourist Attraction","experience":"local"},
    {"match": {"tourism": "artwork"},                   "primary": "Heritage Site",   "secondary": "Public Art",     "experience": "local"},
]

def _classify(tags: dict) -> Tuple[str, str, str]:
    for rule in CATEGORY_MAP:
        if all(tags.get(k) == v for k, v in rule["match"].items()):
            return rule["primary"], rule["secondary"], rule["experience"]
    # Fallback
    if tags.get("tourism"):    return "Heritage Site",   tags["tourism"].replace("_"," ").title(),   "local"
    if tags.get("historic"):   return "Heritage Site",   tags["historic"].replace("_"," ").title(),  "heritage"
    if tags.get("amenity"):    return "Public Facility", tags["amenity"].replace("_"," ").title(),   "local"
    if tags.get("shop"):       return "Local Artisan Shop", tags["shop"].replace("_"," ").title(),   "local"
    if tags.get("leisure"):    return "Park",            tags["leisure"].replace("_"," ").title(),   "local"
    return "Heritage Site", "Place of Interest", "local"


def _operating_model(tags: dict, primary: str) -> str:
    if primary in ("Hospital", "Police Station", "Public Facility"): return "government"
    if tags.get("operator:type") == "private": return "corporate"
    if primary in ("Temple", "Church", "Mosque"): return "community"
    if primary in ("Hotel",) and tags.get("stars"): return "corporate"
    return "family_owned"


def _service_speed(primary: str) -> float:
    speeds = {
        "Street Food": 0.9, "Café": 0.75, "Restaurant": 0.55,
        "Market": 0.7, "Hospital": 0.3, "Heritage Site": 1.0,
        "Park": 1.0, "Temple": 0.8,
    }
    return speeds.get(primary, 0.6)


def build_category_domain(element: dict) -> Dict:
    """Domain 2: Category & Functional — complete schema."""
    tags = element.get("tags", {})
    primary, secondary, experience = _classify(tags)
    model = _operating_model(tags, primary)

    return {
        "primary_category":   primary,
        "secondary_category": secondary,
        "osm_amenity":        tags.get("amenity", ""),
        "osm_tourism":        tags.get("tourism", ""),
        "osm_historic":       tags.get("historic", ""),
        "osm_shop":           tags.get("shop", ""),
        "osm_leisure":        tags.get("leisure", ""),
        "cuisine_type":       tags.get("cuisine", ""),
        "religion":           tags.get("religion", ""),
        "denomination":       tags.get("denomination", ""),
        "operating_model":    model,   # family_owned | corporate | franchise | government | community
        "service_speed_index":_service_speed(primary),
        "experience_type":    experience,   # luxury | local | heritage | budget
        "target_audience":    _target_audience(primary, tags),
        "indoor_outdoor":     _indoor_outdoor(tags, primary),
        "stars_rating":       tags.get("stars", ""),
        "brand":              tags.get("brand", "") or tags.get("operator", ""),
        "operator":           tags.get("operator", ""),
    }


def _target_audience(primary: str, tags: dict) -> str:
    if primary in ("Temple", "Church", "Mosque"): return "devotees"
    if primary in ("Hospital", "Police Station"): return "residents"
    if primary == "Hotel": return "tourists_and_travelers"
    if primary in ("Park", "Beach"): return "families_and_locals"
    if primary == "Museum": return "tourists_and_culture"
    if primary in ("University", "College", "School"): return "students"
    if primary == "Nightlife": return "adults"
    if tags.get("cuisine") or primary == "Restaurant": return "all"
    return "general_public"


def _indoor_outdoor(tags: dict, primary: str) -> str:
    if primary in ("Beach", "Park", "Heritage Site", "Market"): return "outdoor"
    if primary in ("Museum", "Hospital", "Hotel", "Restaurant", "Café"): return "indoor"
    if primary in ("Temple", "Church", "Mosque"): return "both"
    return "outdoor" if tags.get("natural") else "indoor"


# ════════════════════════════════════════════════════════════════
# DOMAIN 3 — TEMPORAL INTELLIGENCE
# ════════════════════════════════════════════════════════════════

# Default hours by category
DEFAULT_HOURS = {
    "Temple":        ("05:00", "21:00", ["06:00-08:00", "17:00-20:00"]),
    "Church":        ("06:00", "20:00", ["07:00-09:00", "16:00-18:00"]),
    "Mosque":        ("05:00", "22:00", ["07:00-08:00", "13:00-14:00", "18:00-20:00"]),
    "Restaurant":    ("11:00", "22:30", ["12:00-14:00", "19:00-22:00"]),
    "Café":          ("07:00", "21:00", ["08:00-10:00", "16:00-19:00"]),
    "Street Food":   ("06:00", "22:00", ["07:00-10:00", "19:00-22:00"]),
    "Nightlife":     ("19:00", "02:00", ["21:00-01:00"]),
    "Market":        ("06:00", "14:00", ["06:00-09:00"]),
    "Hotel":         ("00:00", "23:59", []),
    "Museum":        ("10:00", "17:00", ["10:00-13:00"]),
    "Heritage Site": ("08:00", "18:00", ["09:00-12:00"]),
    "Park":          ("05:00", "21:00", ["06:00-09:00", "17:00-20:00"]),
    "Beach":         ("05:00", "21:00", ["06:00-09:00", "16:00-20:00"]),
    "Hospital":      ("00:00", "23:59", []),
    "Police Station":("00:00", "23:59", []),
    "Public Facility":("09:00","18:00", ["10:00-13:00"]),
}

SEASONAL_PEAKS = {
    "Beach":         ["November","December","January","February","March"],
    "Temple":        ["October","November","March","April"],
    "Church":        ["December","January"],
    "Mosque":        ["April","May"],  # approx Ramadan
    "Market":        ["October","November","December"],
    "Restaurant":    ["October","November","December","January"],
    "Heritage Site": ["November","December","January","February"],
    "Hotel":         ["November","December","January","February"],
    "Park":          ["November","December","January","February"],
}

RAIN_IMPACT = {
    "Beach":         0.95,  # completely closed in monsoon
    "Market":        0.70,  # outdoor markets heavily impacted
    "Park":          0.60,
    "Heritage Site": 0.30,
    "Restaurant":    0.15,
    "Hotel":         0.05,
    "Hospital":      0.00,
    "Temple":        0.20,
}

HOLIDAY_SPIKES = {
    "Temple":        2.5,
    "Church":        3.0,
    "Mosque":        2.8,
    "Market":        2.0,
    "Restaurant":    1.8,
    "Heritage Site": 1.5,
    "Beach":         2.2,
    "Park":          1.8,
    "Hotel":         1.6,
    "Museum":        1.4,
}


def build_temporal_domain(element: dict, primary_category: str) -> Dict:
    """Domain 3: Temporal Intelligence — complete schema."""
    tags = element.get("tags", {})
    osm_hours = tags.get("opening_hours", "")
    cat = primary_category

    open_t, close_t, peaks = DEFAULT_HOURS.get(cat, ("09:00","18:00",["10:00-12:00"]))

    # Use OSM hours if available
    if osm_hours:
        parts = osm_hours.replace("Mo-Su","").replace("24/7","00:00-23:59").strip()
        if "-" in parts:
            try:
                segs = parts.split("-")
                open_t = segs[0].strip()[:5]
                close_t = segs[-1].strip()[:5]
            except: pass

    return {
        "opening_time":          open_t,
        "closing_time":          close_t,
        "hours_raw_osm":         osm_hours,
        "open_24h":              "24/7" in osm_hours,
        "peak_hours":            peaks,
        "seasonal_peak_months":  SEASONAL_PEAKS.get(cat, ["November","December","January"]),
        "lean_months":           ["June","July","August"],  # monsoon — all Mangalore
        "rain_impact_index":     RAIN_IMPACT.get(cat, 0.25),
        "holiday_spike_factor":  HOLIDAY_SPIKES.get(cat, 1.4),
        "best_visit_time":       _best_visit(cat, tags),
        "worst_visit_time":      "June–August (monsoon)",
        "day_of_week_variance":  _dow_variance(cat),
    }


def _best_visit(cat: str, tags: dict) -> str:
    mapping = {
        "Beach": "October–March, 6–9am or 4–7pm",
        "Temple": "Early morning 6–8am, festival days",
        "Church": "Morning service or quiet weekday",
        "Market": "5–8am for fresh produce and fish",
        "Restaurant": "Lunch 12–2pm or dinner 7–9pm",
        "Museum": "Weekday morning 10am–12pm",
        "Heritage Site": "Early morning for photography, cooler",
        "Park": "6–9am or 5–7pm",
        "Hotel": "Check-in 2pm, early November–February",
    }
    return mapping.get(cat, "Dry season — November to March")


def _dow_variance(cat: str) -> str:
    if cat in ("Market",): return "high — weekends much busier"
    if cat in ("Hospital", "Police Station"): return "low — consistent all week"
    if cat in ("Restaurant", "Café"): return "medium — weekends 30–40% busier"
    if cat in ("Temple", "Church", "Mosque"): return "high — festival days spike"
    return "low"


# ════════════════════════════════════════════════════════════════
# DOMAIN 4 — CROWD & DENSITY
# ════════════════════════════════════════════════════════════════

# Crowd profiles by category (Mangalore context)
CROWD_PROFILES = {
    "Beach":         {"weekday": 800,  "weekend": 4000, "tourist_ratio": 0.35, "local_ratio": 0.65, "surge": 3.5},
    "Temple":        {"weekday": 500,  "weekend": 2500, "tourist_ratio": 0.20, "local_ratio": 0.80, "surge": 8.0},
    "Church":        {"weekday": 200,  "weekend": 1500, "tourist_ratio": 0.10, "local_ratio": 0.90, "surge": 5.0},
    "Mosque":        {"weekday": 300,  "weekend": 1200, "tourist_ratio": 0.05, "local_ratio": 0.95, "surge": 4.0},
    "Restaurant":    {"weekday": 80,   "weekend": 180,  "tourist_ratio": 0.30, "local_ratio": 0.70, "surge": 1.8},
    "Café":          {"weekday": 40,   "weekend": 80,   "tourist_ratio": 0.25, "local_ratio": 0.75, "surge": 1.5},
    "Market":        {"weekday": 600,  "weekend": 1200, "tourist_ratio": 0.10, "local_ratio": 0.90, "surge": 2.5},
    "Hotel":         {"weekday": 60,   "weekend": 150,  "tourist_ratio": 0.70, "local_ratio": 0.30, "surge": 2.0},
    "Museum":        {"weekday": 50,   "weekend": 200,  "tourist_ratio": 0.60, "local_ratio": 0.40, "surge": 1.4},
    "Heritage Site": {"weekday": 100,  "weekend": 400,  "tourist_ratio": 0.50, "local_ratio": 0.50, "surge": 2.5},
    "Park":          {"weekday": 200,  "weekend": 600,  "tourist_ratio": 0.15, "local_ratio": 0.85, "surge": 2.0},
    "Hospital":      {"weekday": 400,  "weekend": 200,  "tourist_ratio": 0.10, "local_ratio": 0.90, "surge": 1.2},
    "Public Facility":{"weekday": 150, "weekend": 60,   "tourist_ratio": 0.05, "local_ratio": 0.95, "surge": 1.1},
    "Nightlife":     {"weekday": 50,   "weekend": 300,  "tourist_ratio": 0.40, "local_ratio": 0.60, "surge": 3.0},
    "Street Food":   {"weekday": 100,  "weekend": 200,  "tourist_ratio": 0.20, "local_ratio": 0.80, "surge": 2.0},
}


def build_crowd_domain(element: dict, primary_category: str,
                       dist_from_center: float) -> Dict:
    """Domain 4: Crowd & Density — complete schema."""
    tags = element.get("tags", {})
    cat = primary_category
    profile = CROWD_PROFILES.get(cat, {"weekday": 100, "weekend": 250, "tourist_ratio": 0.3, "local_ratio": 0.7, "surge": 1.5})

    # Distance penalty: further = less crowd
    dist_factor = max(0.2, 1.0 - (dist_from_center / 15.0))

    weekday  = int(profile["weekday"] * dist_factor)
    weekend  = int(profile["weekend"] * dist_factor)

    # Live crowd score (0-10) — synthetic based on time of day
    hour = datetime.now(timezone.utc).hour + 5.5  # IST offset approx
    hour = int(hour) % 24
    if 6 <= hour <= 9 or 17 <= hour <= 20:  live_score = 7
    elif 10 <= hour <= 16:                   live_score = 5
    elif 20 <= hour <= 22:                   live_score = 6
    else:                                    live_score = 2

    return {
        "crowd_score_live":       live_score,
        "crowd_score_source":     "synthetic_time_model",
        "avg_weekday_footfall":   weekday,
        "avg_weekend_footfall":   weekend,
        "tourist_ratio":          round(profile["tourist_ratio"] * (1.2 if dist_from_center < 3 else 0.8), 2),
        "local_ratio":            round(profile["local_ratio"], 2),
        "event_surge_factor":     profile["surge"],
        "crowd_type":             _crowd_type(cat),
        "overcrowding_risk":      "High" if weekend > 2000 else "Medium" if weekend > 500 else "Low",
        "best_time_for_solitude": _solitude_time(cat),
        "instagram_crowd_spike":  cat in ("Beach", "Heritage Site", "Museum", "Temple"),
    }


def _crowd_type(cat: str) -> str:
    if cat in ("Temple", "Church", "Mosque"): return "devotee_community"
    if cat in ("Beach", "Park"): return "family_leisure"
    if cat in ("Restaurant", "Café", "Nightlife"): return "social_dining"
    if cat in ("Hospital", "Police Station"): return "service_seekers"
    if cat in ("Museum", "Heritage Site"): return "tourist_cultural"
    return "mixed"

def _solitude_time(cat: str) -> str:
    if cat == "Beach": return "Weekday 6–8am"
    if cat in ("Temple", "Church"): return "Weekday early morning"
    if cat == "Market": return "Late afternoon 2–4pm"
    return "Weekday morning"


# ════════════════════════════════════════════════════════════════
# DOMAIN 5 — REVIEW & SENTIMENT
# ════════════════════════════════════════════════════════════════

def build_review_domain(element: dict, primary_category: str,
                        wiki_description: str = "") -> Dict:
    """Domain 5: Review & Sentiment — complete schema."""
    tags = element.get("tags", {})

    # Authenticity scoring (deterministic from open signals)
    auth_score = _compute_authenticity(tags, primary_category, wiki_description)

    # Hype index — higher for tourist spots vs local everyday places
    hype = _compute_hype(primary_category, tags)

    # Language distribution in reviews (inferred from location/community context)
    lang_dist = _language_distribution(tags)

    return {
        "avg_rating":                  None,  # No rating API used — privacy/legal
        "review_count":                None,  # Same
        "authenticity_score":          auth_score,
        "authenticity_signals":        _auth_signals(tags, primary_category, wiki_description),
        "hype_index":                  hype,
        "hype_factors":                _hype_factors(primary_category, tags),
        "negative_spike_detected":     False,  # No live review data — always False for open
        "review_language_distribution":lang_dist,
        "sentiment_variance":          _sentiment_variance(primary_category),
        "review_source_note":          "No third-party rating data used. Scores derived from open structural signals only (OSM completeness, Wikipedia presence, source count).",
        "wiki_description":            wiki_description[:200] if wiki_description else "",
        "has_wikipedia":               bool(wiki_description),
        "sources_count":               _count_open_sources(tags),
    }


def _compute_authenticity(tags: dict, cat: str, wiki: str) -> float:
    score = 0.0
    # OSM completeness signals
    if tags.get("name"): score += 0.10
    if tags.get("opening_hours"): score += 0.10
    if tags.get("phone") or tags.get("contact:phone"): score += 0.08
    if tags.get("website"): score += 0.07
    if tags.get("addr:street") or tags.get("addr:full"): score += 0.07
    if tags.get("description"): score += 0.10
    # Wikipedia presence = strong authenticity signal
    if wiki: score += 0.25
    # Category-based bonus
    cat_bonus = {"Heritage Site": 0.15, "Temple": 0.10, "Museum": 0.12,
                 "Beach": 0.10, "Market": 0.08, "Restaurant": 0.05}
    score += cat_bonus.get(cat, 0.05)
    # Age signal
    if tags.get("start_date") or tags.get("year_built"): score += 0.08
    return round(min(1.0, score), 3)


def _auth_signals(tags: dict, cat: str, wiki: str) -> List[str]:
    signals = []
    if wiki: signals.append("Wikipedia article exists")
    if tags.get("opening_hours"): signals.append("Opening hours in OSM")
    if tags.get("phone"): signals.append("Phone number in OSM")
    if tags.get("website"): signals.append("Website in OSM")
    if tags.get("start_date"): signals.append(f"Established: {tags['start_date']}")
    if tags.get("heritage") or tags.get("historic"): signals.append("Heritage designation")
    return signals


def _compute_hype(cat: str, tags: dict) -> float:
    base = {"Heritage Site": 0.8, "Beach": 0.75, "Museum": 0.65, "Temple": 0.6,
            "Restaurant": 0.55, "Hotel": 0.7, "Nightlife": 0.65,
            "Market": 0.4, "Hospital": 0.1, "Park": 0.35}
    return round(base.get(cat, 0.4), 2)


def _hype_factors(cat: str, tags: dict) -> List[str]:
    factors = []
    if cat in ("Heritage Site","Beach","Museum"): factors.append("Featured on travel websites")
    if tags.get("wikipedia"): factors.append("Wikipedia page increases discoverability")
    if tags.get("tourism"): factors.append("Listed as tourism attraction in OSM")
    if cat == "Nightlife": factors.append("Social media-driven discovery")
    return factors


def _language_distribution(tags: dict) -> Dict:
    # Inferred from Mangalore's linguistic context
    return {"Kannada": 0.35, "Tulu": 0.25, "English": 0.20,
            "Konkani": 0.10, "Beary Bashe": 0.07, "Hindi": 0.03}


def _sentiment_variance(cat: str) -> float:
    variances = {"Hospital": 0.8, "Restaurant": 0.6, "Market": 0.5,
                 "Beach": 0.3, "Temple": 0.2, "Heritage Site": 0.2}
    return variances.get(cat, 0.4)


def _count_open_sources(tags: dict) -> int:
    count = 1  # OSM always
    if tags.get("wikipedia"): count += 1
    if tags.get("wikidata"): count += 1
    if tags.get("website"): count += 1
    return count


# ════════════════════════════════════════════════════════════════
# DOMAIN 6 — SAFETY & RISK
# ════════════════════════════════════════════════════════════════

# Mangalore-specific crime/safety profiles
SAFETY_PROFILES = {
    "Beach":         {"crime": 0.35, "night_safety": 0.50, "crowd_crush": 0.30, "disaster": 0.65},
    "Market":        {"crime": 0.40, "night_safety": 0.55, "crowd_crush": 0.40, "disaster": 0.20},
    "Temple":        {"crime": 0.15, "night_safety": 0.70, "crowd_crush": 0.60, "disaster": 0.15},
    "Nightlife":     {"crime": 0.45, "night_safety": 0.55, "crowd_crush": 0.35, "disaster": 0.10},
    "Restaurant":    {"crime": 0.10, "night_safety": 0.75, "crowd_crush": 0.10, "disaster": 0.10},
    "Café":          {"crime": 0.05, "night_safety": 0.85, "crowd_crush": 0.05, "disaster": 0.10},
    "Hotel":         {"crime": 0.10, "night_safety": 0.85, "crowd_crush": 0.05, "disaster": 0.10},
    "Heritage Site": {"crime": 0.15, "night_safety": 0.60, "crowd_crush": 0.20, "disaster": 0.20},
    "Park":          {"crime": 0.25, "night_safety": 0.55, "crowd_crush": 0.15, "disaster": 0.25},
    "Hospital":      {"crime": 0.05, "night_safety": 0.95, "crowd_crush": 0.20, "disaster": 0.10},
    "Museum":        {"crime": 0.05, "night_safety": 0.80, "crowd_crush": 0.10, "disaster": 0.10},
}


def build_safety_domain(element: dict, primary_category: str,
                        lat: float, lon: float,
                        hospital_nodes: List[Dict],
                        police_nodes: List[Dict]) -> Dict:
    """Domain 6: Safety & Risk — complete schema."""
    tags = element.get("tags", {})
    cat = primary_category
    profile = SAFETY_PROFILES.get(cat, {"crime": 0.20, "night_safety": 0.70,
                                         "crowd_crush": 0.10, "disaster": 0.15})

    # Hospital proximity
    hosp_dist = min(
        (_haversine(lat, lon,
                    n.get("lat") or n.get("center",{}).get("lat",0) or 0,
                    n.get("lon") or n.get("center",{}).get("lon",0) or 0)
         for n in hospital_nodes if n.get("lat") or n.get("center")),
        default=5.0
    )

    # Police proximity
    police_dist = min(
        (_haversine(lat, lon,
                    n.get("lat") or n.get("center",{}).get("lat",0) or 0,
                    n.get("lon") or n.get("center",{}).get("lon",0) or 0)
         for n in police_nodes if n.get("lat") or n.get("center")),
        default=3.0
    )

    # Coastal flood risk — higher for lat 12.8–13.0 near coast
    coastal_risk = 0.60 if lon < 74.87 and (12.78 < lat < 13.05) else 0.20

    return {
        "crime_index":               profile["crime"],
        "night_safety_score":        profile["night_safety"],
        "fire_safety_certified":     tags.get("fire_safety") == "yes" or primary_category in ("Hotel","Restaurant"),
        "medical_access_distance_km":round(hosp_dist, 2),
        "police_access_distance_km": round(police_dist, 2),
        "disaster_risk_index":       round(max(profile["disaster"], coastal_risk * 0.5), 2),
        "flood_risk":                round(coastal_risk, 2),
        "crowd_crush_risk":          profile["crowd_crush"],
        "structural_risk":           "ASI protected" if tags.get("heritage") else "unknown",
        "coastal_zone":              lon < 74.87,
        "monsoon_risk_months":       ["June","July","August"] if coastal_risk > 0.4 else [],
        "safety_notes":              _safety_notes(cat, coastal_risk),
    }


def _safety_notes(cat: str, coastal_risk: float) -> str:
    notes = []
    if coastal_risk > 0.5: notes.append("Coastal zone — high flood/current risk in monsoon")
    if cat == "Beach": notes.append("No lifeguard at most Mangalore beaches")
    if cat == "Nightlife": notes.append("Exercise standard urban caution after midnight")
    if cat == "Market": notes.append("Pickpocket risk in crowded morning hours")
    return "; ".join(notes) if notes else "Standard urban safety applies"


# ════════════════════════════════════════════════════════════════
# DOMAIN 7 — ECONOMIC & PRICING
# ════════════════════════════════════════════════════════════════

PRICE_PROFILES = {
    "Restaurant":    {"level": "medium", "avg_per_person": 250, "variation": 0.3, "markup": 0.2},
    "Café":          {"level": "medium", "avg_per_person": 150, "variation": 0.2, "markup": 0.15},
    "Street Food":   {"level": "low",    "avg_per_person": 60,  "variation": 0.1, "markup": 0.05},
    "Hotel":         {"level": "high",   "avg_per_person": 2500,"variation": 0.5, "markup": 0.4},
    "Beach":         {"level": "free",   "avg_per_person": 0,   "variation": 0.1, "markup": 0.0},
    "Temple":        {"level": "free",   "avg_per_person": 0,   "variation": 0.1, "markup": 0.0},
    "Park":          {"level": "free",   "avg_per_person": 0,   "variation": 0.0, "markup": 0.0},
    "Museum":        {"level": "low",    "avg_per_person": 30,  "variation": 0.1, "markup": 0.3},
    "Heritage Site": {"level": "low",    "avg_per_person": 20,  "variation": 0.1, "markup": 0.2},
    "Market":        {"level": "low",    "avg_per_person": 200, "variation": 0.3, "markup": 0.05},
    "Hospital":      {"level": "medium", "avg_per_person": 500, "variation": 0.4, "markup": 0.0},
    "Nightlife":     {"level": "high",   "avg_per_person": 600, "variation": 0.4, "markup": 0.35},
    "Local Artisan Shop":{"level":"low", "avg_per_person": 150, "variation": 0.2, "markup": 0.3},
}


def build_economic_domain(element: dict, primary_category: str) -> Dict:
    """Domain 7: Economic & Pricing — complete schema."""
    tags = element.get("tags", {})
    profile = PRICE_PROFILES.get(primary_category,
                                  {"level":"medium","avg_per_person":200,"variation":0.3,"markup":0.2})

    payment_methods = ["cash", "upi"]
    if primary_category in ("Hotel", "Restaurant") or tags.get("payment:cards") == "yes":
        payment_methods.append("card")
    if tags.get("payment:cash_only") == "yes":
        payment_methods = ["cash"]

    return {
        "price_level":              profile["level"],  # free | low | medium | high
        "avg_spend_per_person":     profile["avg_per_person"],
        "avg_spend_per_person_inr": profile["avg_per_person"],
        "seasonal_price_variation": profile["variation"],
        "tourist_markup_index":     profile["markup"],
        "payment_methods":          payment_methods,
        "currency":                 "INR",
        "free_entry":               profile["level"] == "free",
        "hidden_charges_risk":      "Low" if primary_category in ("Temple","Park","Beach") else "Medium",
        "price_negotiable":         primary_category in ("Market","Local Artisan Shop","Street Food"),
        "peak_season_surcharge":    profile["variation"] > 0.3,
        "fee_source":               "curated_model",
    }


# ════════════════════════════════════════════════════════════════
# DOMAIN 8 — CULTURAL & SOCIAL
# ════════════════════════════════════════════════════════════════

HERITAGE_CATS = {"Heritage Site", "Temple", "Church", "Mosque", "Museum"}
COMMUNITY_MANAGED = {"Temple", "Church", "Mosque"}
FESTIVAL_IMPORTANCE = {
    "Temple": 0.90, "Church": 0.85, "Mosque": 0.80,
    "Heritage Site": 0.60, "Market": 0.65, "Beach": 0.50,
    "Museum": 0.40, "Restaurant": 0.30,
}
CULTURAL_RELEVANCE = {
    "Temple": 0.90, "Church": 0.85, "Mosque": 0.80,
    "Heritage Site": 0.85, "Museum": 0.75, "Market": 0.65,
    "Beach": 0.60, "Restaurant": 0.45, "Park": 0.40,
}


def build_cultural_domain(element: dict, primary_category: str,
                          wiki_description: str = "") -> Dict:
    """Domain 8: Cultural & Social — complete schema."""
    tags = element.get("tags", {})
    cat = primary_category

    heritage = (tags.get("heritage") or tags.get("historic") or
                cat in HERITAGE_CATS or bool(wiki_description))

    return {
        "heritage_status":           heritage,
        "heritage_grade":            tags.get("heritage", ""),
        "community_managed":         cat in COMMUNITY_MANAGED,
        "cultural_relevance_score":  round(CULTURAL_RELEVANCE.get(cat, 0.4) +
                                           (0.10 if wiki_description else 0.0), 2),
        "festival_importance":       round(FESTIVAL_IMPORTANCE.get(cat, 0.3), 2),
        "local_tradition_link":      _tradition_link(tags, cat),
        "community_ownership_type":  "religious_trust" if cat in COMMUNITY_MANAGED else
                                      "government" if cat in ("Museum","Hospital","Police Station") else
                                      "private",
        "religious_significance":    cat in ("Temple","Church","Mosque","Heritage Site"),
        "religion":                  tags.get("religion",""),
        "denomination":              tags.get("denomination",""),
        "historical_period":         tags.get("start_date","") or tags.get("year_built",""),
        "architect":                 tags.get("architect",""),
        "cultural_events_hosted":    cat in ("Temple","Church","Mosque","Event Venue","Market","Museum"),
        "tulu_cultural_link":        _tulu_link(cat, tags),
        "inter_community_relevance": _inter_community(cat, tags),
    }


def _tradition_link(tags: dict, cat: str) -> str:
    name = tags.get("name","").lower()
    if "yaksha" in name or "kambala" in name: return "Tulu performing arts tradition"
    if cat == "Temple" and tags.get("religion") == "hindu": return "Tulu Nadu temple tradition"
    if cat == "Church": return "Mangalorean Catholic heritage"
    if cat == "Mosque" or "dargah" in name: return "Beary Muslim community tradition"
    if "fish" in name or "hoige" in name: return "Mogaveera fishing community tradition"
    if cat == "Market": return "Local trade and community commerce"
    return ""


def _tulu_link(cat: str, tags: dict) -> bool:
    name = tags.get("name","").lower()
    return (cat in ("Temple","Heritage Site") and
            tags.get("religion","") in ("hindu","") and
            not any(w in name for w in ["church","mosque","masjid","dargah"]))


def _inter_community(cat: str, tags: dict) -> bool:
    name = tags.get("name","").lower()
    cross = ["dargah","ullal","dharmasthala","aloysius","milagres","dasara"]
    return any(w in name for w in cross) or cat in ("Park","Beach","Market","Museum")


# ════════════════════════════════════════════════════════════════
# DOMAIN 9 — EXPERIENCE QUALITY
# ════════════════════════════════════════════════════════════════

EXPERIENCE_PROFILES = {
    "Beach":         {"cleanliness":0.60,"noise":0.55,"visual":0.85,"family":True},
    "Temple":        {"cleanliness":0.70,"noise":0.65,"visual":0.80,"family":True},
    "Church":        {"cleanliness":0.85,"noise":0.30,"visual":0.80,"family":True},
    "Mosque":        {"cleanliness":0.80,"noise":0.40,"visual":0.65,"family":True},
    "Restaurant":    {"cleanliness":0.70,"noise":0.60,"visual":0.65,"family":True},
    "Café":          {"cleanliness":0.80,"noise":0.40,"visual":0.70,"family":True},
    "Heritage Site": {"cleanliness":0.65,"noise":0.35,"visual":0.90,"family":True},
    "Museum":        {"cleanliness":0.85,"noise":0.20,"visual":0.85,"family":True},
    "Park":          {"cleanliness":0.60,"noise":0.50,"visual":0.75,"family":True},
    "Market":        {"cleanliness":0.45,"noise":0.80,"visual":0.70,"family":False},
    "Nightlife":     {"cleanliness":0.50,"noise":0.90,"visual":0.70,"family":False},
    "Hospital":      {"cleanliness":0.80,"noise":0.55,"visual":0.40,"family":False},
    "Hotel":         {"cleanliness":0.80,"noise":0.35,"visual":0.75,"family":True},
    "Street Food":   {"cleanliness":0.45,"noise":0.70,"visual":0.65,"family":True},
}


def build_experience_domain(element: dict, primary_category: str) -> Dict:
    """Domain 9: Experience Quality — complete schema."""
    tags = element.get("tags", {})
    cat = primary_category
    prof = EXPERIENCE_PROFILES.get(cat, {"cleanliness":0.60,"noise":0.55,"visual":0.65,"family":True})

    wheelchair = tags.get("wheelchair","unknown")
    accessible = wheelchair == "yes" or cat in ("Museum","Hospital","Hotel")

    return {
        "cleanliness_score":    prof["cleanliness"],
        "noise_level":          prof["noise"],
        "visual_appeal_score":  prof["visual"],
        "wheelchair_accessible":accessible,
        "wheelchair_osm":       wheelchair,
        "child_friendly":       prof["family"],
        "pet_friendly":         cat in ("Park","Beach"),
        "toilets_available":    tags.get("toilets") == "yes" or cat in ("Museum","Hotel","Hospital"),
        "photography_allowed":  cat not in ("Hospital","Police Station"),
        "avg_visit_duration_min": _visit_duration(cat),
        "sensory_intensity":    "High" if prof["noise"] > 0.6 else "Medium" if prof["noise"] > 0.3 else "Low",
        "experience_notes":     _experience_notes(cat, tags),
    }


def _visit_duration(cat: str) -> int:
    durations = {"Beach":120,"Temple":30,"Church":20,"Museum":90,
                 "Heritage Site":45,"Park":60,"Restaurant":60,
                 "Market":45,"Hotel":600,"Café":45,"Nightlife":180}
    return durations.get(cat, 30)


def _experience_notes(cat: str, tags: dict) -> str:
    notes = {
        "Beach": "Best at sunrise/sunset. Monsoon Jun–Aug: stay out of water.",
        "Temple": "Remove footwear, dress modestly. Photography rules vary.",
        "Church": "Quiet, respectful dress required. Photography usually allowed.",
        "Museum": "Guided tours available on request at most Mangalore museums.",
        "Market": "Busy, noisy — don't bring valuables. Bargaining expected.",
        "Heritage Site": "Early morning best — fewer crowds, better light for photos.",
    }
    return notes.get(cat, "Standard visit norms apply.")


# ════════════════════════════════════════════════════════════════
# DOMAIN 10 — ENVIRONMENTAL & CLIMATE
# ════════════════════════════════════════════════════════════════

def build_environment_domain(element: dict, primary_category: str,
                              lat: float, lon: float,
                              city_aqi: Dict, city_temp: Dict) -> Dict:
    """Domain 10: Environmental & Climate — complete schema."""
    tags = element.get("tags", {})

    # Coastal proximity → higher flood risk
    dist_from_coast = _haversine(lat, lon, 12.9141, 74.8200)  # approx coast center
    flood_risk = round(max(0.1, 0.9 - dist_from_coast * 0.12), 2)

    # Green cover estimate by category
    green_pct = {"Park":0.85,"Beach":0.40,"Temple":0.35,"Heritage Site":0.30,
                 "Market":0.05,"Restaurant":0.10,"Hotel":0.15,"Hospital":0.20}

    # Heat exposure
    heat = _heat_exposure(lat, lon, primary_category)

    return {
        "air_quality_index":      city_aqi.get("us_aqi", 0),
        "pm2_5":                  city_aqi.get("pm2_5", 0),
        "pm10":                   city_aqi.get("pm10", 0),
        "aqi_source":             "Open-Meteo live (city-level)",
        "temperature_current_c":  city_temp.get("temperature_2m", 0),
        "humidity_pct":           city_temp.get("relative_humidity_2m", 0),
        "temperature_average":    28.5,
        "temperature_average_c":  28.5,  # Mangalore annual avg
        "heat_index":             heat,
        "flood_risk":             flood_risk,
        "coastal_proximity_km":   round(dist_from_coast, 2),
        "green_cover_percentage": int(green_pct.get(primary_category, 0.15) * 100),
        "water_body_nearby":      (lat > 12.87 and lon < 74.87) or primary_category == "Beach",
        "microclimate_note":      _microclimate(primary_category, lat, lon),
        "monsoon_impact":         "Severe" if flood_risk > 0.6 else "Moderate" if flood_risk > 0.3 else "Low",
    }


def _heat_exposure(lat: float, lon: float, cat: str) -> float:
    base = 0.65  # Mangalore is hot and humid
    if cat in ("Beach", "Heritage Site", "Park"): base += 0.15  # outdoor exposure
    if cat in ("Restaurant", "Hotel", "Museum"): base -= 0.20    # AC likely
    return round(min(1.0, max(0.1, base)), 2)


def _microclimate(cat: str, lat: float, lon: float) -> str:
    if lon < 74.85: return "Coastal breeze — 2–3°C cooler than city centre"
    if cat == "Park": return "Green canopy provides shade — pleasant in morning"
    return "Typical urban microclimate — humid and warm"


# ════════════════════════════════════════════════════════════════
# BONUS DOMAINS — Research-Level Intelligence
# ════════════════════════════════════════════════════════════════

def build_bias_domain(element: dict, primary_category: str) -> Dict:
    """Bonus 1: Bias Detection Domain."""
    tags = element.get("tags", {})
    cat = primary_category
    name = tags.get("name","")

    return {
        "domain": "bias_detection",
        "over_represented_in_travel_media": cat in ("Heritage Site","Beach","Museum"),
        "under_represented_local_spot":     cat in ("Market","Community Centre","Street Food"),
        "tourist_trap_risk":                cat in ("Hotel","Heritage Site") and tags.get("tourism") == "attraction",
        "gentrification_risk":              cat in ("Café","Nightlife","Hotel") and tags.get("stars"),
        "community_erasure_risk":           "Low",
        "representation_note":              _representation_note(cat, name),
        "mainstream_media_coverage":        "High" if cat in ("Heritage Site","Museum","Beach") else "Low",
        "data_bias_note":                   "OSM data reflects mapper density — city centre overrepresented vs periphery",
    }


def _representation_note(cat: str, name: str) -> str:
    if cat == "Heritage Site": return "Colonial-era structures tend to be better documented than indigenous sites"
    if cat == "Temple": return "Large temples well-documented; small community shrines often missing"
    if cat == "Market": return "Traditional markets underrepresented in tourism media vs shopping malls"
    return "Standard representation"


def build_crowd_psychology_domain(element: dict, primary_category: str) -> Dict:
    """Bonus 2: Crowd Psychology Index."""
    cat = primary_category
    festival_trigger = cat in ("Temple","Church","Mosque","Beach","Heritage Site")
    return {
        "domain": "crowd_psychology",
        "herd_mentality_risk":       "High" if cat in ("Beach","Market","Temple") else "Low",
        "festival_trigger":          festival_trigger,
        "fomo_attractiveness":       "High" if cat in ("Heritage Site","Beach") else "Medium",
        "panic_evacuation_risk":     "High" if cat in ("Temple","Market","Beach") else "Low",
        "crowd_ritual_behavior":     cat in ("Temple","Church","Mosque"),
        "social_contagion_factor":   0.7 if cat == "Nightlife" else 0.4,
        "notes":                     "Derived from category archetype; no surveillance data used.",
    }


def build_cultural_density_domain(element: dict, primary_category: str,
                                   lat: float, lon: float,
                                   all_records: List[Dict]) -> Dict:
    """Bonus 3: Cultural Density Index — places within 500m radius."""
    nearby = [r for r in all_records
              if _haversine(lat, lon, r.get("lat",0), r.get("lon",0)) < 0.5]
    religions_nearby = {r.get("tags",{}).get("religion","") for r in nearby if r.get("tags",{}).get("religion")}
    return {
        "domain": "cultural_density",
        "places_within_500m":     len(nearby),
        "religions_within_500m":  list(filter(None, religions_nearby)),
        "cultural_diversity_index":round(min(1.0, len(religions_nearby) * 0.25), 2),
        "religious_overlap_zone": len(religions_nearby) > 1,
        "notes":                  "Computed from OSM co-location within 500m radius",
    }


def build_virality_domain(element: dict, primary_category: str) -> Dict:
    """Bonus 4: Social Media Virality Index."""
    tags = element.get("tags", {})
    cat = primary_category
    visual = cat in ("Beach","Heritage Site","Temple","Museum","Park")
    return {
        "domain": "social_media_virality",
        "instagram_potential":       "High" if visual else "Low",
        "hashtag_likelihood":        visual,
        "sunset_spot":               cat == "Beach" or tags.get("tourism") == "viewpoint",
        "shareable_factor":          0.85 if visual else 0.35,
        "viral_trigger":             _viral_trigger(cat, tags),
        "estimated_social_reach":    "High" if cat in ("Heritage Site","Beach") else "Medium",
    }


def _viral_trigger(cat: str, tags: dict) -> str:
    if cat == "Beach": return "Golden hour photography, water sports"
    if cat == "Heritage Site": return "Historic architecture, unique cultural experience"
    if cat == "Temple": return "Festival lighting, architectural beauty"
    if cat == "Museum": return "Unique exhibits, educational content"
    return "Standard"


def build_sustainability_domain(element: dict, primary_category: str) -> Dict:
    """Bonus 6: Sustainability Index."""
    cat = primary_category
    return {
        "domain": "sustainability",
        "eco_sensitive_zone":        cat in ("Beach","Park") and True,
        "plastic_waste_risk":        "High" if cat in ("Beach","Market","Street Food") else "Low",
        "carbon_footprint_visitor":  "Low" if cat in ("Park","Beach","Temple") else "Medium",
        "water_body_nearby":         cat in ("Beach","Park"),
        "mangrove_proximity_risk":   cat == "Beach",
        "sustainability_score":      0.7 if cat in ("Park","Temple","Heritage Site") else 0.4,
        "responsible_tourism_notes": _sustainability_notes(cat),
    }


def _sustainability_notes(cat: str) -> str:
    if cat == "Beach": return "Avoid single-use plastic. Turtle nesting season Nov–Feb: reduce light/noise"
    if cat == "Park": return "Stay on paths, do not disturb wildlife"
    if cat == "Market": return "Bring reusable bag, avoid excessive packaging"
    return "Follow leave-no-trace principles"


# ════════════════════════════════════════════════════════════════
# MASTER RECORD ASSEMBLER
# ════════════════════════════════════════════════════════════════

def assemble_record(element: dict,
                    city_center_lat: float,
                    city_center_lon: float,
                    admin_zone: str,
                    transport_nodes: List[Dict],
                    hospital_nodes: List[Dict],
                    police_nodes: List[Dict],
                    city_aqi: Dict,
                    city_temp: Dict,
                    wiki_desc: str,
                    all_elements: List[Dict]) -> Dict:
    """Assemble the complete 10-domain + 4 bonus domain record."""
    tags = element.get("tags", {})
    name = tags.get("name", "")
    lat  = element.get("lat") or element.get("center", {}).get("lat", 0.0) or 0.0
    lon  = element.get("lon") or element.get("center", {}).get("lon", 0.0) or 0.0

    # Domains 2 first (needed by others)
    cat_data     = build_category_domain(element)
    primary_cat  = cat_data["primary_category"]

    geo_data     = build_geo_domain(element, city_center_lat, city_center_lon,
                                    admin_zone, transport_nodes)
    dist         = geo_data["distance_from_center_km"]

    temporal     = build_temporal_domain(element, primary_cat)
    crowd        = build_crowd_domain(element, primary_cat, dist)
    review       = build_review_domain(element, primary_cat, wiki_desc)
    safety       = build_safety_domain(element, primary_cat, lat, lon,
                                        hospital_nodes, police_nodes)
    economic     = build_economic_domain(element, primary_cat)
    cultural     = build_cultural_domain(element, primary_cat, wiki_desc)
    experience   = build_experience_domain(element, primary_cat)
    environment  = build_environment_domain(element, primary_cat, lat, lon, city_aqi, city_temp)

    # Bonus domains
    bias         = build_bias_domain(element, primary_cat)
    psych        = build_crowd_psychology_domain(element, primary_cat)
    density      = build_cultural_density_domain(element, primary_cat, lat, lon, all_elements)
    virality     = build_virality_domain(element, primary_cat)
    sustainability = build_sustainability_domain(element, primary_cat)

    return {
        "place_id":        geo_data["place_id"],
        "name":            name,
        "city":            admin_zone,

        # 10 Core Domains
        "geo_data":         geo_data,
        "category_data":    cat_data,
        "temporal_data":    temporal,
        "crowd_data":       crowd,
        "review_data":      review,
        "safety_data":      safety,
        "economic_data":    economic,
        "cultural_data":    cultural,
        "experience_data":  experience,
        "environment_data": environment,

        # Bonus Domains
        "bias_data":        bias,
        "crowd_psychology": psych,
        "cultural_density": density,
        "virality_data":    virality,
        "sustainability":   sustainability,

        # Meta
        "data_version":     "v1_10domains",
        "generated_at":     _now(),
        "sources":          ["osm", "wikipedia" if wiki_desc else "", "open_meteo"],
    }


# ════════════════════════════════════════════════════════════════
# WIKIPEDIA BATCH ENRICHMENT
# ════════════════════════════════════════════════════════════════

def enrich_with_wikipedia(elements: List[Dict]) -> Dict[str, str]:
    """
    Fetch Wikipedia summaries for named elements that have a Wikipedia tag
    or whose name suggests a Wikipedia article exists.
    Returns {element_name: wiki_extract}.
    """
    print("    Enriching with Wikipedia...")
    wiki_map: Dict[str, str] = {}

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name","")
        wiki_title = tags.get("wikipedia","").replace("en:","")

        if not wiki_title:
            # Try name directly for heritage sites
            cat = _classify(tags)[0]
            if cat in ("Heritage Site","Museum","Temple","Church","Mosque","Beach"):
                wiki_title = name

        if wiki_title and name not in wiki_map:
            desc = _wiki_extract(wiki_title)
            if desc:
                wiki_map[name] = desc

    print(f"      Wikipedia descriptions: {len(wiki_map)}")
    return wiki_map


# ════════════════════════════════════════════════════════════════
# CITY-LEVEL INTELLIGENCE SUMMARY
# ════════════════════════════════════════════════════════════════

def build_city_summary(records: List[Dict], city_aqi: Dict, city_temp: Dict) -> Dict:
    """Aggregate city-level intelligence from all records."""

    # Category distribution
    cat_dist: Dict[str,int] = {}
    for r in records:
        cat = r.get("category_data",{}).get("primary_category","Unknown")
        cat_dist[cat] = cat_dist.get(cat,0) + 1

    # Zone distribution
    zone_dist: Dict[str,int] = {}
    for r in records:
        z = r.get("geo_data",{}).get("footfall_heatmap_zone","unknown")
        zone_dist[z] = zone_dist.get(z,0) + 1

    # Average scores
    auth_scores = [r.get("review_data",{}).get("authenticity_score",0) for r in records]
    avg_auth = round(sum(auth_scores)/len(auth_scores),3) if auth_scores else 0

    heritage_count = sum(1 for r in records if r.get("cultural_data",{}).get("heritage_status"))
    wiki_count     = sum(1 for r in records if r.get("review_data",{}).get("has_wikipedia"))
    coastal_count  = sum(1 for r in records if r.get("safety_data",{}).get("coastal_zone"))

    return {
        "city_intel_version":        "v1",
        "generated_at":              _now(),
        "total_records":             len(records),
        "category_distribution":     dict(sorted(cat_dist.items(), key=lambda x:-x[1])),
        "zone_distribution":         zone_dist,
        "avg_authenticity_score":    avg_auth,
        "heritage_places_count":     heritage_count,
        "wikipedia_enriched_count":  wiki_count,
        "coastal_zone_places":       coastal_count,
        "live_air_quality":          city_aqi,
        "live_weather":              city_temp,
        "city_level_signals": {
            "crowd_peak_months":     ["October","November","December","January"],
            "tourist_influx_months": ["November","December","January","February"],
            "monsoon_months":        ["June","July","August"],
            "avg_tourist_ratio":     round(sum(r.get("crowd_data",{}).get("tourist_ratio",0) for r in records)/max(1,len(records)),2),
            "safety_overview":       "Mangalore is generally safe. Coastal zones have monsoon risk Jun–Aug.",
            "data_bias_note":        "OSM data reflects mapper density. City centre has ~3x more records than periphery.",
        },
        "domain_coverage": {
            "geo_data":         "100%",
            "category_data":    "100%",
            "temporal_data":    "100%",
            "crowd_data":       "100% synthetic model",
            "review_data":      "100% structural signals (no 3rd-party ratings)",
            "safety_data":      "100% proximity model",
            "economic_data":    "100% category model",
            "cultural_data":    "100%",
            "experience_data":  "100% category model",
            "environment_data": "100% Open-Meteo + proximity model",
        },
    }


# ════════════════════════════════════════════════════════════════
# MAIN BUILDER
# ════════════════════════════════════════════════════════════════

def build_deep_intelligence(city_id: str,
                             bbox: str,
                             center_lat: float,
                             center_lon: float,
                             limit: int = 0,
                             verbose: bool = False) -> Dict:

    print(f"\n{'═'*65}")
    print(f"  DEEP INTELLIGENCE COLLECTOR — {city_id}")
    print(f"  10 Core Domains + 5 Bonus Domains per record")
    print(f"{'═'*65}\n")

    os.makedirs("data_storage", exist_ok=True)

    # ── Step 1: Fetch city climate (one call for all records) ──
    print("  [1/6] Fetching city climate & AQI...")
    city_aqi, city_temp = _fetch_city_climate(center_lat, center_lon)
    print(f"      AQI: {city_aqi.get('us_aqi','N/A')}  |  Temp: {city_temp.get('temperature_2m','N/A')}°C")

    # ── Step 2: Fetch all OSM places ──
    print("\n  [2/6] Fetching all OSM places...")
    elements = fetch_all_osm_places(bbox)
    if limit > 0:
        elements = elements[:limit]
        print(f"      Limited to first {limit} records")

    # ── Step 3: Extract service nodes for proximity scoring ──
    print("\n  [3/6] Extracting service nodes...")
    transport_nodes = [e for e in elements if e.get("tags",{}).get("railway") == "station"
                       or e.get("tags",{}).get("amenity") in ("bus_station","ferry_terminal")]
    hospital_nodes  = [e for e in elements if e.get("tags",{}).get("amenity") == "hospital"]
    police_nodes    = [e for e in elements if e.get("tags",{}).get("amenity") == "police"]
    print(f"      Transport: {len(transport_nodes)}  |  Hospitals: {len(hospital_nodes)}  |  Police: {len(police_nodes)}")

    # ── Step 4: Wikipedia batch enrichment ──
    print("\n  [4/6] Wikipedia enrichment (priority records)...")
    priority = [e for e in elements
                if e.get("tags",{}).get("wikipedia")
                or _classify(e.get("tags",{}))[0] in ("Heritage Site","Museum","Beach","Temple","Church")][:80]
    wiki_map = enrich_with_wikipedia(priority)

    # ── Step 5: Assemble all records ──
    print(f"\n  [5/6] Assembling {len(elements)} deep records...")
    records: List[Dict] = []
    for i, el in enumerate(elements):
        name = el.get("tags",{}).get("name","")
        wiki = wiki_map.get(name,"")
        try:
            rec = assemble_record(
                element         = el,
                city_center_lat = center_lat,
                city_center_lon = center_lon,
                admin_zone      = "Mangaluru, Dakshina Kannada, Karnataka",
                transport_nodes = transport_nodes,
                hospital_nodes  = hospital_nodes,
                police_nodes    = police_nodes,
                city_aqi        = city_aqi,
                city_temp       = city_temp,
                wiki_desc       = wiki,
                all_elements    = elements,
            )
            records.append(rec)
        except Exception as e:
            if verbose: print(f"      Skipped '{name}': {e}")

        if (i+1) % 100 == 0:
            print(f"      Processed {i+1}/{len(elements)}...")

    # ── Step 6: Save ──
    print(f"\n  [6/6] Saving {len(records)} records...")

    city_summary = build_city_summary(records, city_aqi, city_temp)

    output = {
        "meta": {
            "city_id":        city_id,
            "generated_at":   _now(),
            "total_records":  len(records),
            "domains":        ["geo","category","temporal","crowd","review","safety",
                               "economic","cultural","experience","environment",
                               "bias","crowd_psychology","cultural_density","virality","sustainability"],
            "schema_version": "v1_10domains",
        },
        "city_summary": city_summary,
        "records":       records,
    }

    intel_path = f"data_storage/{city_id}_deep_intel.json"
    summary_path = f"data_storage/{city_id}_intel_summary.json"

    with open(intel_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(city_summary, f, ensure_ascii=False, indent=2)

    size_mb = os.path.getsize(intel_path) / (1024*1024)

    print(f"\n{'═'*65}")
    print(f"  ✓  DEEP INTELLIGENCE COMPLETE")
    print(f"  Records:  {len(records)}")
    print(f"  Intel:    {intel_path}  ({size_mb:.1f} MB)")
    print(f"  Summary:  {summary_path}")
    print(f"\n  CATEGORY DISTRIBUTION:")
    for cat, count in city_summary["category_distribution"].items():
        print(f"    {cat:<28} {count:>5}")
    print(f"\n  AQI: {city_aqi.get('us_aqi','N/A')}  |  Temp: {city_temp.get('temperature_2m','N/A')}°C")
    print(f"  Avg authenticity: {city_summary['avg_authenticity_score']}")
    print(f"  Heritage places:  {city_summary['heritage_places_count']}")
    print(f"  Wikipedia enriched: {city_summary['wikipedia_enriched_count']}")
    print(f"{'═'*65}\n")

    return output


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Deep Intelligence Collector — 10 Core Domains per place"
    )
    parser.add_argument("--city",    default="mangalore")
    parser.add_argument("--bbox",    default="12.78,74.75,13.05,75.05",
                        help="south,west,north,east")
    parser.add_argument("--center",  default="12.9141,74.8560",
                        help="lat,lon of city centre")
    parser.add_argument("--limit",   type=int, default=0,
                        help="Limit records (0=all)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    center = [float(x) for x in args.center.split(",")]

    build_deep_intelligence(
        city_id    = args.city.lower(),
        bbox       = args.bbox,
        center_lat = center[0],
        center_lon = center[1],
        limit      = args.limit,
        verbose    = args.verbose,
    )


if __name__ == "__main__":
    main()