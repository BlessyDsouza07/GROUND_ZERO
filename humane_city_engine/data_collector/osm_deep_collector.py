"""
data_collector/osm_deep_collector.py

OSM DEEP COLLECTOR
──────────────────────────────────────────────────────────────
Fetches ALL named places from OpenStreetMap via Overpass API.
Called by rare_data_orchestrator as: fetch_osm_deep(bbox_str, output_path)

Output: data_storage/<city_id>_raw.json
  {
    "city_id":      "mangalore",
    "bbox":         "12.78,74.75,13.05,75.05",
    "generated_at": "...",
    "total":        1234,
    "elements":     [ ...OSM elements with tags... ]
  }

Source: OpenStreetMap Overpass API (ODbL license — open, legal)
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional

import requests

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "HumaneCityEngine/3.0 (OSM deep collector, non-commercial)"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sleep(s: float = 3.0):
    time.sleep(s)


def _overpass_post(query: str, timeout_buf: int = 30) -> List[Dict]:
    """POST Overpass query, try all mirrors, return elements list."""
    for mirror in OVERPASS_MIRRORS:
        try:
            _sleep(3)
            r = requests.post(
                mirror,
                data={"data": query},
                headers=HEADERS,
                timeout=120 + timeout_buf,
            )
            if r.status_code == 429:
                print(f"    Rate limited on {mirror}, sleeping 15s...")
                _sleep(15); continue
            if r.status_code in (503, 504):
                print(f"    Server busy ({r.status_code}), trying next mirror...")
                continue
            r.raise_for_status()
            data = r.json()
            return data.get("elements", [])
        except Exception as e:
            print(f"    Overpass error on {mirror}: {e}")
            _sleep(5)
    return []


# ── 12 Thematic query blocks — split to avoid timeout ──────────

def _block_places_tourism(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:90];
    (
      node["tourism"]["name"]({bbox});
      node["historic"]["name"]({bbox});
      node["man_made"="lighthouse"]["name"]({bbox});
      node["man_made"="clock"]["name"]({bbox});
      node["man_made"="tower"]["name"]({bbox});
      node["man_made"="water_tower"]["name"]({bbox});
      way["tourism"]["name"]({bbox});
      way["historic"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_food_drink(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:90];
    (
      node["amenity"="restaurant"]["name"]({bbox});
      node["amenity"="cafe"]["name"]({bbox});
      node["amenity"="fast_food"]["name"]({bbox});
      node["amenity"="bar"]["name"]({bbox});
      node["amenity"="pub"]["name"]({bbox});
      node["amenity"="ice_cream"]["name"]({bbox});
      node["amenity"="food_court"]["name"]({bbox});
      node["amenity"="dhaba"]["name"]({bbox});
      node["shop"="bakery"]["name"]({bbox});
      node["shop"="seafood"]["name"]({bbox});
      node["shop"="fish"]["name"]({bbox});
      way["amenity"="restaurant"]["name"]({bbox});
      way["amenity"="cafe"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_accommodation(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["tourism"="hotel"]["name"]({bbox});
      node["tourism"="hostel"]["name"]({bbox});
      node["tourism"="guest_house"]["name"]({bbox});
      node["tourism"="motel"]["name"]({bbox});
      node["tourism"="resort"]["name"]({bbox});
      node["tourism"="homestay"]["name"]({bbox});
      node["tourism"="apartment"]["name"]({bbox});
      way["tourism"="hotel"]["name"]({bbox});
      way["tourism"="resort"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_worship(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:90];
    (
      node["amenity"="place_of_worship"]["name"]({bbox});
      node["building"="temple"]["name"]({bbox});
      node["building"="church"]["name"]({bbox});
      node["building"="mosque"]["name"]({bbox});
      node["building"="chapel"]["name"]({bbox});
      node["building"="shrine"]["name"]({bbox});
      node["building"="cathedral"]["name"]({bbox});
      node["historic"="wayside_shrine"]["name"]({bbox});
      node["historic"="wayside_cross"]["name"]({bbox});
      way["amenity"="place_of_worship"]["name"]({bbox});
      way["building"="temple"]["name"]({bbox});
      way["building"="church"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_nature(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:90];
    (
      node["natural"="beach"]["name"]({bbox});
      node["leisure"="beach"]["name"]({bbox});
      node["natural"="wetland"]["name"]({bbox});
      node["natural"="water"]["name"]({bbox});
      node["natural"="bay"]["name"]({bbox});
      node["natural"="cape"]["name"]({bbox});
      node["natural"="cliff"]["name"]({bbox});
      node["natural"="peak"]["name"]({bbox});
      node["waterway"="waterfall"]["name"]({bbox});
      node["waterway"="river"]["name"]({bbox});
      node["waterway"="stream"]["name"]({bbox});
      node["leisure"="park"]["name"]({bbox});
      node["leisure"="garden"]["name"]({bbox});
      node["leisure"="nature_reserve"]["name"]({bbox});
      node["landuse"="forest"]["name"]({bbox});
      way["natural"="beach"]["name"]({bbox});
      way["natural"="water"]["name"]({bbox});
      way["leisure"="park"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_markets_shopping(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:90];
    (
      node["amenity"="marketplace"]["name"]({bbox});
      node["shop"="craft"]["name"]({bbox});
      node["shop"="spices"]["name"]({bbox});
      node["shop"="supermarket"]["name"]({bbox});
      node["shop"="mall"]["name"]({bbox});
      node["shop"="department_store"]["name"]({bbox});
      node["shop"="cashew"]["name"]({bbox});
      node["shop"="clothes"]["name"]({bbox});
      node["shop"="jewelry"]["name"]({bbox});
      node["shop"="hardware"]["name"]({bbox});
      node["shop"="electronics"]["name"]({bbox});
      node["amenity"="bank"]["name"]({bbox});
      node["amenity"="atm"]["name"]({bbox});
      way["amenity"="marketplace"]["name"]({bbox});
      way["shop"="mall"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_education(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["amenity"="university"]["name"]({bbox});
      node["amenity"="college"]["name"]({bbox});
      node["amenity"="school"]["name"]({bbox});
      node["amenity"="library"]["name"]({bbox});
      node["amenity"="kindergarten"]["name"]({bbox});
      node["amenity"="research_institute"]["name"]({bbox});
      way["amenity"="university"]["name"]({bbox});
      way["amenity"="college"]["name"]({bbox});
      way["amenity"="school"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_health_emergency(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["amenity"="hospital"]["name"]({bbox});
      node["amenity"="clinic"]["name"]({bbox});
      node["amenity"="doctors"]["name"]({bbox});
      node["amenity"="pharmacy"]["name"]({bbox});
      node["amenity"="police"]["name"]({bbox});
      node["amenity"="fire_station"]["name"]({bbox});
      node["amenity"="coast_guard"]["name"]({bbox});
      node["emergency"="lifeguard"]["name"]({bbox});
      node["amenity"="blood_bank"]["name"]({bbox});
      way["amenity"="hospital"]["name"]({bbox});
      way["amenity"="clinic"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_transport(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["railway"="station"]["name"]({bbox});
      node["railway"="halt"]["name"]({bbox});
      node["amenity"="bus_station"]["name"]({bbox});
      node["amenity"="ferry_terminal"]["name"]({bbox});
      node["aeroway"="aerodrome"]["name"]({bbox});
      node["aeroway"="terminal"]["name"]({bbox});
      node["amenity"="parking"]["name"]({bbox});
      node["amenity"="fuel"]["name"]({bbox});
      node["man_made"="pier"]["name"]({bbox});
      node["man_made"="jetty"]["name"]({bbox});
      node["waterway"="dock"]["name"]({bbox});
      node["landuse"="harbour"]["name"]({bbox});
      way["railway"="station"]["name"]({bbox});
      way["amenity"="bus_station"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_culture_community(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["amenity"="arts_centre"]["name"]({bbox});
      node["amenity"="theatre"]["name"]({bbox});
      node["tourism"="museum"]["name"]({bbox});
      node["tourism"="gallery"]["name"]({bbox});
      node["amenity"="community_centre"]["name"]({bbox});
      node["amenity"="social_centre"]["name"]({bbox});
      node["amenity"="cinema"]["name"]({bbox});
      node["amenity"="nightclub"]["name"]({bbox});
      node["amenity"="events_venue"]["name"]({bbox});
      node["amenity"="stadium"]["name"]({bbox});
      node["leisure"="stadium"]["name"]({bbox});
      node["leisure"="sports_centre"]["name"]({bbox});
      way["tourism"="museum"]["name"]({bbox});
      way["amenity"="theatre"]["name"]({bbox});
      way["amenity"="stadium"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_industry_infrastructure(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["industrial"]["name"]({bbox});
      node["man_made"="works"]["name"]({bbox});
      node["man_made"="factory"]["name"]({bbox});
      node["landuse"="industrial"]["name"]({bbox});
      node["man_made"="water_works"]["name"]({bbox});
      node["man_made"="wastewater_plant"]["name"]({bbox});
      node["man_made"="power_station"]["name"]({bbox});
      node["amenity"="post_office"]["name"]({bbox});
      node["office"="government"]["name"]({bbox});
      node["office"="administrative"]["name"]({bbox});
      node["amenity"="courthouse"]["name"]({bbox});
      node["amenity"="townhall"]["name"]({bbox});
      way["industrial"]["name"]({bbox});
      way["man_made"="works"]["name"]({bbox});
    );
    out tags center;
    """)

