"""
data_storage/unified_store_builder.py

UNIFIED CITY DATA STORE — merges every output file into one clean JSON.

WHAT THIS SOLVES:
  The engine currently produces 11+ separate files:
    - mangalore_raw.json           (OSM raw elements)
    - mangalore_data_hub.json      (scored entities by domain)
    - mangalore_specialties.json   (foods, must-visit, must-eat)
    - mangalore_trends.json        (Wikipedia pageviews + RSS)
    - mangalore_places_extended.json (curated landmarks)
    - mangalore_wikidata.json      (heritage, persons, festivals)
    - mangalore_media.json         (Wikimedia photos)
    - mangalore_open_data.json     (ASI, GBIF wildlife, air quality)
    - mangalore_wikipedia_deep.json (geosearch, timelines, food mentions)
    - mangalore_rare_enriched.json (earlier partial merge)
    - mangalore.db                 (SQLite subset)

  This builder reads ALL of them, merges into one canonical store,
  deduplicates by place name, cross-references sources, and sorts
  every section so the engine (and you) can query one place.

OUTPUT:  data_storage/<city_id>_city_store.json

SCHEMA of city_store.json:
  {
    "meta":        { city info, build timestamp, source inventory }
    "places":      [ unified place entries — deduped, sorted by score ]
    "food":        { dishes, restaurants, street_food, markets }
    "stay":        [ accommodation — all types, sorted by grade ]
    "activities":  [ things to do, sorted by domain then score ]
    "explore":     [ heritage, temples, churches, historic ]
    "local":       [ markets, craft shops, community life ]
    "transport":   [ all mobility options ]
    "emergency":   [ hospitals, police, fire ]
    "people":      [ notable persons from Wikidata ]
    "wildlife":    [ species — birds, animals, marine ]
    "media":       [ photos with attribution ]
    "trends":      [ what's being searched/read right now ]
    "festivals":   [ annual events with months ]
    "timeline":    [ historical events sorted by year ]
    "day_trips":   [ nearby cities ]
    "seasons":     { peak, monsoon, best_months }
    "live":        { air quality, current weather context }
    "stats":       { counts per section, source breakdown, coverage score }
  }

USAGE:
  python -m data_storage.unified_store_builder --city mangalore
  python -m data_storage.unified_store_builder --city mangalore --verbose
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: str, label: str = "") -> Dict:
    """Load a JSON file if it exists. Returns empty dict if missing."""
    if not os.path.exists(path):
        if label:
            print(f"    [skip] {label} — file not found: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        size = os.path.getsize(path)
        if label:
            print(f"    [ok]   {label} — {size//1024}KB")
        return data
    except Exception as e:
        print(f"    [err]  {label} — {e}")
        return {}


# ============================================================
# SECTION BUILDERS
# ============================================================

def _build_places(
    data_hub:         Dict,
    osm_raw:          Dict,
    places_extended:  Dict,
    rare_enriched:    Dict,
    wikidata:         Dict,
    wikipedia_deep:   Dict,
    verbose:          bool = False,
) -> List[Dict]:
    """
    Build the unified places list.
    Master deduplication: name (lowercase) is the unique key.
    Merges: data_hub score + OSM tags + curated notes + Wikidata facts + Wikipedia geo.
    Sorted by: authenticity_score desc, then name asc.
    """

    # Index: name_lower → unified record
    index: Dict[str, Dict] = {}

    def _upsert(name: str, update: Dict, source: str):
        if not name or len(name.strip()) < 2:
            return
        key = name.strip().lower()
        if key not in index:
            index[key] = {
                "name":               name.strip(),
                "sources":            [],
                "authenticity_score": 0.0,
                "grade":              "D",
                "domain":             "",
                "subcategory":        "",
                "lat":                None,
                "lon":                None,
                "tags":               {},
                "notes":              "",
                "best_time":          "",
                "phone":              "",
                "website":            "",
                "opening_hours":      "",
                "wikipedia_url":      "",
                "wikidata_url":       "",
                "photo_url":          "",
                "heritage_type":      "",
                "inception_year":     "",
                "architect":          "",
                "religion":           "",
                "wiki_description":   "",
                "extra":              {},
            }
        rec = index[key]
        if source not in rec["sources"]:
            rec["sources"].append(source)
        # Merge — only overwrite if new value is non-empty
        for k, v in update.items():
            if v and not rec.get(k):
                rec[k] = v
            elif k == "authenticity_score" and v > rec.get("authenticity_score", 0):
                rec[k] = v
            elif k == "tags" and isinstance(v, dict):
                rec["tags"].update(v)
            elif k == "sources":
                pass  # handled above

    # ── 1. Data Hub (scored entities — highest quality) ────────
    for domain, entities in data_hub.items():
        if domain in ("generated_at", "city", "city_id", "summary"):
            continue
        for e in (entities if isinstance(entities, list) else []):
            _upsert(e.get("name", ""), {
                "domain":             domain,
                "subcategory":        e.get("subcategory", ""),
                "lat":                e.get("coordinates", {}).get("latitude"),
                "lon":                e.get("coordinates", {}).get("longitude"),
                "authenticity_score": e.get("authenticity_score", 0),
                "grade":              e.get("grade", "D"),
            }, "data_hub")

    # ── 2. OSM raw (coordinates + tags for unnamed-in-hub places) ─
    for el in osm_raw.get("elements", []):
        name = el.get("tags", {}).get("name")
        if name:
            _upsert(name, {
                "lat":   el.get("lat") or el.get("center", {}).get("lat"),
                "lon":   el.get("lon") or el.get("center", {}).get("lon"),
                "tags":  el.get("tags", {}),
                "phone": el.get("tags", {}).get("phone") or el.get("tags", {}).get("contact:phone", ""),
                "website":       el.get("tags", {}).get("website", ""),
                "opening_hours": el.get("tags", {}).get("opening_hours", ""),
            }, "osm")

    # ── 3. Extended places (curated notes + best_time) ─────────
    _SKIP_KEYS = {"city", "city_id", "generated_at", "sources", "summary"}
    for section_key, items in places_extended.items():
        if section_key in _SKIP_KEYS:
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):   # skip bare strings like food names
                continue
            name = item.get("name", "")
            _upsert(name, {
                "domain":       item.get("domain", ""),
                "subcategory":  item.get("subcategory", ""),
                "lat":          item.get("lat"),
                "lon":          item.get("lon"),
                "notes":        item.get("notes", ""),
                "best_time":    item.get("best_time", ""),
                "wikipedia_url": (
                    f"https://en.wikipedia.org/wiki/{item['wikipedia_title']}"
                    if item.get("wikipedia_title") else ""
                ),
            }, "curated")

    # ── 4. Wikidata (heritage facts, inception, architect) ─────
    for section in ["heritage_structures", "places_of_worship", "natural_areas",
                    "educational_institutions", "infrastructure"]:
        for item in wikidata.get(section, []):
            name = item.get("itemLabel", "")
            qid  = item.get("item", "").split("/")[-1]
            _upsert(name, {
                "heritage_type":  item.get("heritageLabel", "") or item.get("typeLabel", ""),
                "inception_year": item.get("inception", "")[:4] if item.get("inception") else "",
                "architect":      item.get("architectLabel", ""),
                "religion":       item.get("religionLabel", ""),
                "wikidata_url":   f"https://www.wikidata.org/wiki/{qid}" if qid else "",
                "photo_url":      item.get("image", ""),
            }, "wikidata")

    # ── 5. Wikipedia geosearch nearby places ───────────────────
    for place in wikipedia_deep.get("nearby_geo_places", []):
        name = place.get("name", "")
        _upsert(name, {
            "lat":           place.get("lat"),
            "lon":           place.get("lon"),
            "wikipedia_url": place.get("wiki_url", ""),
        }, "wikipedia")

    # ── 6. Rare enriched (catch any remaining) ─────────────────
    for rec in (rare_enriched.get("places") if isinstance(rare_enriched.get("places"), list) else []):
        name = rec.get("name", "")
        sources = rec.get("sources", [])
        _upsert(name, {}, "rare_merge")
        if name.strip().lower() in index:
            for s in sources:
                if s not in index[name.strip().lower()]["sources"]:
                    index[name.strip().lower()]["sources"].append(s)

    # ── Sort: score desc → name asc ────────────────────────────
    result = sorted(
        index.values(),
        key=lambda r: (-r["authenticity_score"], r["name"])
    )

    if verbose:
        print(f"      Places merged: {len(result)} unique")
        multi = sum(1 for r in result if len(r["sources"]) > 1)
        print(f"      Multi-source verified: {multi}")

    return result


def _build_food_section(
    specialties:    Dict,
    places:         List[Dict],
    wikidata:       Dict,
    wikipedia_deep: Dict,
) -> Dict:
    """Unified food section: dishes, restaurants, street food, markets."""

    # Dishes from specialties
    dishes = specialties.get("food_items", [])

    # Wikidata-confirmed foods
    wd_foods = [f.get("foodLabel", "") for f in wikidata.get("local_foods", []) if f.get("foodLabel")]

    # Wikipedia food mentions
    wiki_foods = wikipedia_deep.get("food_mentions", [])

    # All unique dish names
    all_dishes = list(dict.fromkeys(
        [d for d in dishes + wd_foods + wiki_foods if d and len(d) > 2]
    ))

    # Filter places by food domain
    restaurants = sorted(
        [p for p in places if p.get("domain") == "food"
         or p.get("tags", {}).get("amenity") in ("restaurant", "cafe", "fast_food",
            "ice_cream", "bakery", "food_court", "canteen", "snack_bar")],
        key=lambda p: -p.get("authenticity_score", 0)
    )

    street_food = [
        p for p in places if p.get("tags", {}).get("amenity") in
        ("street_vendor", "kiosk", "juice_bar", "dhaba", "tiffin_room")
    ]

    markets = [
        p for p in places if p.get("tags", {}).get("amenity") == "marketplace"
        or p.get("subcategory") in ("Bazaar / Market", "Market Experience", "Fish Market")
        or "market" in p.get("tags", {}).get("amenity", "").lower()
        or "market" in p.get("subcategory", "").lower()
    ]

    must_eat = specialties.get("must_eat_spots", [])

    return {
        "culture_notes":   specialties.get("food_culture", ""),
        "local_ingredients": specialties.get("local_ingredients", []),
        "signature_dishes": all_dishes,
        "dish_count":      len(all_dishes),
        "restaurants":     restaurants[:100],
        "street_food":     street_food,
        "must_eat_spots":  must_eat,
        "markets":         markets,
    }


def _build_stay_section(places: List[Dict]) -> List[Dict]:
    """All accommodation sorted by grade then score."""
    stay_amenities = {"hotel", "hostel", "guest_house", "motel", "resort",
                      "apartment", "chalet", "camp_site", "dharamshala", "homestay"}
    stay = [
        p for p in places
        if p.get("domain") == "stay"
        or p.get("tags", {}).get("tourism") in stay_amenities
    ]
    return sorted(stay, key=lambda p: (
        {"A": 0, "B": 1, "C": 2, "D": 3}.get(p.get("grade", "D"), 3),
        -p.get("authenticity_score", 0)
    ))


def _build_activities_section(places: List[Dict], specialties: Dict) -> List[Dict]:
    """Things to do — sport, cultural performance, boat rides, experiences."""
    activity_subcats = {
        "Cultural Performance", "Traditional Sport", "Boat Ride",
        "Heritage Walk", "Nature Park", "Water Sports",
    }
    activity_tags = {"sport", "leisure"}

    items = [
        p for p in places
        if p.get("domain") == "activities"
        or p.get("subcategory") in activity_subcats
        or any(t in p.get("tags", {}) for t in activity_tags)
    ]

    # Add curated experiences as activity entries
    for exp in specialties.get("experiences", []):
        # may be string or {"description": str, "source": str}
        desc = exp if isinstance(exp, str) else exp.get("description", "")
        if desc:
            items.append({
                "name":    desc,
                "domain":  "activities",
                "sources": ["curated"],
                "notes":   "",
                "subcategory": "Experience",
                "authenticity_score": 0.8,
                "grade": "B",
            })

    return sorted(items, key=lambda p: -p.get("authenticity_score", 0))


def _build_explore_section(places: List[Dict], wikidata: Dict) -> List[Dict]:
    """Heritage, temples, churches, historic — enriched with Wikidata facts."""

    explore_domains = {"explore", "culture"}
    explore_tags = {"historic", "heritage"}
    explore_subcats = {
        "Hindu Temple", "Church", "Mosque", "Dargah / Shrine", "Chapel",
        "Historic Fort", "Lighthouse", "Heritage Palace", "Hilltop Temple",
        "Healing Shrine", "Place of Worship",
    }

    base_items = {
        p["name"].lower(): p for p in places
        if p.get("domain") in explore_domains
        or p.get("subcategory") in explore_subcats
        or "historic" in p.get("tags", {})
        or "place_of_worship" in p.get("tags", {}).get("amenity", "")
    }

    # Enrich with Wikidata heritage/worship items not yet in places
    for section in ("heritage_structures", "places_of_worship", "natural_areas"):
        for item in wikidata.get(section, []):
            name = item.get("itemLabel", "")
            if not name:
                continue
            key = name.lower()
            if key not in base_items:
                base_items[key] = {
                    "name":          name,
                    "domain":        "explore",
                    "sources":       ["wikidata"],
                    "subcategory":   item.get("typeLabel", "Heritage Site"),
                    "heritage_type": item.get("heritageLabel", ""),
                    "inception_year": item.get("inception", "")[:4] if item.get("inception") else "",
                    "architect":     item.get("architectLabel", ""),
                    "wikidata_url":  item.get("item", ""),
                    "authenticity_score": 0.7,
                    "grade": "B",
                    "lat": None, "lon": None,
                }

    return sorted(
        base_items.values(),
        key=lambda p: (-p.get("authenticity_score", 0), p.get("name", ""))
    )


def _build_wildlife_section(open_data: Dict) -> Dict:
    """GBIF wildlife + marine species."""
    wildlife = sorted(
        open_data.get("species_wildlife", []),
        key=lambda s: -s.get("count", 0)
    )
    marine = open_data.get("marine_species", [])

    # Group wildlife by class
    by_class: Dict[str, List] = {}
    for s in wildlife:
        cls = s.get("class", "Unknown")
        by_class.setdefault(cls, []).append(s)

    return {
        "total_species":    len(wildlife),
        "marine_species":   len(marine),
        "by_class":         by_class,
        "marine":           marine,
        "top_sightings":    wildlife[:20],
    }


def _build_media_section(media_data: Dict, wikipedia_deep: Dict) -> Dict:
    """Photos with license + attribution — all freely usable."""
    commons_photos = media_data.get("commons_photos", [])
    wiki_images    = media_data.get("wikipedia_images", [])

    # Add Wikipedia article thumbnails from deep miner
    article_thumbs = []
    for article_data in wikipedia_deep.get("articles", {}).values():
        summary = article_data.get("summary") or {}
        thumb = summary.get("thumbnail", "")
        if thumb:
            article_thumbs.append({
                "thumb_url":   thumb,
                "article":     article_data.get("title", ""),
                "source":      "Wikipedia",
                "license":     "CC BY-SA",
            })

    all_media = commons_photos + wiki_images + article_thumbs

    return {
        "total_photos":    len(all_media),
        "commons_photos":  commons_photos[:50],
        "wiki_images":     wiki_images,
        "article_thumbs":  article_thumbs[:30],
        "license_note":    "All items are freely licensed — check item.license_url for attribution requirements",
    }


def _build_trends_section(trends: Dict) -> Dict:
    """What's being searched/read right now — Wikipedia pageviews + RSS."""
    wiki_trends = sorted(
        trends.get("wikipedia_trends", []),
        key=lambda t: -t.get("wikipedia_views_30d", 0)
    )
    rss = trends.get("rss_articles", [])
    relevant_rss = [a for a in rss if a.get("is_city_relevant")]

    return {
        "wikipedia_trending":  wiki_trends,
        "rss_all":             rss[:50],
        "rss_city_relevant":   relevant_rss[:30],
        "top_article":         wiki_trends[0] if wiki_trends else {},
    }


