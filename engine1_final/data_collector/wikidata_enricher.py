"""
data_collector/wikidata_enricher.py

Wikidata SPARQL Enricher for Engine 1.

Wikidata is:
  - Free, no API key, CC0 public domain
  - Structured facts about places (coordinates, descriptions, images)
  - Cross-linked to OSM via wikidata= tag
  - The world's largest structured knowledge base

What this enricher does:
  - Queries Wikidata SPARQL for tourist places in Mangalore
  - Enriches existing OSM entities with Wikidata descriptions
  - Provides a second source for multi-source consensus
  - Extracts inception dates (for heritage authenticity)
  - Cross-validates coordinates

Source label: "community_map" (Wikidata is openly maintained community data)
"""

import json
import os
import time
import requests
from typing import List, Dict, Optional
from utils.logger import get_logger
from utils.rate_limiter import sleep_between_calls, WIKI_DELAY

logger = get_logger("WikidataEnricher")

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

HEADERS = {
    "User-Agent": "GroundZeroEngine/1.0 (educational tourism project)",
    "Accept": "application/json"
}

RAW_OUTPUT_DIR = "data_storage/raw"
os.makedirs(RAW_OUTPUT_DIR, exist_ok=True)


# ============================================================
# SPARQL QUERY — Tourist places near Mangalore (within ~15km)
# ============================================================

MANGALORE_WIKIDATA_QUERY = """
SELECT DISTINCT ?place ?placeLabel ?description ?lat ?lon ?inception ?heritage ?osmRelation WHERE {

  # Places within ~15km of Mangalore city centre (12.87, 74.86)
  SERVICE wikibase:around {
    ?place wdt:P625 ?coord .
    bd:serviceParam wikibase:center "Point(74.86 12.87)"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "15" .
  }

  # Must be a physical place of some kind (not a person, organisation etc.)
  ?place wdt:P31 ?type .
  FILTER(?type IN (
    wd:Q839954,    # archaeological site
    wd:Q33506,     # museum
    wd:Q12280,     # bridge
    wd:Q16560,     # palace
    wd:Q44539,     # temple
    wd:Q16970,     # church
    wd:Q39614,     # cemetery
    wd:Q515,       # city (for neighbourhoods)
    wd:Q23413,     # castle
    wd:Q570116,    # tourist attraction
    wd:Q4022,      # river
    wd:Q23397,     # lake
    wd:Q40080,     # beach
    wd:Q1145276,   # lighthouse
    wd:Q35509,     # market
    wd:Q7075,      # library
    wd:Q207694,    # art museum
    wd:Q4830453,   # business
    wd:Q3947,      # house
    wd:Q13406463,  # historic site
    wd:Q1469416,   # urban park
    wd:Q2977,      # cathedral
    wd:Q82117,     # fort
    wd:Q8502,      # mountain
    wd:Q34763,     # waterfall
    wd:Q2044,      # bay
    wd:Q1437459    # festival (recurring cultural events)
  ))

  # Extract coordinates
  ?place wdt:P625 ?coord .
  BIND(geof:latitude(?coord) AS ?lat)
  BIND(geof:longitude(?coord) AS ?lon)

  # Optional enrichment fields
  OPTIONAL { ?place schema:description ?description FILTER(LANG(?description) = "en") }
  OPTIONAL { ?place wdt:P571 ?inception }
  OPTIONAL { ?place wdt:P1435 ?heritage }
  OPTIONAL { ?place wdt:P402 ?osmRelation }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en,kn" .
  }
}
LIMIT 300
"""


# ============================================================
# FETCH WIKIDATA PLACES
# ============================================================

