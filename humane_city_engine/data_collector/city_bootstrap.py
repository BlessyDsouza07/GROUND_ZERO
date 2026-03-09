"""
data_collector/city_bootstrap.py  [SCALABLE VERSION]

Generic city bootstrap — works for ANY city by reading a CityProfile.

USAGE:
  # Bootstrap Mangalore (default):
  python -m data_collector.city_bootstrap

  # Bootstrap any other city:
  python -m data_collector.city_bootstrap --city mysore
  python -m data_collector.city_bootstrap --city goa
  python -m data_collector.city_bootstrap --city udupi

  # Bootstrap multiple cities:
  python -m data_collector.city_bootstrap --city mangalore mysore goa

HOW TO ADD A NEW CITY:
  1. Create city_profiles/<cityname>_profile.py
  2. Define a CityProfile object (use mangalore_profile.py as template)
  3. Register it in CITY_REGISTRY below (one line)
  4. Run: python -m data_collector.city_bootstrap --city <cityname>
  That's it. No other files need changing.
"""

import argparse
import os
import sys

from config.city_boundary import fetch_city_boundary
from data_collector.get_area_id import get_area_id_for_profile
from data_collector.osm_places import fetch_osm_places
from data_collector.normalizer import normalize_to_entities
from data_collector.generic_places_collector import build_extended_places_dataset
from data_collector.generic_specialty_collector import build_specialty_dataset
from data_collector.generic_trend_collector import build_trend_dataset

from data_core.pipeline import DataCorePipeline
from data_core.data_hub_builder import DataHubBuilder

from city_profiles.city_profile import CityProfile


# ============================================================
# CITY REGISTRY — add new cities here (one line each)
# ============================================================

def _load_registry():
    """
    Loads all available city profiles.
    Import is deferred so missing profile files don't crash the whole app.
    """
    registry = {}

    try:
        from city_profiles.mangalore_profile import MANGALORE
        registry["mangalore"] = MANGALORE
    except ImportError:
        pass

    # ── ADD NEW CITIES HERE ────────────────────────────────────
    # Copy these lines and fill in your city:
    #
    # try:
    #     from city_profiles.mysore_profile import MYSORE
    #     registry["mysore"] = MYSORE
    # except ImportError:
    #     pass
    #
    # try:
    #     from city_profiles.goa_profile import GOA
    #     registry["goa"] = GOA
    # except ImportError:
    #     pass
    #
    # try:
    #     from city_profiles.udupi_profile import UDUPI
    #     registry["udupi"] = UDUPI
    # except ImportError:
    #     pass

    return registry


# ============================================================
# SINGLE CITY BOOTSTRAP
# ============================================================