def _build_timeline(wikipedia_deep: Dict) -> List[Dict]:
    """Historical events sorted chronologically by year."""
    events = wikipedia_deep.get("historical_events", [])
    return sorted(
        [e for e in events if e.get("year")],
        key=lambda e: e["year"]
    )


def _compute_coverage_score(store: Dict) -> Dict:
    """Score how complete the data is — 0-100 per section."""
    scores = {}
    checks = {
        "places":     (len(store.get("places", [])),              100, 500),
        "food_dishes":(len(store.get("food", {}).get("signature_dishes", [])), 10, 25),
        "restaurants":(len(store.get("food", {}).get("restaurants", [])),      20, 100),
        "stay":       (len(store.get("stay", [])),                20, 80),
        "activities": (len(store.get("activities", [])),          10, 50),
        "explore":    (len(store.get("explore", [])),             15, 60),
        "wildlife":   (store.get("wildlife", {}).get("total_species", 0), 5, 50),
        "media":      (store.get("media", {}).get("total_photos", 0),     5, 40),
        "trends":     (len(store.get("trends", {}).get("wikipedia_trending", [])), 3, 15),
        "timeline":   (len(store.get("timeline", [])),            5, 30),
        "festivals":  (len(store.get("festivals", [])),           3, 15),
    }
    total_score = 0
    for key, (count, min_good, max_good) in checks.items():
        pct = min(100, int(100 * (count - min_good) / max(max_good - min_good, 1)))
        scores[key] = max(0, pct)
        total_score += scores[key]

    scores["overall"] = round(total_score / len(checks))
    return scores


