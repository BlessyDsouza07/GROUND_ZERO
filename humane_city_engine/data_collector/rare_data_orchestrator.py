"""
data_collector/rare_data_orchestrator.py

RARE DATA ORCHESTRATOR — runs all deep collectors and merges into one enriched store.

USAGE:
  python -m data_collector.rare_data_orchestrator --city mangalore
  python -m data_collector.rare_data_orchestrator --city mangalore --skip-existing
  python -m data_collector.rare_data_orchestrator --city mangalore --collectors osm wikidata
  python -m data_collector.rare_data_orchestrator --city mangalore --merge-only
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
from typing import Dict, List


# ============================================================
# SELF-CONTAINED CITY REGISTRY
# (No dependency on new city_bootstrap — works standalone)
# ============================================================

def _load_registry():
    """Load available city profiles. Self-contained — no city_bootstrap needed."""
    registry = {}

    try:
        from city_profiles.mangalore_profile import MANGALORE
        registry["mangalore"] = MANGALORE
    except ImportError:
        pass

    # Add new cities here as you create their profiles:
    # try:
    #     from city_profiles.mysore_profile import MYSORE
    #     registry["mysore"] = MYSORE
    # except ImportError:
    #     pass

    return registry


# ============================================================
# INDIVIDUAL COLLECTOR RUNNERS
# ============================================================

def run_osm_deep(profile, skip_existing: bool = False) -> str:
    path = profile.raw_osm_path
    if skip_existing and os.path.exists(path):
        print(f"  [OSM] Skipping — using existing {path}")
        return path
    from data_collector.osm_deep_collector import fetch_osm_deep
    fetch_osm_deep(bbox_str=profile.bbox_str, output_path=path)
    return path


def run_wikidata(profile, skip_existing: bool = False) -> str:
    path = f"data_core/{profile.city_id}_wikidata.json"
    if skip_existing and os.path.exists(path):
        print(f"  [Wikidata] Skipping — using existing {path}")
        return path
    from data_collector.wikidata_deep_collector import collect_wikidata_deep
    collect_wikidata_deep(
        city_name    = profile.display_name,
        state        = profile.state,
        country_code = profile.country_code,
        output_path  = path,
        profile_qid  = getattr(profile, "wikidata_qid", None),
    )
    return path


def run_commons(profile, skip_existing: bool = False) -> str:
    path = f"data_core/{profile.city_id}_media.json"
    if skip_existing and os.path.exists(path):
        print(f"  [Commons] Skipping — using existing {path}")
        return path
    from data_collector.commons_media_collector import (
        collect_media_for_city, build_commons_categories_for_city
    )
    cats = build_commons_categories_for_city(profile.city_id, profile.display_name)
    collect_media_for_city(
        city_name          = profile.display_name,
        commons_categories = cats,
        wikipedia_articles = profile.wikipedia_articles[:12],
        output_path        = path,
    )
    return path


def run_open_govt(profile, skip_existing: bool = False) -> str:
    path = f"data_core/{profile.city_id}_open_data.json"
    if skip_existing and os.path.exists(path):
        print(f"  [OpenGovt] Skipping — using existing {path}")
        return path
    from data_collector.open_govt_collector import collect_open_govt_data
    is_coastal = any("beach" in lm.subcategory.lower() for lm in profile.landmarks)
    collect_open_govt_data(
        city_name   = profile.display_name,
        state       = profile.state,
        lat         = profile.center_lat,
        lon         = profile.center_lon,
        bbox_str    = profile.bbox_str,
        output_path = path,
        is_coastal  = is_coastal,
    )
    return path


def run_wikipedia_deep(profile, skip_existing: bool = False) -> str:
    path = f"data_core/{profile.city_id}_wikipedia_deep.json"
    if skip_existing and os.path.exists(path):
        print(f"  [Wikipedia] Skipping — using existing {path}")
        return path
    from data_collector.wikipedia_deep_miner import mine_wikipedia_deep
    mine_wikipedia_deep(
        primary_articles = profile.wikipedia_articles,
        city_name        = profile.display_name,
        output_path      = path,
    )
    return path


def run_trends(profile, skip_existing: bool = False) -> str:
    path = profile.trends_path
    if skip_existing and os.path.exists(path):
        print(f"  [Trends] Skipping — using existing {path}")
        return path
    from data_collector.generic_trend_collector import build_trend_dataset
    build_trend_dataset(profile)
    return path


# ============================================================
# MERGER
# ============================================================

def merge_all_sources(profile) -> Dict:
    print(f"\n  Merging all rare data sources for {profile.display_name}...")
    os.makedirs("data_core", exist_ok=True)

    merged = {
        "city":         profile.display_name,
        "city_id":      profile.city_id,
        "generated_at": _now_iso(),
        "sources":      [],
        "places":       {},
        "wildlife":     [],
        "marine_life":  [],
        "air_quality":  {},
        "media":        {},
        "wikipedia":    {},
        "trends":       {},
        "wikidata":     {},
    }

    def _load(path: str) -> Dict:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _add_place(name: str, data: Dict, source: str):
        if not name or len(name.strip()) < 2:
            return
        key = name.strip().lower()
        if key not in merged["places"]:
            merged["places"][key] = {"name": name, "sources": [], "data": {}}
        merged["places"][key]["sources"].append(source)
        merged["places"][key]["data"][source] = data

    # OSM
    osm_raw = _load(profile.raw_osm_path)
    if osm_raw.get("elements"):
        merged["sources"].append("OpenStreetMap")
        for el in osm_raw["elements"]:
            name = el.get("tags", {}).get("name")
            if name:
                _add_place(name, {
                    "lat":  el.get("lat") or el.get("center", {}).get("lat"),
                    "lon":  el.get("lon") or el.get("center", {}).get("lon"),
                    "tags": el.get("tags", {}),
                }, "osm")

    # Wikidata
    wd = _load(f"data_core/{profile.city_id}_wikidata.json")
    if wd:
        merged["sources"].append("Wikidata")
        merged["wikidata"] = {k: wd.get(k, []) for k in [
            "heritage_structures", "places_of_worship", "educational_institutions",
            "notable_persons", "local_foods", "festivals", "organisations",
            "infrastructure", "summary",
        ]}
        for item in wd.get("heritage_structures", []) + wd.get("places_of_worship", []):
            _add_place(item.get("itemLabel", ""), item, "wikidata")

    # Open Govt
    og = _load(f"data_core/{profile.city_id}_open_data.json")
    if og:
        merged["sources"].append("Open Government / Science APIs")
        merged["wildlife"]    = og.get("species_wildlife", [])
        merged["marine_life"] = og.get("marine_species", [])
        merged["air_quality"] = og.get("air_quality", {})
        for mon in og.get("asi_monuments", []):
            _add_place(mon.get("name", ""), mon, "asi")

    # Wikipedia
    wp = _load(f"data_core/{profile.city_id}_wikipedia_deep.json")
    if wp:
        merged["sources"].append("Wikipedia")
        merged["wikipedia"] = {
            "nearby_places":     wp.get("nearby_geo_places", []),
            "food_mentions":     wp.get("food_mentions", []),
            "place_mentions":    wp.get("place_mentions", []),
            "historical_events": wp.get("historical_events", []),
            "article_count":     len(wp.get("articles", {})),
        }
        for place in wp.get("nearby_geo_places", []):
            _add_place(place.get("name", ""), place, "wikipedia_geo")

    # Media
    media = _load(f"data_core/{profile.city_id}_media.json")
    if media:
        merged["sources"].append("Wikimedia Commons")
        merged["media"] = {
            "photos_count":     len(media.get("commons_photos", [])),
            "wikipedia_images": len(media.get("wikipedia_images", [])),
            "sample_photos":    media.get("commons_photos", [])[:20],
        }

    # Trends
    trends = _load(profile.trends_path)
    if trends:
        merged["trends"] = {
            "wikipedia_articles_tracked": len(trends.get("wikipedia_trends", [])),
            "rss_articles":               len(trends.get("rss_articles", [])),
            "top_trending": sorted(
                trends.get("wikipedia_trends", []),
                key=lambda x: x.get("wikipedia_views_30d", 0),
                reverse=True
            )[:10],
        }

    # Stats
    total_places  = len(merged["places"])
    multi_source  = sum(1 for p in merged["places"].values() if len(p["sources"]) > 1)

    merged["summary"] = {
        "total_unique_places":     total_places,
        "multi_source_verified":   multi_source,
        "single_source_only":      total_places - multi_source,
        "wildlife_species":        len(merged.get("wildlife", [])),
        "marine_species":          len(merged.get("marine_life", [])),
        "media_photos":            merged.get("media", {}).get("photos_count", 0),
        "data_sources_used":       len(set(merged["sources"])),
    }

    # Convert places dict → sorted list
    output_path = f"data_core/{profile.city_id}_rare_enriched.json"
    merged_save  = dict(merged)
    merged_save["places"] = sorted(
        merged["places"].values(),
        key=lambda p: -len(p["sources"])
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged_save, f, ensure_ascii=False, indent=2)

    print(f"\n  ✓ Rare enriched dataset → {output_path}")
    print(f"    Unique places:        {total_places}")
    print(f"    Multi-source verified:{multi_source}")
    print(f"    Sources used:         {len(set(merged['sources']))}")
    return merged


# ============================================================
# CLI
# ============================================================

ALL_COLLECTORS = ["osm", "wikidata", "commons", "govt", "wikipedia", "trends"]


def main():
    parser = argparse.ArgumentParser(
        description="Run rare data collectors for a city",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m data_collector.rare_data_orchestrator --city mangalore
  python -m data_collector.rare_data_orchestrator --city mangalore --skip-existing
  python -m data_collector.rare_data_orchestrator --city mangalore --collectors osm wikidata govt
  python -m data_collector.rare_data_orchestrator --city mangalore --merge-only
        """
    )
    parser.add_argument("--city",          default="mangalore")
    parser.add_argument("--collectors",    nargs="+", default=ALL_COLLECTORS,
                        choices=ALL_COLLECTORS)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--merge-only",    action="store_true")
    args = parser.parse_args()

    registry = _load_registry()
    if args.city not in registry:
        print(f"\nERROR: City '{args.city}' not in registry.")
        print(f"Available: {', '.join(registry.keys()) or 'none — check city_profiles/ folder'}")
        print(f"Add a profile: see city_profiles/HOWTO_ADD_CITY.md")
        sys.exit(1)

    profile = registry[args.city]
    os.makedirs("data_core",    exist_ok=True)
    os.makedirs("data_storage", exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  Rare Data Orchestrator: {profile.display_name}")
    print(f"  Collectors: {', '.join(args.collectors)}")
    print(f"{'='*55}")

    if not args.merge_only:
        collector_map = {
            "osm":       lambda: run_osm_deep(profile,      args.skip_existing),
            "wikidata":  lambda: run_wikidata(profile,      args.skip_existing),
            "commons":   lambda: run_commons(profile,       args.skip_existing),
            "govt":      lambda: run_open_govt(profile,     args.skip_existing),
            "wikipedia": lambda: run_wikipedia_deep(profile, args.skip_existing),
            "trends":    lambda: run_trends(profile,        args.skip_existing),
        }

        for name in args.collectors:
            print(f"\n{'─'*40}")
            print(f"  Running: {name.upper()}")
            try:
                path = collector_map[name]()
                print(f"  ✓ {name} complete → {path}")
            except Exception as e:
                print(f"  ✗ {name} FAILED: {e}")
                import traceback
                traceback.print_exc()
                # Continue with remaining collectors even if one fails

    print(f"\n{'─'*40}")
    print(f"  Merging all sources...")
    merge_all_sources(profile)

    print(f"\n{'='*55}")
    print(f"  ✓ DONE: {profile.display_name}")
    print(f"  Main output: data_core/{profile.city_id}_rare_enriched.json")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()