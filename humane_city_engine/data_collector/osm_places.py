"""
osm_places.py

Fetches raw tourism-related place data from OpenStreetMap
using Overpass API and a valid AREA_ID.

This module:
- Accepts dynamic AREA_ID
- Collects broad tourism + amenity data
- Handles API errors safely
- Saves raw JSON to file
- Returns parsed JSON for pipeline use
"""

import requests
import json
import os
import time
from typing import Dict


# ============================================================
# CONFIGURATION
# ============================================================

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


# ============================================================
# MAIN FUNCTION
# ============================================================

def fetch_osm_places(
    area_id: int,
    output_path: str = "data_storage/raw_places.json"
) -> Dict:
    """
    Fetch tourism and amenity data from OSM.

    Args:
        area_id (int): Valid Overpass AREA_ID
        output_path (str): File to save raw JSON

    Returns:
        Dict: Raw OSM JSON response
    """

    if not isinstance(area_id, int):
        raise ValueError("area_id must be an integer.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    query = f"""
    [out:json][timeout:120];
    area({area_id})->.searchArea;

    (
      node["tourism"](area.searchArea);
      node["amenity"](area.searchArea);
      node["historic"](area.searchArea);
      node["natural"](area.searchArea);
      node["leisure"](area.searchArea);
      node["shop"](area.searchArea);

      way["tourism"](area.searchArea);
      way["amenity"](area.searchArea);
      way["historic"](area.searchArea);
      way["natural"](area.searchArea);
      way["leisure"](area.searchArea);
      way["shop"](area.searchArea);
    );

    out tags center;
    """

    # Respect Overpass usage policy
    time.sleep(1)

    try:
        response = requests.post(
            OVERPASS_URL,
            data=query,
            timeout=180
        )
        response.raise_for_status()

    except requests.RequestException as e:
        raise RuntimeError(f"Overpass API request failed: {e}")

    data = response.json()

    if "elements" not in data:
        raise ValueError("Unexpected Overpass response format.")

    # Save raw data
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Raw OSM data collected: {len(data['elements'])} elements")

    return data


# ============================================================
# OPTIONAL CLI EXECUTION
# ============================================================

if __name__ == "__main__":

    from get_area_id import get_area_id

    city = "Mangalore"

    area_id = get_area_id(city)

    fetch_osm_places(
        area_id=area_id,
        output_path="data_storage/raw_places.json"
    )
