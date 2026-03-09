"""
data_collector/generic_places_collector.py  [SCALABLE VERSION]

Builds the extended places dataset for ANY city using its CityProfile.
Combines curated landmark seeds with targeted OSM queries.

Output: data_core/<city_id>_places_extended.json
"""

import requests
import json
import os
import time
from typing import List, Dict
from datetime import datetime

from city_profiles.city_profile import CityProfile, LandmarkSeed

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "HumaneCityEngine/3.0 (open-source city guide)"}


def _osm_query(query: str) -> List[Dict]:
    """Run Overpass query, rotate mirrors on failure."""
    for mirror in OVERPASS_MIRRORS:
        try:
            time.sleep(2)
            resp = requests.post(mirror, data={"data": query}, headers=HEADERS, timeout=60)
            if resp.status_code in (429, 503, 504):
                time.sleep(5)
                continue
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception:
            time.sleep(3)
    return []


def _fetch_food_spots_osm(bbox: str) -> List[Dict]:
    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"~"restaurant|cafe|fast_food|bar|pub|food_court|ice_cream|juice_bar|sweet_shop|bakery|snack_bar|dhaba|canteen|street_vendor|biryani_house|seafood"]({bbox});
      way["amenity"~"restaurant|cafe|fast_food|bakery|food_court"]({bbox});
      node["cuisine"]({bbox});
      node["shop"~"bakery|confectionery|seafood|fish|spices|deli|beverages"]({bbox});
    );
    out tags center;
    """
    elements = _osm_query(query)
    return [e for e in elements if e.get("tags", {}).get("name")]


def _fetch_accommodation_osm(bbox: str) -> List[Dict]:
    query = f"""
    [out:json][timeout:60];
    (
      node["tourism"~"hotel|hostel|guest_house|motel|resort|camp_site|apartment|homestay"]({bbox});
      way["tourism"~"hotel|resort|guest_house"]({bbox});
      node["building"="hotel"]({bbox});
      way["building"="hotel"]({bbox});
    );
    out tags center;
    """
    elements = _osm_query(query)
    return [e for e in elements if e.get("tags", {}).get("name")]


def _landmarks_by_category(landmarks: List[LandmarkSeed]) -> Dict[str, List]:
    """Group landmarks by their category_group (domain-based)."""
    groups: Dict[str, List] = {}
    for lm in landmarks:
        # Derive group from subcategory
        sc = lm.subcategory.lower()
        if "beach" in sc:           group = "beaches"
        elif "temple" in sc or "shrine" in sc: group = "temples"
        elif "church" in sc or "chapel" in sc: group = "churches"
        elif "mosque" in sc or "dargah" in sc: group = "mosques"
        elif "historic" in sc or "fort" in sc or "lighthouse" in sc or "heritage" in sc: group = "historic_sites"
        elif "park" in sc or "nature" in sc or "mangrove" in sc or "garden" in sc or "river" in sc or "estuary" in sc or "forest" in sc or "waterfall" in sc: group = "nature_spots"
        elif "viewpoint" in sc or "scenic" in sc: group = "viewpoints"
        elif lm.domain == "activities" or "performance" in sc or "sport" in sc or "experience" in sc or "walk" in sc or "boat" in sc or "market" in sc.replace("supermarket",""):
            group = "experiences"
        elif lm.domain == "food" or "restaurant" in sc or "cafe" in sc or "ice cream" in sc or "bakery" in sc or "breakfast" in sc:
            group = "must_eat_spots"
        elif lm.domain == "local" or "market" in sc or "bazaar" in sc or "shopping" in sc or "bakery" in sc:
            group = "shopping_areas"
        elif lm.domain == "stay":
            group = "accommodation"
        else:
            group = "attractions"

        if group not in groups:
            groups[group] = []

        groups[group].append({
            "name": lm.name,
            "subcategory": lm.subcategory,
            "domain": lm.domain,
            "lat": lm.lat,
            "lon": lm.lon,
            "notes": lm.notes,
            "best_time": lm.best_time,
            "tags": lm.tags,
            "wikipedia_title": lm.wikipedia_title,
            "source": "curated_seed",
        })

    return groups


def build_extended_places_dataset(profile: CityProfile) -> Dict:
    """
    Build the extended places dataset for any city.

    Combines:
    - Curated landmark seeds from CityProfile
    - Live OSM food spots query
    - Live OSM accommodation query

    Args:
        profile: CityProfile for the target city

    Returns:
        Dict saved to profile.places_extended_path
    """

    print(f"\n  Building extended places for {profile.display_name}...")
    os.makedirs("data_core", exist_ok=True)

    # Live OSM queries using city's bbox
    print(f"  Fetching food spots from OSM ({profile.bbox_str})...")
    food_osm = _fetch_food_spots_osm(profile.bbox_str)
    print(f"    OSM food spots: {len(food_osm)} named")

    print(f"  Fetching accommodation from OSM...")
    accom_osm = _fetch_accommodation_osm(profile.bbox_str)
    print(f"    OSM accommodation: {len(accom_osm)} named")

    # Curated landmarks grouped by category
    landmark_groups = _landmarks_by_category(profile.landmarks)
    total_curated = len(profile.landmarks)

    def _osm_to_record(e: Dict) -> Dict:
        tags = e.get("tags", {})
        return {
            "name":          tags.get("name", ""),
            "amenity_type":  tags.get("amenity") or tags.get("tourism") or "",
            "cuisine":       tags.get("cuisine", ""),
            "stars":         tags.get("stars", ""),
            "phone":         tags.get("phone") or tags.get("contact:phone", ""),
            "website":       tags.get("website", ""),
            "opening_hours": tags.get("opening_hours", ""),
            "lat":           e.get("lat") or e.get("center", {}).get("lat"),
            "lon":           e.get("lon") or e.get("center", {}).get("lon"),
            "osm_id":        e.get("id"),
            "source":        "osm_live",
        }

    dataset = {
        "city":          profile.display_name,
        "city_id":       profile.city_id,
        "generated_at":  datetime.utcnow().isoformat(),
        "sources": ["OpenStreetMap", "CityProfile Curated Seed"],

        "summary": {
            "curated_landmarks":   total_curated,
            "osm_food_spots":      len(food_osm),
            "osm_accommodation":   len(accom_osm),
            "total": total_curated + len(food_osm) + len(accom_osm),
        },

        # Curated by category
        **landmark_groups,

        # Live OSM data
        "osm_food_spots":    [_osm_to_record(e) for e in food_osm if e.get("tags", {}).get("name")],
        "osm_accommodation": [_osm_to_record(e) for e in accom_osm if e.get("tags", {}).get("name")],
    }

    with open(profile.places_extended_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Extended places saved: {profile.places_extended_path}")
    print(f"    Curated: {total_curated} | OSM food: {len(food_osm)} | OSM accommodation: {len(accom_osm)}")
    print(f"    Categories: {', '.join(landmark_groups.keys())}")

    return dataset


if __name__ == "__main__":
    from city_profiles.mangalore_profile import MANGALORE
    build_extended_places_dataset(MANGALORE)