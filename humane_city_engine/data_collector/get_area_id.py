"""
data_collector/get_area_id.py  [SCALABLE VERSION]

Resolves Overpass area_id for any city via CityProfile.

Priority order:
1. Use profile.osm_area_id (computed from known relation_id) — instant, no API
2. Try each name variant × admin level — dynamic lookup
3. Raise clear error with help message
"""

import requests
import time
from typing import Optional

from city_profiles.city_profile import CityProfile


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def get_area_id_for_profile(profile: CityProfile) -> int:
    """
    Resolve Overpass area_id for a city using its CityProfile.

    For Mangalore (and any city with a known relation_id),
    this returns instantly without any API call.

    Args:
        profile: CityProfile for the target city

    Returns:
        int: area_id for use in Overpass queries
    """

    # ── FAST PATH: known relation_id in profile ────────────────
    if profile.osm_area_id:
        print(f"  Using known area_id from profile: {profile.osm_area_id}")
        return profile.osm_area_id

    # ── DYNAMIC LOOKUP: try name variants × admin levels ───────
    print(f"  Dynamic OSM lookup for: {profile.display_name}")

    name_variants = profile.name_variants or [profile.display_name]
    admin_levels = profile.osm_admin_levels or ["6", "7", "8"]

    for name in name_variants:
        for level in admin_levels:
            query = f"""
            [out:json][timeout:30];
            relation["name"="{name}"]["admin_level"="{level}"];
            out ids;
            """
            time.sleep(2)

            try:
                resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=45)
                resp.raise_for_status()
                elements = resp.json().get("elements", [])

                if elements:
                    relation_id = elements[0]["id"]
                    area_id = relation_id + 3600000000
                    print(f"  Found: '{name}' admin_level={level} → area_id {area_id}")
                    print(f"  TIP: Add osm_relation_id={relation_id} to {profile.city_id}_profile.py to skip this lookup next time.")
                    return area_id
                else:
                    print(f"  Not found: '{name}' admin_level={level}")

            except requests.RequestException as e:
                print(f"  Query failed ({name}, level {level}): {e}")

    raise ValueError(
        f"Could not resolve OSM area_id for '{profile.display_name}'.\n"
        f"Tried names: {name_variants}\n"
        f"Tried admin levels: {admin_levels}\n"
        f"Fix: Go to https://www.openstreetmap.org, search '{profile.display_name}', \n"
        f"click the city boundary relation, note the relation ID, \n"
        f"then add osm_relation_id=<id> to {profile.city_id}_profile.py"
    )


# Backwards-compatible wrapper for old callers
def get_area_id(city_name: str, admin_level: str = "8") -> int:
    """Legacy function — prefer get_area_id_for_profile() for new code."""
    from city_profiles.mangalore_profile import MANGALORE
    if city_name.lower() in ("mangalore", "mangaluru"):
        return MANGALORE.osm_area_id
    raise ValueError(f"Unknown city: {city_name}. Use get_area_id_for_profile() with a CityProfile.")