def bootstrap_city(profile: CityProfile, skip_osm: bool = False):
    """
    Run the complete data collection pipeline for one city.

    Steps:
    1. Fetch city boundary (GeoJSON)
    2. Get OSM area_id (from profile or dynamic lookup)
    3. Fetch ALL OSM place data (comprehensive tags)
    4. Normalize into BaseEntity objects (rich subcategories)
    5. Run DataCorePipeline (scoring)
    6. Build Data Hub
    7. Build extended places dataset (curated + targeted OSM)
    8. Build specialty dataset (local foods, must-visit)
    9. Build trend dataset (Wikipedia pageviews + RSS)

    Args:
        profile:   CityProfile for the target city
        skip_osm:  If True, skip OSM fetch (use cached raw file) — speeds up re-runs
    """

    city = profile.display_name
    print(f"\n{'='*55}")
    print(f"  City Bootstrap: {city}")
    print(f"  City ID:        {profile.city_id}")
    print(f"  Bbox:           {profile.bbox_str}")
    print(f"{'='*55}\n")

    os.makedirs("data_storage", exist_ok=True)
    os.makedirs("data_core", exist_ok=True)
    os.makedirs("config", exist_ok=True)

    # ── STEP 1: City boundary ──────────────────────────────────
    print("Step 1/9: Fetching city boundary...")
    try:
        fetch_city_boundary(
            city_name=profile.full_name,
            output_path=profile.boundary_path
        )
    except Exception as e:
        print(f"  Boundary fetch failed (non-fatal): {e}")

    # ── STEP 2: OSM area_id ────────────────────────────────────
    print("Step 2/9: Resolving OSM area ID...")
    area_id = get_area_id_for_profile(profile)
    print(f"  area_id = {area_id}")

    # ── STEP 3: Raw OSM data ───────────────────────────────────
    if skip_osm and os.path.exists(profile.raw_osm_path):
        print(f"Step 3/9: Skipping OSM fetch — using cached {profile.raw_osm_path}")
    else:
        print("Step 3/9: Fetching comprehensive OSM place data...")
        fetch_osm_places(
            area_id=area_id,
            bbox_str=profile.bbox_str,
            output_path=profile.raw_osm_path
        )

    # ── STEP 4: Normalize ──────────────────────────────────────
    print("Step 4/9: Normalizing entities...")
    entities = normalize_to_entities(raw_file_path=profile.raw_osm_path)

    # ── STEP 5: DataCorePipeline ───────────────────────────────
    print("Step 5/9: Running Data Core pipeline...")
    pipeline = DataCorePipeline()
    scored_entities = pipeline.run(entities)

    # ── STEP 6: Data Hub ───────────────────────────────────────
    print("Step 6/9: Building Data Hub...")
    hub_builder = DataHubBuilder()
    data_hub = hub_builder.build(scored_entities)
    hub_builder.save(data_hub, profile.data_hub_path)
    print(f"  Saved → {profile.data_hub_path}")

    # ── STEP 7: Extended places (curated + targeted OSM) ───────
    print("Step 7/9: Building extended places dataset...")
    build_extended_places_dataset(profile)

    # ── STEP 8: Specialty dataset (food + landmarks) ───────────
    print("Step 8/9: Building specialty dataset...")
    build_specialty_dataset(profile)

    # ── STEP 9: Trend dataset (Wikipedia + RSS) ────────────────
    print("Step 9/9: Building trend dataset...")
    build_trend_dataset(profile)

    print(f"\n{'='*55}")
    print(f"  ✓ {city} bootstrap COMPLETE")
    print(f"  Data hub:      {profile.data_hub_path}")
    print(f"  Places:        {profile.places_extended_path}")
    print(f"  Specialties:   {profile.specialties_path}")
    print(f"  Trends:        {profile.trends_path}")
    print(f"{'='*55}\n")

    return data_hub


# ============================================================
# CLI ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap city data for the Humane City Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m data_collector.city_bootstrap
  python -m data_collector.city_bootstrap --city mangalore
  python -m data_collector.city_bootstrap --city mysore
  python -m data_collector.city_bootstrap --city mangalore mysore goa
  python -m data_collector.city_bootstrap --city mangalore --skip-osm
  python -m data_collector.city_bootstrap --list
        """
    )

    parser.add_argument(
        "--city",
        nargs="+",
        default=["mangalore"],
        help="City ID(s) to bootstrap. Default: mangalore"
    )
    parser.add_argument(
        "--skip-osm",
        action="store_true",
        help="Skip OSM fetch and use cached raw file (faster for re-runs)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available cities and exit"
    )

    args = parser.parse_args()

    registry = _load_registry()

    if args.list:
        print("\nAvailable cities:")
        for city_id, profile in registry.items():
            print(f"  {city_id:<20} {profile.full_name}")
        print(f"\nTotal: {len(registry)} cities")
        print("\nTo add a new city, see: city_profiles/HOWTO_ADD_CITY.md")
        sys.exit(0)

    errors = []
    for city_id in args.city:
        city_id = city_id.lower().strip()
        if city_id not in registry:
            print(f"\n  ERROR: City '{city_id}' not found in registry.")
            print(f"  Available: {', '.join(registry.keys())}")
            print(f"  To add '{city_id}': see city_profiles/HOWTO_ADD_CITY.md")
            errors.append(city_id)
            continue

        profile = registry[city_id]
        try:
            bootstrap_city(profile, skip_osm=args.skip_osm)
        except Exception as e:
            print(f"\n  ERROR bootstrapping {city_id}: {e}")
            import traceback
            traceback.print_exc()
            errors.append(city_id)

    if errors:
        print(f"\nFailed cities: {', '.join(errors)}")
        sys.exit(1)

    print(f"\nAll cities bootstrapped successfully.")


if __name__ == "__main__":
    main()