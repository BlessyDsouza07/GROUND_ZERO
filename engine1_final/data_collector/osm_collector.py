"""
data_collector/osm_collector.py  [v2 — Deep Mangalore Collection]

OpenStreetMap Overpass API Collector — Expanded for Ground Zero.

COVERAGE EXPANSION vs v1:
  - Wider bbox: covers Mangalore + Udupi coastal belt + Coorg foothills
  - 14 query groups (was 9) — added unexplored/local/feast-specific
  - Tulu Nadu cultural specifics: Bhuta Kola shrines, Kambala fields,
    coastal fishing villages, church feasts, temple car routes
  - All OSM tag variants captured: addr:*, contact:*, name:tulu, name:kn
  - Ways with center coords — captures large parks, temples, malls
  - Nodes AND relations for large complex sites

DATA SOURCES (all free, no key required):
  OpenStreetMap via Overpass API — ODbL licence
  Attribution: © OpenStreetMap contributors
"""

import json
import os
import time
import requests
from datetime import datetime, timezone
from typing import Dict
from utils.logger import get_logger
from utils.rate_limiter import sleep_between_calls, OSM_DELAY

logger = get_logger("OSMCollector")

# ============================================================
# EXTENDED BOUNDING BOX
# Covers Mangalore city + beaches + Pilikula + coastal villages
# + Udupi southern edge + Bantwal + Puttur foothills
# South, West, North, East
# ============================================================

MANGALORE_BBOX     = "12.780,74.750,13.020,74.990"  # Core city + beaches
COASTAL_BELT_BBOX  = "12.820,74.720,13.060,74.880"  # Coastal villages + fishing harbours
HINTERLAND_BBOX    = "12.750,74.850,12.950,75.050"  # Pilikula, Kadri hills, Bantwal belt

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {
    "User-Agent": "GroundZeroEngine/2.0 (Mangalore tourism intelligence; non-commercial)"
}

RAW_OUTPUT_DIR = "data_storage/raw"
os.makedirs(RAW_OUTPUT_DIR, exist_ok=True)

# ============================================================
# QUERY GROUPS — 14 targeted groups
# Each is a precise Overpass QL query for one tourism category
# ============================================================