def _block_activities_outdoor(bbox: str) -> List[Dict]:
    return _overpass_post(f"""
    [out:json][timeout:60];
    (
      node["leisure"="swimming_pool"]["name"]({bbox});
      node["amenity"="boat_rental"]["name"]({bbox});
      node["leisure"="golf_course"]["name"]({bbox});
      node["sport"]["name"]({bbox});
      node["tourism"="viewpoint"]["name"]({bbox});
      node["tourism"="camp_site"]["name"]({bbox});
      node["tourism"="picnic_site"]["name"]({bbox});
      node["tourism"="information"]["name"]({bbox});
      node["tourism"="artwork"]["name"]({bbox});
      node["tourism"="zoo"]["name"]({bbox});
      node["tourism"="aquarium"]["name"]({bbox});
      node["tourism"="theme_park"]["name"]({bbox});
      way["tourism"="viewpoint"]["name"]({bbox});
      way["leisure"="golf_course"]["name"]({bbox});
    );
    out tags center;
    """)


# Query blocks — map of label → function
QUERY_BLOCKS = [
    ("places_tourism",        _block_places_tourism),
    ("food_drink",            _block_food_drink),
    ("accommodation",         _block_accommodation),
    ("worship",               _block_worship),
    ("nature",                _block_nature),
    ("markets_shopping",      _block_markets_shopping),
    ("education",             _block_education),
    ("health_emergency",      _block_health_emergency),
    ("transport",             _block_transport),
    ("culture_community",     _block_culture_community),
    ("industry_infrastructure",_block_industry_infrastructure),
    ("activities_outdoor",    _block_activities_outdoor),
]