# ============================================================
# MASTER BUILDER
# ============================================================

def build_unified_store(city_id: str, verbose: bool = False) -> Dict:
    """
    Read all output files for a city and build the unified store.

    Args:
        city_id:  e.g. "mangalore"
        verbose:  Print detailed progress

    Returns:
        The complete unified store dict (also saved to file)
    """

    print(f"\n{'='*55}")
    print(f"  Unified Store Builder — {city_id}")
    print(f"{'='*55}\n")

    # ── Load all source files ──────────────────────────────────
    print("  Loading source files...")
    data_hub         = _load(f"data_storage/{city_id}_data_hub.json",      "data_hub")
    osm_raw          = _load(f"data_storage/{city_id}_raw.json",           "osm_raw")
    specialties      = _load(f"data_core/{city_id}_specialties.json",      "specialties")
    trends_data      = _load(f"data_core/{city_id}_trends.json",           "trends")
    places_extended  = _load(f"data_core/{city_id}_places_extended.json",  "places_extended")
    wikidata         = _load(f"data_core/{city_id}_wikidata.json",         "wikidata")
    media_data       = _load(f"data_core/{city_id}_media.json",            "media")
    open_data        = _load(f"data_core/{city_id}_open_data.json",        "open_data")
    wikipedia_deep   = _load(f"data_core/{city_id}_wikipedia_deep.json",   "wikipedia_deep")
    rare_enriched    = _load(f"data_core/{city_id}_rare_enriched.json",    "rare_enriched")

    # Count available sources
    available = sum(1 for d in [data_hub, osm_raw, specialties, trends_data,
                                 places_extended, wikidata, media_data,
                                 open_data, wikipedia_deep] if d)
    print(f"  Sources loaded: {available}/9")

    # ── Build all sections ─────────────────────────────────────
    print("\n  Building sections...")

    print("  → Places (dedup + merge)...")
    places = _build_places(
        data_hub, osm_raw, places_extended,
        rare_enriched, wikidata, wikipedia_deep,
        verbose=verbose
    )

    print("  → Food...")
    food = _build_food_section(specialties, places, wikidata, wikipedia_deep)

    print("  → Stay...")
    stay = _build_stay_section(places)

    print("  → Activities...")
    activities = _build_activities_section(places, specialties)

    print("  → Explore (heritage, temples, historic)...")
    explore = _build_explore_section(places, wikidata)

    print("  → Local life...")
    local = sorted(
        [p for p in places if p.get("domain") == "local"
         or p.get("tags", {}).get("shop")
         or p.get("tags", {}).get("amenity") in ("marketplace", "community_centre", "social_centre")],
        key=lambda p: -p.get("authenticity_score", 0)
    )

    print("  → Transport...")
    transport = sorted(
        [p for p in places if p.get("domain") == "transport"
         or p.get("tags", {}).get("amenity") in ("bus_station", "ferry_terminal", "taxi")
         or p.get("tags", {}).get("highway") == "bus_stop"
         or p.get("tags", {}).get("railway") in ("station", "halt")],
        key=lambda p: -p.get("authenticity_score", 0)
    )

    print("  → Emergency...")
    emergency = [p for p in places
                 if p.get("domain") == "emergency"
                 or p.get("tags", {}).get("amenity") in ("hospital", "police", "fire_station", "pharmacy")]

    print("  → Wildlife...")
    wildlife = _build_wildlife_section(open_data)

    print("  → Media...")
    media = _build_media_section(media_data, wikipedia_deep)

    print("  → Trends...")
    trends_section = _build_trends_section(trends_data)

    print("  → Timeline...")
    timeline = _build_timeline(wikipedia_deep)

    # People
    people = sorted(
        wikidata.get("notable_persons", []),
        key=lambda p: p.get("birthdate", "0")
    )

    # Festivals — merge from wikidata + specialties
    wd_festivals  = [{"name": f.get("eventLabel", ""), "source": "wikidata"}
                     for f in wikidata.get("festivals", []) if f.get("eventLabel")]
    # specialties["festivals"] may be list of strings OR list of dicts
    _raw_festivals = specialties.get("festivals", [])
    cur_festivals = []
    for f in _raw_festivals:
        if isinstance(f, str):
            cur_festivals.append({"name": f, "month": None, "notes": "", "source": "curated"})
        elif isinstance(f, dict) and f.get("name"):
            cur_festivals.append({"name": f.get("name",""), "month": f.get("month"),
                                  "notes": f.get("notes",""), "source": "curated"})
    all_festival_names = {f["name"].lower() for f in cur_festivals}
    for f in wd_festivals:
        if f["name"].lower() not in all_festival_names:
            cur_festivals.append(f)
    festivals = sorted(cur_festivals, key=lambda f: f.get("month", 13))

    # Day trips
    day_trips = specialties.get("day_trips", [])

    # Seasons
    seasons = specialties.get("seasons", {})

    # Live data
    live = {
        "air_quality":     open_data.get("air_quality", {}),
        "asi_monuments":   open_data.get("asi_monuments", []),
        "walkable_routes": open_data.get("walkable_routes", []),
    }

    # ── Assemble final store ───────────────────────────────────
    store = {
        "meta": {
            "city_id":        city_id,
            "built_at":       _now_iso(),
            "sources_loaded": available,
            "source_files": {
                "data_hub":        f"data_storage/{city_id}_data_hub.json",
                "osm_raw":         f"data_storage/{city_id}_raw.json",
                "specialties":     f"data_core/{city_id}_specialties.json",
                "trends":          f"data_core/{city_id}_trends.json",
                "places_extended": f"data_core/{city_id}_places_extended.json",
                "wikidata":        f"data_core/{city_id}_wikidata.json",
                "media":           f"data_core/{city_id}_media.json",
                "open_data":       f"data_core/{city_id}_open_data.json",
                "wikipedia_deep":  f"data_core/{city_id}_wikipedia_deep.json",
            }
        },

        "places":     places,
        "food":       food,
        "stay":       stay,
        "activities": activities,
        "explore":    explore,
        "local":      local,
        "transport":  transport,
        "emergency":  emergency,
        "people":     people,
        "wildlife":   wildlife,
        "media":      media,
        "trends":     trends_section,
        "timeline":   timeline,
        "festivals":  festivals,
        "day_trips":  day_trips,
        "seasons":    seasons,
        "live":       live,
    }

    # Coverage score
    coverage = _compute_coverage_score(store)
    store["stats"] = {
        "total_places":         len(places),
        "multi_source":         sum(1 for p in places if len(p.get("sources", [])) > 1),
        "grade_A":              sum(1 for p in places if p.get("grade") == "A"),
        "grade_B":              sum(1 for p in places if p.get("grade") == "B"),
        "grade_C":              sum(1 for p in places if p.get("grade") == "C"),
        "food_dishes":          len(food.get("signature_dishes", [])),
        "restaurants":          len(food.get("restaurants", [])),
        "stay_options":         len(stay),
        "activities":           len(activities),
        "explore_sites":        len(explore),
        "local_spots":          len(local),
        "transport_nodes":      len(transport),
        "emergency_services":   len(emergency),
        "notable_persons":      len(people),
        "wildlife_species":     wildlife.get("total_species", 0),
        "marine_species":       wildlife.get("marine_species", 0),
        "photos":               media.get("total_photos", 0),
        "trending_articles":    len(trends_section.get("wikipedia_trending", [])),
        "historical_events":    len(timeline),
        "festivals":            len(festivals),
        "day_trips":            len(day_trips),
        "coverage_score":       coverage,
    }

    # ── Save ───────────────────────────────────────────────────
    os.makedirs("data_storage", exist_ok=True)
    output_path = f"data_storage/{city_id}_city_store.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)

    print(f"\n{'='*55}")
    print(f"  ✓ UNIFIED STORE BUILT")
    print(f"  Output:  {output_path}  ({size_mb:.1f} MB)")
    print(f"\n  COUNTS:")
    s = store["stats"]
    print(f"    Places (total):       {s['total_places']}")
    print(f"    Multi-source:         {s['multi_source']}")
    print(f"    Grade A / B / C:      {s['grade_A']} / {s['grade_B']} / {s['grade_C']}")
    print(f"    Food dishes:          {s['food_dishes']}")
    print(f"    Restaurants:          {s['restaurants']}")
    print(f"    Stay options:         {s['stay_options']}")
    print(f"    Activities:           {s['activities']}")
    print(f"    Explore (heritage):   {s['explore_sites']}")
    print(f"    Wildlife species:     {s['wildlife_species']}")
    print(f"    Photos:               {s['photos']}")
    print(f"    Historical events:    {s['historical_events']}")
    print(f"    Festivals:            {s['festivals']}")
    print(f"    Notable persons:      {s['notable_persons']}")
    print(f"\n  COVERAGE SCORE:")
    for k, v in coverage.items():
        bar = "█" * (v // 10) + "░" * (10 - v // 10)
        print(f"    {k:<18} [{bar}] {v}%")
    print(f"{'='*55}\n")

    return store


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Build unified city data store from all collector outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m data_storage.unified_store_builder --city mangalore
  python -m data_storage.unified_store_builder --city mangalore --verbose
  python -m data_storage.unified_store_builder --city mangalore mysore goa
        """
    )
    parser.add_argument("--city",    nargs="+", default=["mangalore"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    for city_id in args.city:
        try:
            build_unified_store(city_id.lower(), verbose=args.verbose)
        except Exception as e:
            print(f"\nERROR building store for '{city_id}': {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()