"""
city_bootstrap.py

Master runner for full city ingestion and Data Hub creation.

Pipeline:
1. Fetch city boundary
2. Get Overpass AREA_ID (hardcoded for Mangalore — no slow API lookup)
3. Fetch raw OSM places (comprehensive — all 30+ tag categories)
4. Normalize into BaseEntity objects (rich subcategories)
5. Run DataCorePipeline
6. Build final Data Hub
7. [NEW] Build extended Mangalore places dataset (curated + targeted OSM)
"""

import os

from config.city_boundary import fetch_city_boundary
from data_collector.get_area_id import get_area_id
from data_collector.osm_places import fetch_osm_places
from data_collector.normalizer import normalize_to_entities
from data_collector.mangalore_places_collector import build_extended_places_dataset

from data_core.pipeline import DataCorePipeline
from data_core.data_hub_builder import DataHubBuilder


def build_city_data_hub(city_full_name: str, city_short_name: str):
    """
    Complete city ingestion and Data Hub generation.

    Args:
        city_full_name: e.g. "Mangalore, Karnataka, India"
        city_short_name: e.g. "Mangalore"
    """

    print("\nStarting City Bootstrap...\n")

    print("Fetching city boundary...")
    fetch_city_boundary(
        city_name=city_full_name,
        output_path=f"config/{city_short_name.lower()}_boundary.geojson"
    )

    print("Getting Overpass AREA_ID...")
    area_id = get_area_id(city_short_name)
    print(f"AREA_ID: {area_id}")

    print("Fetching raw OSM place data (comprehensive)...")
    fetch_osm_places(
        area_id=area_id,
        output_path=f"data_storage/{city_short_name.lower()}_raw.json"
    )

    print("Normalizing entities...")
    entities = normalize_to_entities(
        raw_file_path=f"data_storage/{city_short_name.lower()}_raw.json"
    )

    print("Running Data Core pipeline...")
    pipeline = DataCorePipeline()
    scored_entities = pipeline.run(entities)

    print("Building final Data Hub...")
    hub_builder = DataHubBuilder()
    data_hub = hub_builder.build(scored_entities)

    os.makedirs("data_storage", exist_ok=True)

    hub_output_path = f"data_storage/{city_short_name.lower()}_data_hub.json"
    hub_builder.save(data_hub, hub_output_path)

    print("\nBuilding extended Mangalore places dataset...")
    build_extended_places_dataset()

    print("\n" + "=" * 50)
    print("CITY DATA HUB SUCCESSFULLY BUILT")
    print(f"Main hub:          {hub_output_path}")
    print(f"Extended places:   data_core/mangalore_places_extended.json")
    print("=" * 50)

    return data_hub


if __name__ == "__main__":

    build_city_data_hub(
        city_full_name="Mangalore, Karnataka, India",
        city_short_name="Mangalore"
    )