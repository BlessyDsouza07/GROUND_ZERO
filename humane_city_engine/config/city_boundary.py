"""
city_boundary.py

Fetches city boundary GeoJSON from OpenStreetMap Nominatim API.

Usage:
    boundary = fetch_city_boundary("Mangalore, Karnataka, India")

This module:
- Is reusable
- Handles API errors
- Saves boundary to file
- Returns boundary object
- Is compatible with full ingestion pipeline
"""

import requests
import json
import os
import time
from typing import Dict


# ============================================================
# CONFIGURATION
# ============================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "HumaneCityEngine/1.0 (educational project)"


# ============================================================
# MAIN FUNCTION
# ============================================================

def fetch_city_boundary(
    city_name: str,
    output_path: str = "config/city_boundary.geojson"
) -> Dict:
    """
    Fetch GeoJSON boundary for a given city.

    Args:
        city_name (str): Full city name with region and country
        output_path (str): Where to save the GeoJSON

    Returns:
        Dict: GeoJSON boundary object
    """

    if not city_name or not isinstance(city_name, str):
        raise ValueError("city_name must be a valid string.")

    # Ensure config directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    params = {
        "q": city_name,
        "format": "json",
        "polygon_geojson": 1
    }

    headers = {
        "User-Agent": USER_AGENT
    }

    # Respect Nominatim rate limits
    time.sleep(1)

    try:
        response = requests.get(
            NOMINATIM_URL,
            params=params,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch city boundary: {e}")

    data = response.json()

    if not data:
        raise ValueError(f"No boundary found for city: {city_name}")

    geojson = data[0].get("geojson")

    if not geojson:
        raise ValueError("GeoJSON boundary not available in response.")

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    return geojson


# ============================================================
# OPTIONAL CLI EXECUTION
# ============================================================

if __name__ == "__main__":

    city = "Mangalore, Karnataka, India"

    boundary = fetch_city_boundary(
        city_name=city,
        output_path="config/mangalore_boundary.geojson"
    )

    print("✅ Boundary successfully fetched and saved.")