def fetch_wikidata_places(
    save_raw: bool = True,
    output_path: str = f"{RAW_OUTPUT_DIR}/wikidata_mangalore_raw.json"
) -> List[Dict]:
    """
    Query Wikidata SPARQL for tourist-relevant places near Mangalore.

    Returns:
        List[Dict]: normalized place records with wikidata enrichment
    """

    logger.info("WikidataEnricher — Starting SPARQL query")

    sleep_between_calls(WIKI_DELAY)

    try:
        response = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": MANGALORE_WIKIDATA_QUERY, "format": "json"},
            headers=HEADERS,
            timeout=60
        )

        if response.status_code != 200:
            logger.error(f"Wikidata SPARQL failed: HTTP {response.status_code}")
            return []

        data = response.json()
        results = data.get("results", {}).get("bindings", [])
        logger.info(f"  Wikidata returned {len(results)} results")

    except Exception as e:
        logger.error(f"Wikidata fetch failed: {e}")
        return []

    places = []
    for row in results:
        place = normalize_wikidata_row(row)
        if place:
            places.append(place)

    logger.info(f"  Normalized {len(places)} valid Wikidata places")

    if save_raw:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"places": places, "source": "Wikidata SPARQL", "count": len(places)}, f, indent=2)
        logger.info(f"  Wikidata raw saved → {output_path}")

    return places


# ============================================================
# NORMALIZE ONE WIKIDATA ROW
# ============================================================

def normalize_wikidata_row(row: Dict) -> Optional[Dict]:
    """Convert a raw SPARQL result row into a clean place dict."""

    try:
        wikidata_id = row.get("place", {}).get("value", "").split("/")[-1]
        name = row.get("placeLabel", {}).get("value", "")
        description = row.get("description", {}).get("value", "")
        lat = float(row.get("lat", {}).get("value", 0))
        lon = float(row.get("lon", {}).get("value", 0))
        inception = row.get("inception", {}).get("value", "")
        heritage = row.get("heritage", {}).get("value", "")
        osm_relation = row.get("osmRelation", {}).get("value", "")

        if not name or name.startswith("Q"):
            return None  # Skip unnamed / ID-only results

        if not (12.7 <= lat <= 13.1 and 74.7 <= lon <= 75.1):
            return None  # Outside Mangalore region

        return {
            "wikidata_id": wikidata_id,
            "name": name,
            "description": description[:500] if description else "",
            "latitude": lat,
            "longitude": lon,
            "inception": inception[:10] if inception else "",
            "heritage_status": bool(heritage),
            "osm_relation": osm_relation,
            "source": "wikidata",
            "source_category": "community_map",
            "wikidata_url": f"https://www.wikidata.org/wiki/{wikidata_id}"
        }

    except Exception:
        return None


# ============================================================
# ENRICH OSM ENTITIES WITH WIKIDATA
# ============================================================

def build_wikidata_lookup(wikidata_places: List[Dict]) -> Dict[str, Dict]:
    """
    Build a lookup dict: wikidata_id → place record.
    OSM entities store wikidata= tag which links to this.
    """
    return {p["wikidata_id"]: p for p in wikidata_places if p.get("wikidata_id")}


def enrich_entity_with_wikidata(entity_trace: List[str], wikidata_lookup: Dict[str, Dict]) -> Optional[Dict]:
    """
    If an OSM entity has a wikidata= tag stored in its decision_trace,
    fetch the matching Wikidata record and return enrichment data.
    """
    for trace in entity_trace:
        if trace.startswith("OSM_EXTRA:"):
            try:
                extra = json.loads(trace.replace("OSM_EXTRA:", ""))
                wikidata_id = extra.get("wikidata", "").split("/")[-1]
                if wikidata_id in wikidata_lookup:
                    return wikidata_lookup[wikidata_id]
            except Exception:
                pass
    return None


# ============================================================
# STANDALONE RUN
# ============================================================

if __name__ == "__main__":
    places = fetch_wikidata_places()
    print(f"\n✅ Wikidata places fetched: {len(places)}")
    if places:
        print(f"   Sample: {places[0]['name']} — {places[0]['description'][:80]}")