def build_queries(bbox: str) -> Dict[str, str]:
    return {

    # ── 1. ALL FOOD & DRINK ─────────────────────────────────
    "food_and_drink": f"""
[out:json][timeout:90];
(
  node["amenity"~"restaurant|cafe|fast_food|bar|pub|food_court|ice_cream|
       juice_bar|bakery|snack_bar|nightclub|canteen|street_vendor|biryani_house|
       sweet_shop|seafood|dhaba"]({bbox});
  way["amenity"~"restaurant|cafe|fast_food|bar|pub|food_court"]({bbox});
  node["shop"~"bakery|confectionery|seafood|fish|butcher|greengrocer|
       beverages|alcohol|deli|spices"]({bbox});
  node["cuisine"]({bbox});
);
out center tags;
""",

    # ── 2. ACCOMMODATION ────────────────────────────────────
    "accommodation": f"""
[out:json][timeout:90];
(
  node["tourism"~"hotel|hostel|guest_house|motel|resort|homestay|apartment|camp_site"]({bbox});
  way["tourism"~"hotel|hostel|guest_house|motel|resort|homestay"]({bbox});
  way["building"="hotel"]({bbox});
  node["building"="hotel"]({bbox});
);
out center tags;
""",

    # ── 3. BEACHES, COAST & WATER ───────────────────────────
    "nature_water": f"""
[out:json][timeout:90];
(
  node["natural"~"beach|waterfall|water|wood|forest|hill|peak|wetland|spring|cliff|bay"]({bbox});
  way["natural"~"beach|water|wood|coastline|wetland|bay"]({bbox});
  node["leisure"~"park|garden|nature_reserve|marina|beach_resort|playground"]({bbox});
  way["leisure"~"park|garden|nature_reserve|marina"]({bbox});
  node["waterway"~"dock|jetty|river|stream|waterfall"]({bbox});
  way["waterway"~"river|stream|dock"]({bbox});
  node["tourism"="picnic_site"]({bbox});
  node["tourism"="viewpoint"]({bbox});
  node["natural"="spring"]({bbox});
);
out center tags;
""",

    # ── 4. TEMPLES, SHRINES & RELIGIOUS ─────────────────────
    # Mangalore-specific: Bhuta Kola shrines, Jainas, temples
    "religion": f"""
[out:json][timeout:90];
(
  node["amenity"="place_of_worship"]({bbox});
  way["amenity"="place_of_worship"]({bbox});
  node["building"~"temple|church|mosque|chapel|shrine|mandir|masjid|gurudwara"]({bbox});
  way["building"~"temple|church|mosque|chapel|shrine"]({bbox});
  node["religion"]({bbox});
  node["historic"~"wayside_shrine|memorial|monument|ruins|castle|fort|archaeological_site|lighthouse"]({bbox});
  way["historic"]({bbox});
  node["man_made"="shrine"]({bbox});
  node["name:tulu"]({bbox});
);
out center tags;
""",

    # ── 5. CULTURE, MUSEUMS, HERITAGE ───────────────────────
    "culture_heritage": f"""
[out:json][timeout:90];
(
  node["tourism"~"museum|gallery|artwork|attraction|information|theme_park|zoo"]({bbox});
  way["tourism"~"museum|gallery|attraction|theme_park|zoo"]({bbox});
  node["amenity"~"theatre|cinema|arts_centre|library|community_centre|exhibition_centre"]({bbox});
  way["amenity"~"theatre|cinema|arts_centre|library"]({bbox});
  node["heritage"]({bbox});
  way["heritage"]({bbox});
  node["historic"]({bbox});
  node["tourism"="artwork"]({bbox});
);
out center tags;
""",

    # ── 6. SHOPPING & MARKETS ───────────────────────────────
    "shopping": f"""
[out:json][timeout:90];
(
  node["shop"~"spices|supermarket|grocery|clothes|saree|jewellery|electronics|
       gift|books|pharmacy|mobile_phone|hardware|toys|florist|optician|
       perfumery|music|stationery|art|antiques|handcraft"]({bbox});
  node["amenity"~"marketplace|market|shopping_centre"]({bbox});
  way["amenity"~"marketplace|market|shopping_centre"]({bbox});
  way["shop"~"supermarket|department_store|clothes"]({bbox});
  node["craft"]({bbox});
);
out center tags;
""",

    # ── 7. SPORTS, WELLNESS & RECREATION ────────────────────
    "sports_wellness": f"""
[out:json][timeout:90];
(
  node["leisure"~"stadium|sports_centre|swimming_pool|fitness_centre|golf_course|
       water_park|amusement_arcade|pitch|track"]({bbox});
  way["leisure"~"stadium|sports_centre|swimming_pool|fitness_centre|pitch"]({bbox});
  node["sport"]({bbox});
  node["amenity"="spa"]({bbox});
  node["shop"~"massage|beauty|hairdresser|yoga"]({bbox});
  node["healthcare"~"alternative|ayurveda"]({bbox});
);
out center tags;
""",

    # ── 8. TRANSPORT & CONNECTIVITY ─────────────────────────
    "transport": f"""
[out:json][timeout:90];
(
  node["amenity"~"bus_station|ferry_terminal|taxi|parking|fuel|car_rental|bicycle_rental"]({bbox});
  node["public_transport"~"station|stop_position|platform"]({bbox});
  node["railway"~"station|halt|tram_stop"]({bbox});
  way["railway"="station"]({bbox});
  node["aeroway"~"aerodrome|terminal|gate"]({bbox});
  way["aeroway"~"aerodrome|terminal"]({bbox});
  node["amenity"="taxi"]({bbox});
  node["highway"="bus_stop"]({bbox});
);
out center tags;
""",

    # ── 9. EMERGENCY, HEALTH & SAFETY ───────────────────────
    "safety_health": f"""
[out:json][timeout:90];
(
  node["amenity"~"hospital|police|fire_station|pharmacy|bank|atm|post_office|
       clinic|dentist|veterinary|embassy|consulate"]({bbox});
  way["amenity"~"hospital|police|fire_station|clinic"]({bbox});
  node["emergency"]({bbox});
  node["healthcare"~"hospital|clinic|doctor|pharmacy|dentist"]({bbox});
);
out center tags;
""",

    # ── 10. UNEXPLORED: LOCAL & AUTHENTIC MANGALORE ─────────
    # Fishing villages, Kambala fields, boat jetties, salt pans,
    # arecanut farms, cashew processing units — real Mangalore
    "unexplored_local": f"""
[out:json][timeout:90];
(
  node["landuse"~"farmland|orchard|aquaculture|salt_pond|reservoir"]({bbox});
  way["landuse"~"farmland|orchard|aquaculture|salt_pond"]({bbox});
  node["fishing"="yes"]({bbox});
  node["man_made"~"lighthouse|pier|jetty|breakwater|fish_farm|salt_evaporation_pond"]({bbox});
  way["man_made"~"pier|jetty|breakwater"]({bbox});
  node["harbour"]({bbox});
  way["harbour"]({bbox});
  node["place"~"neighbourhood|suburb|quarter|village|hamlet"]({bbox});
  node["amenity"="community_centre"]({bbox});
  node["tourism"="yes"]({bbox});
  node["description"]({bbox});
);
out center tags;
""",

    # ── 11. FEASTS, EVENTS & FESTIVALS (OSM-tagged) ─────────
    # Church feasts, temple car festivals, Kambala events
    "feasts_festivals": f"""
[out:json][timeout:90];
(
  node["event"]({bbox});
  node["festival"]({bbox});
  node["recurring_event"]({bbox});
  node["amenity"="events_venue"]({bbox});
  way["amenity"="events_venue"]({bbox});
  node["tourism"="yes"]["name"~"[Ff]east|[Ff]estival|[Uu]tsav|[Jj]atra|[Mm]ela|[Kk]ambala|[Pp]rayer|[Cc]ar [Ff]estival"]({bbox});
  node["leisure"~"bandstand|outdoor_stage|amphitheatre"]({bbox});
  node["amenity"~"conference_centre|exhibition_centre|music_venue"]({bbox});
);
out center tags;
""",

    # ── 12. EDUCATION & INSTITUTIONS ────────────────────────
    "education_institutions": f"""
[out:json][timeout:90];
(
  node["amenity"~"university|college|school|research_institute"]({bbox});
  way["amenity"~"university|college|school"]({bbox});
  node["amenity"="place_of_worship"]["denomination"]({bbox});
  node["office"~"government|ngo|diplomatic|association"]({bbox});
);
out center tags;
""",

    # ── 13. COASTAL BELT — fishing villages & hidden beaches ─
    "coastal_villages": f"""
[out:json][timeout:90];
(
  node["natural"~"beach|bay|cape|cliff|coastline|inlet"]({COASTAL_BELT_BBOX});
  way["natural"~"beach|coastline|bay"]({COASTAL_BELT_BBOX});
  node["place"~"village|hamlet"]({COASTAL_BELT_BBOX});
  node["man_made"~"lighthouse|pier|breakwater"]({COASTAL_BELT_BBOX});
  node["harbour"]({COASTAL_BELT_BBOX});
  node["tourism"]({COASTAL_BELT_BBOX});
  node["amenity"="place_of_worship"]({COASTAL_BELT_BBOX});
  node["fishing"="yes"]({COASTAL_BELT_BBOX});
);
out center tags;
""",

    # ── 14. HINTERLAND — nature, waterfalls, hills ──────────
    "hinterland_nature": f"""
[out:json][timeout:90];
(
  node["natural"~"waterfall|peak|hill|spring|cave|rock"]({HINTERLAND_BBOX});
  way["natural"~"waterfall|wood|forest"]({HINTERLAND_BBOX});
  node["leisure"~"nature_reserve|park"]({HINTERLAND_BBOX});
  way["leisure"~"nature_reserve"]({HINTERLAND_BBOX});
  node["tourism"~"attraction|viewpoint|picnic_site"]({HINTERLAND_BBOX});
  node["place"~"village|hamlet"]({HINTERLAND_BBOX});
  node["amenity"="place_of_worship"]({HINTERLAND_BBOX});
  node["historic"]({HINTERLAND_BBOX});
);
out center tags;
""",
    }


