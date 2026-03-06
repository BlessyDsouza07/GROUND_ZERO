"""
get_area_id.py

Fetches Overpass AREA_ID for a given city name.

This module:
- Queries Overpass API
- Converts relation ID to AREA_ID
- Is reusable
- Handles errors safely
- Compatible with osm_places.py
"""

import requests
import time
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


# ============================================================
# MAIN FUNCTION
# ============================================================

def get_area_id(
    city_name: str,
    admin_level: str = "8"
) -> int:
    """
    Fetch Overpass AREA_ID for a city.

    Args:
        city_name (str): City name (e.g., "Mangalore")
        admin_level (str): OSM admin level (default: 8)

    Returns:
        int: AREA_ID usable in Overpass queries
    """

    if not city_name or not isinstance(city_name, str):
        raise ValueError("city_name must be a valid string.")

    query = f"""
    [out:json][timeout:30];
    relation
      ["name"="{city_name}"]
      ["admin_level"="{admin_level}"];
    out ids;
    """

    # Respect API usage
    time.sleep(1)

    try:
        response = requests.post(
            OVERPASS_URL,
            data=query,
            timeout=60
        )
        response.raise_for_status()

    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch AREA_ID: {e}")

    data = response.json()

    elements = data.get("elements", [])

    if not elements:
        raise ValueError(
            f"No relation found for city '{city_name}' "
            f"with admin_level={admin_level}"
        )

    relation_id = elements[0]["id"]

    # Convert relation ID to AREA_ID
    # Overpass area_id formula:
    # AREA_ID = relation_id + 3600000000
    area_id = relation_id + 3600000000

    return area_id


# ============================================================
# OPTIONAL CLI EXECUTION
# ============================================================

if __name__ == "__main__":

    city = "Mangalore"

    area_id = get_area_id(city)

    print(f"✅ AREA_ID for {city}: {area_id}")
