"""
city_bootstrap.py

Master runner for full city ingestion and Data Hub creation.

Pipeline:
1. Fetch city boundary
2. Get Overpass AREA_ID
3. Fetch raw OSM places
4. Normalize into BaseEntity objects
5. Run DataCorePipeline
6. Build final Data Hub

This file is your official system entry point.
"""

import os

from city_boundary import fetch_city_boundary
from get_area_id import get_area_id
from osm_places import fetch_osm_places
from normalizer import normalize_to_entities

from core.pipeline import DataCorePipeline
from core.data_hub_builder import DataHubBuilder


# ============================================================
# MAIN BOOTSTRAP FUNCTION
# ============================================================

def build_city_data_hub(city_full_name: str, city_short_name: str):
    """
    Complete city ingestion and Data Hub generation.

    Args:
        city_full_name: e.g. "Mangalore, Karnataka, India"
        city_short_name: e.g. "Mangalore"
    """

    print("\n🚀 Starting City Bootstrap...\n")

    # --------------------------------------------------------
    # 1️⃣ Fetch Boundary
    # --------------------------------------------------------
    print("📍 Fetching city boundary...")
    boundary = fetch_city_boundary(
        city_name=city_full_name,
        output_path=f"config/{city_short_name.lower()}_boundary.geojson"
    )

    # --------------------------------------------------------
    # 2️⃣ Get AREA_ID
    # --------------------------------------------------------
    print("🗺 Getting Overpass AREA_ID...")
    area_id = get_area_id(city_short_name)

    print(f"AREA_ID: {area_id}")

    # --------------------------------------------------------
    # 3️⃣ Fetch OSM Places
    # --------------------------------------------------------
    print("🌍 Fetching raw OSM place data...")
    raw_data = fetch_osm_places(
        area_id=area_id,
        output_path=f"data_storage/{city_short_name.lower()}_raw.json"
    )

    # --------------------------------------------------------
    # 4️⃣ Normalize to Entities
    # --------------------------------------------------------
    print("🧠 Normalizing entities...")
    entities = normalize_to_entities(
        raw_file_path=f"data_storage/{city_short_name.lower()}_raw.json"
    )

    # --------------------------------------------------------
    # 5️⃣ Run Data Core Pipeline
    # --------------------------------------------------------
    print("⚙ Running Data Core pipeline...")
    pipeline = DataCorePipeline()
    scored_entities = pipeline.run(entities)

    # --------------------------------------------------------
    # 6️⃣ Build Final Data Hub
    # --------------------------------------------------------
    print("🏗 Building final Data Hub...")
    hub_builder = DataHubBuilder()
    data_hub = hub_builder.build(scored_entities)

    # Save final hub
    os.makedirs("data_storage", exist_ok=True)

    hub_output_path = f"data_storage/{city_short_name.lower()}_data_hub.json"

    hub_builder.save(data_hub, hub_output_path)

    print("\n✅ CITY DATA HUB SUCCESSFULLY BUILT")
    print(f"📦 Output: {hub_output_path}")

    return data_hub


# ============================================================
# CLI EXECUTION
# ============================================================

if __name__ == "__main__":

    build_city_data_hub(
        city_full_name="Mangalore, Karnataka, India",
        city_short_name="Mangalore"
    )