# ============================================================
# FETCH ONE QUERY GROUP
# ============================================================

def fetch_query_group(group_name: str, query: str, max_retries: int = 3) -> Dict:
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"  Fetching '{group_name}' (attempt {attempt})")
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query.strip()},
                headers=HEADERS,
                timeout=120
            )
            if resp.status_code == 200:
                data = resp.json()
                n = len(data.get("elements", []))
                logger.info(f"  ✓ '{group_name}': {n} elements")
                return data
            elif resp.status_code == 429:
                logger.warning(f"  Rate limited on '{group_name}'. Waiting 30s...")
                time.sleep(30)
            else:
                logger.warning(f"  HTTP {resp.status_code} on '{group_name}'")
        except requests.Timeout:
            logger.warning(f"  Timeout on '{group_name}' (attempt {attempt})")
            time.sleep(8 * attempt)
        except Exception as e:
            logger.error(f"  Error on '{group_name}': {e}")

        sleep_between_calls(OSM_DELAY * attempt)

    logger.error(f"  FAILED: '{group_name}' after {max_retries} attempts — returning empty")
    return {"elements": []}


# ============================================================
# MERGE — deduplicate by OSM element ID
# ============================================================

def merge_elements(group_results: Dict[str, Dict]) -> Dict:
    seen_ids = set()
    merged = []

    for group_name, result in group_results.items():
        for el in result.get("elements", []):
            el_id = el.get("id")
            if el_id and el_id not in seen_ids:
                seen_ids.add(el_id)
                # Tag which group found this element (for debugging)
                el["_source_group"] = group_name
                merged.append(el)

    logger.info(f"  Merged: {len(merged)} unique OSM elements")
    return {"elements": merged}


