"""
data_collector/opentripmap_collector.py

OpenTripMap (OTM) API Collector for Engine 1.

OpenTripMap is:
  - Free tier: 5000 calls/day, no credit card
  - Tourism-focused POI database
  - Data sourced from OSM + curated additions
  - Provides "stars" rating (0-3) for tourist importance
  - Covers: natural, cultural, historic, architecture, religion, sport

API Key: required (free registration at https://opentripmap.io)
Set in .env as: OPENTRIPMAP_KEY=your_key_here

What this module adds:
  - Tourism importance rating (0.0, 0.5, 1.0, 2.0, 3.0) from OTM
  - "xid" — OTM's cross-reference ID for places
  - Kinds/categories confirmed by tourism experts
  - Acts as 3rd source for multi-source consensus (verified community data)

If OTM key is not set, this module gracefully skips and logs a warning.
The pipeline still works perfectly with OSM + Wikidata alone.

Source label: "community_map"
"""

import json
import os
import requests
import time
from typing import List, Dict, Optional
from utils.logger import get_logger
from utils.rate_limiter import sleep_between_calls, OTM_DELAY

logger = get_logger("OpenTripMapCollector")

OTM_BASE = "https://api.opentripmap.com/0.1/en/places"

# Mangalore centre
MANGALORE_LAT = 12.9141
MANGALORE_LON = 74.8560

# Radius in meters
SEARCH_RADIUS = 15000  # 15km covers all of Mangalore

RAW_OUTPUT_DIR = "data_storage/raw"
os.makedirs(RAW_OUTPUT_DIR, exist_ok=True)

# OTM "kinds" relevant to tourism — excludes purely commercial/industrial
TOURIST_KINDS = ",".join([
    "cultural",
    "historic",
    "architecture",
    "natural",
    "religion",
    "beaches_and_coasts",
    "sport",
    "tourist_facilities",
    "amusements",
    "museums",
    "interesting_places"
])


# ============================================================
# FETCH PLACES LIST (radius query)
# ============================================================

def fetch_otm_places(
    api_key: str,
    save_raw: bool = True,
    output_path: str = f"{RAW_OUTPUT_DIR}/otm_mangalore_raw.json"
) -> List[Dict]:
    """
    Fetch tourist places near Mangalore from OpenTripMap.

    Uses radius search + filtering by tourism-relevant kinds.
    OTM rates each place 0-3 stars for tourist importance —
    this becomes our "tourist_importance" signal.

    Args:
        api_key: OTM API key (from .env OPENTRIPMAP_KEY)
        save_raw: whether to save raw JSON
        output_path: where to save

    Returns:
        List[Dict]: normalized OTM place records
    """

    if not api_key:
        logger.warning("OpenTripMap: no API key set. Skipping OTM collection.")
        logger.warning("  Get a free key at https://opentripmap.io → engine still works without it")
        return []

    logger.info("OpenTripMapCollector — Starting fetch")

    # Step 1: Get list of places in radius
    list_url = f"{OTM_BASE}/radius"
    params = {
        "apikey": api_key,
        "lat": MANGALORE_LAT,
        "lon": MANGALORE_LON,
        "radius": SEARCH_RADIUS,
        "kinds": TOURIST_KINDS,
        "rate": "1",          # Only places with at least 0.5 star importance
        "limit": 500,
        "format": "json"
    }

    try:
        response = requests.get(list_url, params=params, timeout=30)
        if response.status_code != 200:
            logger.error(f"OTM list fetch failed: HTTP {response.status_code}")
            return []

        raw_list = response.json()
        logger.info(f"  OTM returned {len(raw_list)} places in radius")

    except Exception as e:
        logger.error(f"OTM fetch error: {e}")
        return []

    # Step 2: Fetch details for each place (includes description)
    places = []
    detail_url = f"{OTM_BASE}/xid"

    for i, item in enumerate(raw_list):
        xid = item.get("xid")
        if not xid:
            continue

        sleep_between_calls(OTM_DELAY)

        try:
            detail_response = requests.get(
                f"{detail_url}/{xid}",
                params={"apikey": api_key},
                timeout=15
            )

            if detail_response.status_code == 200:
                detail = detail_response.json()
                normalized = normalize_otm_place(detail)
                if normalized:
                    places.append(normalized)

        except Exception as e:
            logger.debug(f"OTM detail fetch failed for {xid}: {e}")
            continue

        if (i + 1) % 50 == 0:
            logger.info(f"  OTM progress: {i+1}/{len(raw_list)}")

    logger.info(f"  OTM enriched {len(places)} places with details")

    if save_raw:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"places": places, "count": len(places)}, f, ensure_ascii=False, indent=2)
        logger.info(f"  OTM raw saved → {output_path}")

    return places


# ============================================================
# NORMALIZE OTM DETAIL RECORD
# ============================================================

def normalize_otm_place(detail: Dict) -> Optional[Dict]:
    """Convert OTM detail API response to clean dict."""

    try:
        xid = detail.get("xid", "")
        name = detail.get("name", "").strip()

        if not name:
            return None

        point = detail.get("point", {})
        lat = point.get("lat")
        lon = point.get("lon")

        if lat is None or lon is None:
            return None

        if not (12.7 <= lat <= 13.1 and 74.7 <= lon <= 75.1):
            return None

        kinds = detail.get("kinds", "")
        rate = detail.get("rate", 0)         # OTM tourist importance: 0-3
        wikipedia = detail.get("wikipedia")
        wikidata = detail.get("wikidata")

        # Extract description from info block
        info = detail.get("info", {})
        description = info.get("descr", "") or ""

        return {
            "otm_xid": xid,
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "kinds": kinds,
            "tourist_importance": float(rate),
            "description": description[:500] if description else "",
            "wikipedia": wikipedia,
            "wikidata": wikidata,
            "source": "opentripmap",
            "source_category": "community_map",
            "otm_url": f"https://opentripmap.com/en/card/{xid}"
        }

    except Exception:
        return None


# ============================================================
# BUILD OTM LOOKUP BY NAME (for cross-enrichment)
# ============================================================

def build_otm_name_lookup(otm_places: List[Dict]) -> Dict[str, Dict]:
    """
    Build a lookup dict: normalized_name → OTM record.
    Used by the pipeline to cross-enrich OSM entities.
    """
    lookup = {}
    for p in otm_places:
        key = p["name"].lower().strip()
        lookup[key] = p
    return lookup


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    import os as _os
    from dotenv import load_dotenv
    load_dotenv()

    key = _os.getenv("OPENTRIPMAP_KEY", "")

    if not key:
        print("⚠  OPENTRIPMAP_KEY not set in .env")
        print("   Get a free key at https://opentripmap.io")
        print("   Engine 1 works without it (OSM + Wikidata still run)")
    else:
        places = fetch_otm_places(api_key=key)
        print(f"\n✅ OpenTripMap places collected: {len(places)}")
