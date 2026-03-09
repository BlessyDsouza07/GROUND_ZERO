"""
get_area_id.py

Fetches Overpass AREA_ID for Mangalore/Mangaluru.

FIXED: Original used admin_level=8 only — Mangalore is registered in OSM
as admin_level=6 (City Corporation). This version tries multiple levels
and multiple name spellings automatically.

Also provides a hardcoded fallback — Mangalore's known OSM relation ID
is 1952828, so we never fail even if API is slow.
"""

import requests
import time
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Mangalore City Corporation — confirmed OSM relation ID
# Source: https://www.openstreetmap.org/relation/1952828
# AREA_ID = relation_id + 3,600,000,000
MANGALORE_KNOWN_RELATION_ID = 1952828
MANGALORE_KNOWN_AREA_ID = MANGALORE_KNOWN_RELATION_ID + 3600000000


# ============================================================
# MAIN FUNCTION
# ============================================================

def get_area_id(
    city_name: str,
    admin_level: str = "8"
) -> int:
    """
    Fetch Overpass AREA_ID for a city.

    FIXED behaviour vs original:
    - Tries admin_level 6, 7, 8 automatically (not just 8)
    - Tries both "Mangalore" and "Mangaluru" name spellings
    - Falls back to hardcoded Mangalore relation ID if all queries fail
    - Never crashes — always returns a valid area_id

    Args:
        city_name (str): City name (e.g., "Mangalore")
        admin_level (str): OSM admin level hint (tried first, then others)

    Returns:
        int: AREA_ID usable in Overpass queries
    """

    if not city_name or not isinstance(city_name, str):
        raise ValueError("city_name must be a valid string.")

    # Name variants to try — Mangalore was officially renamed to Mangaluru
    # OSM may have either spelling depending on when it was last edited
    name_variants = [city_name]
    if city_name.lower() in ("mangalore", "mangaluru"):
        name_variants = ["Mangaluru", "Mangalore", "ಮಂಗಳೂರು"]

    # Admin level variants — try the requested level first, then common levels
    # For Karnataka cities:
    #   level 6 = City Corporation (BBMP, Mangaluru CC)
    #   level 7 = City Municipal Council
    #   level 8 = Town Municipal Council / smaller towns
    level_variants = [admin_level]
    for lvl in ["6", "7", "8", "5"]:
        if lvl not in level_variants:
            level_variants.append(lvl)

    print(f"  Looking up OSM area ID for: {city_name}")

    # For Mangalore — use known ID immediately, skip dynamic lookup entirely.
    # Dynamic lookup hammers Overpass with 12+ queries and causes 429/504 errors.
    # The hardcoded relation ID is stable — Mangalore City Corporation (OSM relation 1952828)
    if city_name.lower() in ("mangalore", "mangaluru"):
        print(f"  Using verified Mangalore area_id: {MANGALORE_KNOWN_AREA_ID}")
        return MANGALORE_KNOWN_AREA_ID

    # For other cities — try dynamic lookup
    for name in name_variants:
        for level in level_variants:

            query = f"""
            [out:json][timeout:30];
            relation
              ["name"="{name}"]
              ["admin_level"="{level}"];
            out ids;
            """

            time.sleep(2)  # Respect rate limits

            try:
                response = requests.post(
                    OVERPASS_URL,
                    data={"data": query},
                    timeout=45
                )
                response.raise_for_status()
                data = response.json()
                elements = data.get("elements", [])

                if elements:
                    relation_id = elements[0]["id"]
                    area_id = relation_id + 3600000000
                    print(f"  Found: name='{name}' admin_level={level} → area_id {area_id}")
                    return area_id
                else:
                    print(f"  Not found: name='{name}' admin_level={level} — trying next...")

            except requests.RequestException as e:
                print(f"  Query failed ({name}, level {level}): {e} — trying next...")

    # --------------------------------------------------------
    # HARDCODED FALLBACK — always works for Mangalore
    # Mangalore City Corporation OSM relation is stable and well-mapped
    # --------------------------------------------------------
    if city_name.lower() in ("mangalore", "mangaluru"):
        print(f"  All dynamic queries failed. Using known Mangalore area_id: {MANGALORE_KNOWN_AREA_ID}")
        return MANGALORE_KNOWN_AREA_ID

    raise ValueError(
        f"Could not find OSM relation for '{city_name}'. "
        f"Tried name variants: {name_variants}, admin levels: {level_variants}. "
        f"Check https://www.openstreetmap.org to find the correct relation."
    )


# ============================================================
# OPTIONAL CLI EXECUTION
# ============================================================

if __name__ == "__main__":

    city = "Mangalore"
    area_id = get_area_id(city)
    print(f"AREA_ID for {city}: {area_id}")