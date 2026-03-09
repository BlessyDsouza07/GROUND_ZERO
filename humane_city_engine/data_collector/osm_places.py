"""
data_collector/osm_places.py

OSM place fetcher — supports both old (area_id) and new (bbox_str) calling styles.

This file is a compatibility bridge:
  - OLD callers (original city_bootstrap): fetch_osm_places(area_id, output_path)
  - NEW callers (scalable city_bootstrap): fetch_osm_places(area_id, bbox_str, output_path)
  - rare_data_orchestrator uses osm_deep_collector.py directly (90+ tags)

For the basic bootstrap pipeline, this file runs a solid 12-tag OSM query.
For the deep rare data collection, use osm_deep_collector.py instead.
"""

import requests
import json
import os
import time
from typing import Dict, Optional

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def fetch_osm_places(
    area_id:     Optional[int] = None,
    bbox_str:    Optional[str] = None,
    output_path: str = "data_storage/raw_places.json",
) -> Dict:
    """
    Fetch tourism and amenity place data from OpenStreetMap Overpass API.

    Args:
        area_id:     Overpass area_id (optional if bbox_str provided)
        bbox_str:    Bounding box "south,west,north,east" (optional if area_id provided)
        output_path: File path to save raw JSON result

    Returns:
        Dict: Raw OSM JSON response

    Note:
        For comprehensive 90+ tag collection, use osm_deep_collector.py.
        This function runs a standard 12-category query suitable for the
        basic bootstrap pipeline.
    """

    if area_id is None and bbox_str is None:
        raise ValueError("Either area_id or bbox_str must be provided.")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    # Build query — prefer area_id (faster), fall back to bbox
    if area_id:
        scope = f"area({area_id})->.searchArea;"
        filter_suffix = "(area.searchArea)"
    else:
        filter_suffix = f"({bbox_str})"
        scope = ""

    query = f"""
    [out:json][timeout:120];
    {scope}
    (
      node["tourism"]{filter_suffix};
      node["amenity"]{filter_suffix};
      node["historic"]{filter_suffix};
      node["natural"]{filter_suffix};
      node["leisure"]{filter_suffix};
      node["shop"]{filter_suffix};
      node["craft"]{filter_suffix};
      node["sport"]{filter_suffix};
      node["waterway"~"dock|jetty|waterfall|dam|weir"]{filter_suffix};
      node["man_made"~"lighthouse|tower|pier|jetty|windmill"]{filter_suffix};

      way["tourism"]{filter_suffix};
      way["amenity"]{filter_suffix};
      way["historic"]{filter_suffix};
      way["natural"]{filter_suffix};
      way["leisure"]{filter_suffix};
      way["shop"]{filter_suffix};
    );
    out tags center;
    """

    print(f"  Fetching OSM data (scope: {'area_id=' + str(area_id) if area_id else 'bbox=' + str(bbox_str)[:30]}...)")
    time.sleep(3)  # Respect Overpass usage policy

    last_error = None
    for mirror in OVERPASS_MIRRORS:
        try:
            response = requests.post(
                mirror,
                data={"data": query},
                headers={"User-Agent": "HumaneCityEngine/3.0 (non-commercial city guide)"},
                timeout=180
            )
            if response.status_code in (429, 503, 504):
                print(f"  Mirror {mirror[:35]}... rate limited, trying next")
                time.sleep(8)
                continue
            response.raise_for_status()

            data = response.json()
            if "elements" not in data:
                raise ValueError("Unexpected Overpass response format.")

            named = sum(1 for e in data["elements"] if e.get("tags", {}).get("name"))

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"  ✓ OSM data: {len(data['elements'])} elements ({named} named) → {output_path}")
            return data

        except requests.RequestException as e:
            last_error = e
            print(f"  Mirror failed: {e} — trying next")
            time.sleep(5)

    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_error}")


if __name__ == "__main__":
    from data_collector.get_area_id import get_area_id
    area_id = get_area_id("Mangalore")
    fetch_osm_places(area_id=area_id, output_path="data_storage/mangalore_raw.json")