def fetch_osm_deep(bbox_str: str,
                   output_path: str = "data_storage/mangalore_raw.json") -> Dict:
    """
    Main entry point called by rare_data_orchestrator.

    Args:
        bbox_str:    "south,west,north,east"  e.g. "12.78,74.75,13.05,75.05"
        output_path: where to save result JSON

    Returns:
        The saved data dict.
    """
    print(f"\n  OSM Deep Collector — bbox: {bbox_str}")
    print(f"  Fetching {len(QUERY_BLOCKS)} thematic blocks...")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    all_elements: List[Dict] = []
    seen_ids = set()

    for i, (label, fn) in enumerate(QUERY_BLOCKS, 1):
        print(f"    [{i:02d}/{len(QUERY_BLOCKS)}] {label}...", end=" ", flush=True)
        try:
            elements = fn(bbox_str)
        except Exception as e:
            print(f"FAILED: {e}")
            elements = []

        # Deduplicate by OSM id
        new = 0
        for el in elements:
            eid = el.get("id")
            if eid and eid not in seen_ids:
                # Keep only named elements
                if el.get("tags", {}).get("name"):
                    seen_ids.add(eid)
                    all_elements.append(el)
                    new += 1

        print(f"{new} new  (total: {len(all_elements)})")

    # Normalise: ensure every element has lat/lon at top level
    for el in all_elements:
        if el.get("type") == "way" and "center" in el:
            el.setdefault("lat", el["center"].get("lat"))
            el.setdefault("lon", el["center"].get("lon"))

    result = {
        "city_id":       _city_id_from_path(output_path),
        "bbox":          bbox_str,
        "generated_at":  _now(),
        "total":         len(all_elements),
        "block_labels":  [b[0] for b in QUERY_BLOCKS],
        "elements":      all_elements,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n  ✓ OSM Deep — {len(all_elements)} unique named places")
    print(f"  Saved → {output_path}  ({size_kb:.0f} KB)")

    return result


def _city_id_from_path(path: str) -> str:
    base = os.path.basename(path)       # mangalore_raw.json
    return base.replace("_raw.json","").replace(".json","")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox",   default="12.78,74.75,13.05,75.05")
    parser.add_argument("--output", default="data_storage/mangalore_raw.json")
    args = parser.parse_args()
    fetch_osm_deep(bbox_str=args.bbox, output_path=args.output)