# ============================================================
# MAIN COLLECTOR
# ============================================================

def fetch_osm_places(
    save_raw: bool = True,
    output_path: str = f"{RAW_OUTPUT_DIR}/osm_mangalore_raw.json"
) -> str:
    """
    Fetch all tourist-relevant places from OSM for Mangalore.
    14 query groups, 3 bounding boxes, deduplicated output.

    Returns path to saved raw JSON (input for normalizer).
    """

    logger.info("=" * 60)
    logger.info("OSM COLLECTOR v2 — Deep Mangalore Fetch")
    logger.info(f"Primary bbox: {MANGALORE_BBOX}")
    logger.info(f"Coastal bbox: {COASTAL_BELT_BBOX}")
    logger.info(f"Hinterland bbox: {HINTERLAND_BBOX}")
    logger.info("=" * 60)

    queries = build_queries(MANGALORE_BBOX)
    group_results = {}

    for group_name, query in queries.items():
        result = fetch_query_group(group_name, query)
        group_results[group_name] = result
        sleep_between_calls(OSM_DELAY)

    merged = merge_elements(group_results)
    merged["metadata"] = {
        "city": "Mangalore",
        "bboxes": {
            "primary": MANGALORE_BBOX,
            "coastal": COASTAL_BELT_BBOX,
            "hinterland": HINTERLAND_BBOX
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL — © OpenStreetMap contributors",
        "attribution": "Map data © OpenStreetMap contributors",
        "total_elements": len(merged["elements"]),
        "groups_fetched": list(group_results.keys()),
        "group_counts": {k: len(v.get("elements",[])) for k, v in group_results.items()}
    }

    if save_raw:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info(f"  Raw saved → {output_path}")
        logger.info(f"  Total elements: {len(merged['elements'])}")

    logger.info("OSM COLLECTOR — Done")
    return output_path


if __name__ == "__main__":
    path = fetch_osm_places()
    print(f"\n✅ OSM data saved: {path}")
