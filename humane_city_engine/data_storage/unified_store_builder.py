"""
data_storage/unified_store_builder.py

UNIFIED CITY DATA STORE — all data merged, deduped, sorted into 27 domains.

Reads every output file → merges → writes:
  data_storage/<city_id>_city_store.json        (main store, 27 domains)
  data_core/<city_id>_special_store.json        (Mangalore-specific only)

USAGE:
  python -m data_storage.unified_store_builder --city mangalore
  python -m data_storage.unified_store_builder --city mangalore --verbose
  python -m data_storage.unified_store_builder --city mangalore --include-special
"""

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Import taxonomy
try:
    from config.domain_taxonomy import TAXONOMY, ALL_DOMAINS, classify_osm_element, domain_for_subcategory
except ImportError:
    # Fallback if taxonomy not yet installed
    ALL_DOMAINS = ["places_landmarks","explore_sites","activities","local_spots",
                   "restaurants","food_dishes","stay_options","beaches_coastal",
                   "nature_eco","wildlife_species","marine_species","transport_nodes",
                   "emergency_services","religious_spiritual","markets_commerce",
                   "shopping_crafts","museums_culture","education_institutions",
                   "adventure_outdoor","photography_spots","nightlife_social",
                   "day_trips","festivals_events","historical_events","notable_persons",
                   "media_photos","trending_articles"]
    TAXONOMY = {d: [] for d in ALL_DOMAINS}
    def classify_osm_element(tags): return ("places_landmarks", "City Landmark")
    def domain_for_subcategory(sc): return "places_landmarks"


def _now(): return datetime.now(timezone.utc).isoformat()


def _load(path: str, label: str = "") -> Dict:
    if not os.path.exists(path):
        if label: print(f"    [skip] {label}")
        return {}
    try:
        data = json.load(open(path, encoding="utf-8"))
        size = os.path.getsize(path) // 1024
        if label: print(f"    [ok]   {label} — {size}KB")
        return data
    except Exception as e:
        print(f"    [err]  {label} — {e}")
        return {}


# ============================================================
# PLACE RECORD SCHEMA
# Every place in every domain uses this flat schema
# ============================================================

def _blank_record(name: str) -> Dict:
    return {
        "name":               name.strip(),
        "domain":             "",
        "subcategory":        "",
        "sources":            [],
        "source_count":       0,
        "authenticity_score": 0.0,
        "grade":              "D",
        "lat":                None,
        "lon":                None,
        # Descriptive
        "notes":              "",
        "best_time":          "",
        "tags":               {},
        # Contact
        "phone":              "",
        "website":            "",
        "opening_hours":      "",
        # Links
        "wikipedia_url":      "",
        "wikidata_url":       "",
        "photo_url":          "",
        # Heritage / cultural
        "heritage_type":      "",
        "inception_year":     "",
        "architect":          "",
        "religion":           "",
        "denomination":       "",
        # Wikipedia description
        "wiki_description":   "",
    }


# ============================================================
# MASTER PLACE INDEX (dedup by name)
# ============================================================

class PlaceIndex:
    def __init__(self):
        self._idx: Dict[str, Dict] = {}

    def upsert(self, name: str, update: Dict, source: str):
        if not name or len(name.strip()) < 2: return
        key = name.strip().lower()
        if key not in self._idx:
            self._idx[key] = _blank_record(name)
        rec = self._idx[key]

        if source not in rec["sources"]:
            rec["sources"].append(source)
            rec["source_count"] = len(rec["sources"])

        for k, v in update.items():
            if k == "authenticity_score":
                if v and v > rec["authenticity_score"]: rec[k] = v
            elif k == "tags" and isinstance(v, dict):
                rec["tags"].update(v)
            elif k == "sources": pass
            elif k == "source_count": pass
            else:
                if v and not rec.get(k): rec[k] = v

    def all_records(self) -> List[Dict]:
        return list(self._idx.values())

    def get(self, name: str) -> Optional[Dict]:
        return self._idx.get(name.strip().lower())


# ============================================================
# DOMAIN CLASSIFIER (maps legacy subcategories to new domains)
# ============================================================

# Legacy subcategory strings → new domain
LEGACY_MAP = {
    "beach": "beaches_coastal", "Beach": "beaches_coastal",
    "Hindu Temple": "religious_spiritual", "Church": "religious_spiritual",
    "Mosque": "religious_spiritual", "Dargah / Shrine": "religious_spiritual",
    "Healing Shrine": "religious_spiritual", "Ashram / Mutt": "religious_spiritual",
    "Jain Temple": "religious_spiritual", "Wayside Shrine": "religious_spiritual",
    "Historic Fort": "places_landmarks", "Lighthouse": "places_landmarks",
    "Heritage Palace": "places_landmarks", "Fort / Watchtower": "places_landmarks",
    "Heritage Building": "places_landmarks", "Historical Monument": "places_landmarks",
    "Scenic Viewpoint": "explore_sites", "Coastal Viewpoint": "explore_sites",
    "Heritage Walk": "activities", "Cultural Performance": "activities",
    "Traditional Sport": "activities", "Boat Ride": "activities",
    "Nature Park": "nature_eco", "Mangroves": "nature_eco",
    "River Estuary": "nature_eco", "Viewpoint": "explore_sites",
    "Market Experience": "markets_commerce", "Bazaar / Market": "markets_commerce",
    "Bakery Street": "restaurants", "Spice Market": "markets_commerce",
    "Ice Cream Parlour": "restaurants", "Traditional Breakfast": "restaurants",
    "Heritage Café": "restaurants", "Chinese Restaurant": "restaurants",
    "Coastal Restaurant": "restaurants",
}

def _resolve_domain(record: Dict) -> str:
    """Pick the best domain for a record."""
    existing = record.get("domain", "")
    if existing and existing in ALL_DOMAINS: return existing

    # Try subcategory
    sc = record.get("subcategory", "")
    if sc in LEGACY_MAP: return LEGACY_MAP[sc]

    # Try OSM tags
    tags = record.get("tags", {})
    if tags:
        domain, _ = classify_osm_element(tags)
        return domain

    return "places_landmarks"


def _resolve_subcategory(record: Dict) -> str:
    """Infer a valid subcategory from the record."""
    sc = record.get("subcategory", "")
    if sc: return sc

    tags = record.get("tags", {})
    if tags:
        _, subcategory = classify_osm_element(tags)
        return subcategory

    return "City Landmark"


# ============================================================
# SOURCE INGESTION FUNCTIONS
# ============================================================

def _ingest_data_hub(idx: PlaceIndex, data_hub: Dict):
    for domain, entities in data_hub.items():
        if not isinstance(entities, list): continue
        for e in entities:
            if not isinstance(e, dict): continue
            idx.upsert(e.get("name", ""), {
                "domain":             domain,
                "subcategory":        e.get("subcategory", ""),
                "lat":                e.get("coordinates", {}).get("latitude"),
                "lon":                e.get("coordinates", {}).get("longitude"),
                "authenticity_score": e.get("authenticity_score", 0),
                "grade":              e.get("grade", "D"),
            }, "data_hub")


def _ingest_osm_raw(idx: PlaceIndex, osm_raw: Dict):
    for el in osm_raw.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name", "")
        if not name: continue
        domain, subcategory = classify_osm_element(tags)
        idx.upsert(name, {
            "domain":        domain,
            "subcategory":   subcategory,
            "lat":           el.get("lat") or el.get("center", {}).get("lat"),
            "lon":           el.get("lon") or el.get("center", {}).get("lon"),
            "tags":          tags,
            "phone":         tags.get("phone") or tags.get("contact:phone", ""),
            "website":       tags.get("website", ""),
            "opening_hours": tags.get("opening_hours", ""),
            "religion":      tags.get("religion", ""),
            "denomination":  tags.get("denomination", ""),
        }, "osm")


def _ingest_places_extended(idx: PlaceIndex, places_extended: Dict):
    SKIP = {"city", "city_id", "generated_at", "sources", "summary"}
    for section, items in places_extended.items():
        if section in SKIP or not isinstance(items, list): continue
        for item in items:
            if not isinstance(item, dict): continue
            name = item.get("name", "")
            if not name: continue

            sc = item.get("subcategory", "")
            domain = LEGACY_MAP.get(sc, item.get("domain", ""))
            if domain not in ALL_DOMAINS: domain = _resolve_domain({"subcategory": sc})

            idx.upsert(name, {
                "domain":        domain,
                "subcategory":   sc,
                "lat":           item.get("lat"),
                "lon":           item.get("lon"),
                "notes":         item.get("notes", ""),
                "best_time":     item.get("best_time", ""),
                "wikipedia_url": (f"https://en.wikipedia.org/wiki/{item['wikipedia_title']}"
                                  if item.get("wikipedia_title") else ""),
            }, "curated")


def _ingest_wikidata(idx: PlaceIndex, wikidata: Dict):
    SECTIONS = {
        "heritage_structures":       "places_landmarks",
        "places_of_worship":         "religious_spiritual",
        "natural_areas":             "nature_eco",
        "educational_institutions":  "education_institutions",
        "infrastructure":            "transport_nodes",
        "organisations":             "local_spots",
    }
    for section, domain in SECTIONS.items():
        for item in wikidata.get(section, []):
            if not isinstance(item, dict): continue
            name = item.get("itemLabel", "")
            if not name: continue
            qid = item.get("item", "").split("/")[-1]
            idx.upsert(name, {
                "domain":        domain,
                "heritage_type": item.get("heritageLabel", "") or item.get("typeLabel", ""),
                "inception_year": str(item.get("inception", ""))[:4] if item.get("inception") else "",
                "architect":     item.get("architectLabel", ""),
                "religion":      item.get("religionLabel", ""),
                "wikidata_url":  f"https://www.wikidata.org/wiki/{qid}" if qid else "",
                "photo_url":     item.get("image", ""),
            }, "wikidata")


def _ingest_wikipedia(idx: PlaceIndex, wikipedia_deep: Dict):
    for place in wikipedia_deep.get("nearby_geo_places", []):
        if not isinstance(place, dict): continue
        name = place.get("name", "")
        if not name: continue
        idx.upsert(name, {
            "lat":           place.get("lat"),
            "lon":           place.get("lon"),
            "wikipedia_url": place.get("wiki_url", ""),
        }, "wikipedia")


def _ingest_open_data(idx: PlaceIndex, open_data: Dict):
    for mon in open_data.get("asi_monuments", []):
        if not isinstance(mon, dict): continue
        name = mon.get("name", "")
        if not name: continue
        idx.upsert(name, {
            "domain":      "places_landmarks",
            "subcategory": "Historical Monument",
            "notes":       mon.get("notes", ""),
        }, "asi")

    for route in open_data.get("walkable_routes", []):
        if not isinstance(route, dict): continue
        name = route.get("name", "")
        if not name: continue
        idx.upsert(name, {
            "domain":      "adventure_outdoor",
            "subcategory": "Trekking Trail",
        }, "osm_routes")


# ============================================================
# BUILD 27-DOMAIN STORE
# ============================================================

def _build_domain_store(idx: PlaceIndex) -> Dict[str, List[Dict]]:
    """Sort all records into the 27 domains."""
    store: Dict[str, List] = {d: [] for d in ALL_DOMAINS}

    for rec in idx.all_records():
        domain = _resolve_domain(rec)
        if domain not in store:
            domain = "places_landmarks"
        rec["domain"] = domain
        rec["subcategory"] = _resolve_subcategory(rec)
        store[domain].append(rec)

    # Sort each domain: multi-source first, then score desc, then name asc
    for domain in store:
        store[domain].sort(
            key=lambda r: (
                -r["source_count"],
                -r["authenticity_score"],
                r["name"]
            )
        )

    return store


# ============================================================
# SPECIAL SECTION BUILDERS (non-place domains)
# ============================================================

def _build_food_dishes(specialties: Dict, wikidata: Dict, wikipedia_deep: Dict, special_store: Dict) -> List[Dict]:
    """All documented food dishes as structured records."""
    dishes = []
    seen = set()

    def _add(name, category, cuisine="", community="", description="", best_where="", source=""):
        if not name or name.lower() in seen: return
        seen.add(name.lower())
        dishes.append({
            "name": name, "domain": "food_dishes", "subcategory": category,
            "cuisine": cuisine, "community": community, "description": description,
            "best_where": best_where, "source": source,
        })

    # From Mangalore special store (most detailed)
    for d in special_store.get("food_deep", {}).get("dishes", []):
        if isinstance(d, dict):
            _add(d.get("name",""), d.get("category","Local Breakfast Item"),
                 d.get("cuisine",""), d.get("community",""),
                 d.get("description",""), d.get("best_where",""), "special_store")

    # From specialties (signature foods)
    for item in specialties.get("food_items", []):
        if isinstance(item, str): _add(item, "Tulu Cuisine", source="specialties")
        elif isinstance(item, dict): _add(item.get("name",""), "Tulu Cuisine", source="specialties")

    # From Wikidata
    for f in wikidata.get("local_foods", []):
        if isinstance(f, dict): _add(f.get("foodLabel",""), "Tulu Cuisine", source="wikidata")

    # From Wikipedia food mentions
    for f in wikipedia_deep.get("food_mentions", []):
        if isinstance(f, str) and len(f) > 3: _add(f, "Tulu Cuisine", source="wikipedia")

    return sorted(dishes, key=lambda d: d.get("subcategory",""))


def _build_wildlife(open_data: Dict, special_store: Dict) -> Dict[str, List]:
    """All wildlife by subcategory."""
    by_subcat: Dict[str, List] = {
        "Bird": [], "Mammal": [], "Reptile": [], "Amphibian": [],
        "Insect": [], "Butterfly": [], "Migratory Species": [],
    }

    for sp in open_data.get("species_wildlife", []):
        if not isinstance(sp, dict): continue
        cls = sp.get("class", "")
        if "Aves" in cls: by_subcat["Bird"].append(sp)
        elif "Mammalia" in cls: by_subcat["Mammal"].append(sp)
        elif "Reptilia" in cls: by_subcat["Reptile"].append(sp)
        elif "Amphibia" in cls: by_subcat["Amphibian"].append(sp)
        elif "Insecta" in cls: by_subcat["Insect"].append(sp)
        elif "Lepidoptera" in cls: by_subcat["Butterfly"].append(sp)

    # Local GBIF birds
    for b in special_store.get("wildlife_local", {}).get("gbif_birds", []):
        if isinstance(b, dict):
            entry = {"species": b.get("species",""), "common_name": b.get("common_name",""), "family": b.get("family",""), "source": "gbif_local"}
            if entry not in by_subcat["Bird"]: by_subcat["Bird"].append(entry)

    # Rare coastal species
    for s in special_store.get("wildlife_local", {}).get("rare_coastal_species", []):
        if isinstance(s, dict):
            t = s.get("type", "")
            if "Bird" in t: by_subcat["Bird"].append(s)
            elif "Mammal" in t: by_subcat["Mammal"].append(s)
            elif "Reptile" in t: by_subcat["Reptile"].append(s)

    return {k: sorted(v, key=lambda x: x.get("common_name") or x.get("species","")) for k,v in by_subcat.items()}


def _build_marine_species(open_data: Dict) -> Dict[str, List]:
    by_subcat = {
        "Fish Species": [], "Crustacean": [], "Coral Species": [],
        "Sea Turtle": [], "Marine Mammal": [], "Mollusc": [], "Seabird": [],
    }
    for sp in open_data.get("marine_species", []):
        if isinstance(sp, dict):
            by_subcat["Fish Species"].append(sp)

    # Add known Mangalore coastal species
    known_marine = [
        {"species": "Olive Ridley Sea Turtle", "subcategory": "Sea Turtle", "status": "Seasonal nester"},
        {"species": "Irrawaddy Dolphin", "subcategory": "Marine Mammal", "status": "Rare visitor"},
        {"species": "Dugong", "subcategory": "Marine Mammal", "status": "Very rare"},
        {"species": "Mud Crab (Scylla serrata)", "subcategory": "Crustacean", "status": "Common — Mangalore delicacy"},
        {"species": "Spiny Lobster (Panulirus sp.)", "subcategory": "Crustacean", "status": "Seasonal, caught locally"},
        {"species": "Fiddler Crab", "subcategory": "Crustacean", "status": "Common in mangroves"},
        {"species": "Indian Mackerel (Rastrelliger kanagurta)", "subcategory": "Fish Species", "status": "Very common — Bangude"},
        {"species": "Lady Fish (Eleutheronema tetradactylum)", "subcategory": "Fish Species", "status": "Very common — Kane"},
        {"species": "Seer Fish (Sawara)", "subcategory": "Fish Species", "status": "Common — Neymeen"},
        {"species": "Pomfret (Pampus argenteus)", "subcategory": "Fish Species", "status": "Common — prized"},
    ]
    for sp in known_marine:
        sc = sp.get("subcategory", "Fish Species")
        if sc in by_subcat:
            by_subcat[sc].append(sp)

    return by_subcat


def _build_festivals(specialties: Dict, wikidata: Dict, special_store: Dict) -> List[Dict]:
    seen = set()
    festivals = []

    def _add(name, category, month=None, notes="", source=""):
        if not name or name.lower() in seen: return
        seen.add(name.lower())
        festivals.append({
            "name": name, "domain": "festivals_events",
            "subcategory": category, "month": month,
            "notes": notes, "source": source,
        })

    # Specialties (may be strings or dicts)
    for f in specialties.get("festivals", []):
        if isinstance(f, str): _add(f, "Temple Festival", source="specialties")
        elif isinstance(f, dict): _add(f.get("name",""), f.get("category","Temple Festival"),
                                        f.get("month"), f.get("notes",""), "specialties")

    # Tulu culture traditions
    for t in special_store.get("tulu_culture", {}).get("key_traditions", []):
        if isinstance(t, dict):
            _add(t.get("name",""), "Traditional Performance", notes=t.get("notes",""), source="tulu_culture")

    # Wikidata festivals
    for f in wikidata.get("festivals", []):
        if isinstance(f, dict): _add(f.get("eventLabel",""), "Cultural Festival", source="wikidata")

    # Known Mangalore festivals
    known = [
        ("Mangalore Dasara",          "Cultural Festival",       10, "City-wide, Kudroli temple centrepiece, 10 days"),
        ("Navaratri at Mangaladevi",  "Temple Festival",         10, "9-night Shakti worship, thousands attend"),
        ("Pili Vesha (Tiger Dance)",  "Traditional Performance", 10, "Navaratri tiger dance processions, unique to Tulu Nadu"),
        ("Monte Feast (Milagres)",    "Church Feast",             8, "Hundreds of thousands attend the hillside church"),
        ("St Aloysius Feast",         "Church Feast",             6, "June 21, parade through city, major Catholic event"),
        ("Eid ul-Fitr",               "Cultural Festival",     None, "Beary community, Idgah Maidan mass prayer"),
        ("Kambala Season",            "Kambala / Folk Sport Event", 11, "Nov-Mar, buffalo races in paddy fields across district"),
        ("Brahmotsava",               "Temple Festival",          3, "Annual chariot festival at major temples"),
        ("Matsya Jatre",              "Cultural Festival",     None, "Fish festival, Mogaveera fishing community, Hoige Bazaar"),
        ("Yakshagana Season",         "Traditional Performance", 11, "Nov-May, nightly performances across coastal Karnataka"),
    ]
    for name, cat, month, notes in known:
        _add(name, cat, month, notes, "curated")

    return sorted([f for f in festivals if f.get("month")], key=lambda f: f["month"]) + \
           [f for f in festivals if not f.get("month")]


def _build_historical_events(wikipedia_deep: Dict, special_store: Dict) -> List[Dict]:
    seen_years = {}
    events = []

    def _add(year, event, category="City Milestone", source=""):
        if not year: return
        entry = {"year": year, "event": event, "domain": "historical_events",
                 "subcategory": category, "source": source}
        events.append(entry)

    for e in wikipedia_deep.get("historical_events", []):
        if isinstance(e, dict): _add(e.get("year"), e.get("context","")[:200], source="wikipedia")

    for e in special_store.get("history", {}).get("timeline", []):
        if isinstance(e, dict): _add(e.get("year"), e.get("event",""), "City Milestone", "special_store")

    return sorted(events, key=lambda e: e.get("year", 9999))


def _build_notable_persons(wikidata: Dict, special_store: Dict) -> List[Dict]:
    seen = set()
    persons = []

    for p in wikidata.get("notable_persons", []):
        if not isinstance(p, dict): continue
        name = p.get("personLabel", "")
        if not name or name.lower() in seen: continue
        seen.add(name.lower())
        persons.append({
            "name": name, "domain": "notable_persons",
            "occupation": p.get("occupationLabel",""),
            "subcategory": _occupation_to_subcategory(p.get("occupationLabel","")),
            "birthdate": p.get("birthdate","")[:10] if p.get("birthdate") else "",
            "source": "wikidata",
        })

    return sorted(persons, key=lambda p: p.get("birthdate",""))


def _occupation_to_subcategory(occ: str) -> str:
    occ = occ.lower()
    if any(w in occ for w in ["politician","administrator","minister"]): return "Politician / Administrator"
    if any(w in occ for w in ["artist","painter","sculptor"]): return "Artist"
    if any(w in occ for w in ["writer","poet","author","novelist"]): return "Writer / Poet"
    if any(w in occ for w in ["scientist","physicist","chemist","engineer"]): return "Scientist / Scholar"
    if any(w in occ for w in ["musician","singer","composer"]): return "Musician"
    if any(w in occ for w in ["actor","filmmaker","director"]): return "Filmmaker / Actor"
    if any(w in occ for w in ["athlete","cricketer","footballer","player"]): return "Sportsperson"
    if any(w in occ for w in ["spiritual","religious","swami","bishop","priest"]): return "Religious Leader"
    return "Notable Person"


def _build_media(media_data: Dict, wikipedia_deep: Dict) -> List[Dict]:
    items = []
    seen = set()

    def _add(item):
        url = item.get("thumb_url","") or item.get("url","")
        if not url or url in seen: return
        seen.add(url)
        items.append({**item, "domain": "media_photos"})

    for p in media_data.get("commons_photos", [])[:60]:
        if isinstance(p, dict):
            _add({**p, "subcategory": "Landmark Photo"})

    for p in media_data.get("wikipedia_images", []):
        if isinstance(p, dict):
            _add({**p, "subcategory": "City Landscape"})

    for art_data in wikipedia_deep.get("articles", {}).values():
        if not isinstance(art_data, dict): continue
        summary = art_data.get("summary") or {}
        if isinstance(summary, dict):
            thumb = summary.get("thumbnail","")
            if thumb:
                _add({"thumb_url": thumb, "source": "Wikipedia",
                      "license": "CC BY-SA", "article": art_data.get("title",""),
                      "subcategory": "City Landscape"})

    return items


def _build_trending(trends: Dict) -> List[Dict]:
    items = []

    for t in trends.get("wikipedia_trends", []):
        if isinstance(t, dict):
            items.append({
                "name":        t.get("article",""),
                "domain":      "trending_articles",
                "subcategory": "Wikipedia Article",
                "views_30d":   t.get("wikipedia_views_30d", 0),
                "source":      "wikipedia_pageviews",
            })

    for a in trends.get("rss_articles", [])[:30]:
        if isinstance(a, dict):
            items.append({
                "name":        a.get("title",""),
                "domain":      "trending_articles",
                "subcategory": "News Feature" if not a.get("is_city_relevant") else "Local Discovery",
                "url":         a.get("url",""),
                "published":   a.get("published",""),
                "source":      "rss",
            })

    return sorted(items, key=lambda x: -x.get("views_30d", 0))


def _build_day_trips(specialties: Dict) -> List[Dict]:
    trips = []
    for item in specialties.get("day_trips", []):
        if isinstance(item, str):
            trips.append({"name": item, "domain": "day_trips", "subcategory": "Nearby Town", "source": "specialties"})
        elif isinstance(item, dict):
            trips.append({**item, "domain": "day_trips",
                          "subcategory": item.get("subcategory", "Nearby Town")})
    return trips


# ============================================================
# COVERAGE SCORE
# ============================================================

def _coverage_score(store: Dict) -> Dict:
    checks = {
        "places_landmarks":  (len(store.get("places_landmarks",[])),      10, 80),
        "beaches_coastal":   (len(store.get("beaches_coastal",[])),         3, 20),
        "religious_spiritual":(len(store.get("religious_spiritual",[])),   10, 60),
        "restaurants":       (len(store.get("restaurants",[])),            15, 100),
        "food_dishes":       (len(store.get("food_dishes",[])),            10, 30),
        "stay_options":      (len(store.get("stay_options",[])),           10, 60),
        "nature_eco":        (len(store.get("nature_eco",[])),              5, 30),
        "wildlife_species":  (sum(len(v) for v in store.get("wildlife_species",{}).values()), 5, 50),
        "marine_species":    (sum(len(v) for v in store.get("marine_species",{}).values()),   3, 20),
        "transport_nodes":   (len(store.get("transport_nodes",[])),         5, 40),
        "markets_commerce":  (len(store.get("markets_commerce",[])),        3, 20),
        "museums_culture":   (len(store.get("museums_culture",[])),         3, 20),
        "festivals_events":  (len(store.get("festivals_events",[])),        5, 20),
        "historical_events": (len(store.get("historical_events",[])),       5, 30),
        "notable_persons":   (len(store.get("notable_persons",[])),         3, 20),
        "media_photos":      (len(store.get("media_photos",[])),            5, 40),
        "trending_articles": (len(store.get("trending_articles",[])),       3, 15),
    }
    scores = {}
    for k, (count, lo, hi) in checks.items():
        pct = max(0, min(100, int(100 * (count - lo) / max(hi - lo, 1))))
        scores[k] = pct
    scores["overall"] = round(sum(scores.values()) / len(scores))
    return scores


# ============================================================
# MASTER BUILDER
# ============================================================

def build_unified_store(city_id: str, verbose: bool = False,
                        include_special: bool = False) -> Dict:

    print(f"\n{'='*60}")
    print(f"  Unified Store Builder v2 — {city_id}")
    print(f"{'='*60}\n")

    # ── Load all sources ───────────────────────────────────────
    print("  Loading source files...")
    data_hub       = _load(f"data_storage/{city_id}_data_hub.json",       "data_hub")
    osm_raw        = _load(f"data_storage/{city_id}_raw.json",            "osm_raw")
    specialties    = _load(f"data_core/{city_id}_specialties.json",       "specialties")
    trends         = _load(f"data_core/{city_id}_trends.json",            "trends")
    places_ext     = _load(f"data_core/{city_id}_places_extended.json",   "places_extended")
    wikidata       = _load(f"data_core/{city_id}_wikidata.json",          "wikidata")
    media_data     = _load(f"data_core/{city_id}_media.json",             "media")
    open_data      = _load(f"data_core/{city_id}_open_data.json",         "open_data")
    wikipedia_deep = _load(f"data_core/{city_id}_wikipedia_deep.json",    "wikipedia_deep")
    special_store  = _load(f"data_core/{city_id}_special_store.json",     "special_store")

    sources_loaded = sum(1 for d in [data_hub, osm_raw, specialties, trends, places_ext,
                                      wikidata, media_data, open_data, wikipedia_deep] if d)
    print(f"  Sources loaded: {sources_loaded}/9  |  Special store: {'yes' if special_store else 'not yet run'}")

    # ── Build place index ──────────────────────────────────────
    print("\n  Building place index...")
    idx = PlaceIndex()
    _ingest_data_hub(idx, data_hub)
    print(f"    After data_hub:  {len(idx.all_records())}")
    _ingest_osm_raw(idx, osm_raw)
    print(f"    After osm_raw:   {len(idx.all_records())}")
    _ingest_places_extended(idx, places_ext)
    print(f"    After extended:  {len(idx.all_records())}")
    _ingest_wikidata(idx, wikidata)
    print(f"    After wikidata:  {len(idx.all_records())}")
    _ingest_wikipedia(idx, wikipedia_deep)
    print(f"    After wikipedia: {len(idx.all_records())}")
    _ingest_open_data(idx, open_data)
    print(f"    After open_data: {len(idx.all_records())}")

    # Ingest underrated spots from special store
    for spot in special_store.get("underrated_spots", {}).get("underrated_curated", []):
        if isinstance(spot, dict):
            name = spot.get("name","")
            sc = spot.get("subcategory","")
            domain = LEGACY_MAP.get(sc, "local_spots")
            idx.upsert(name, {
                "domain": domain, "subcategory": sc,
                "lat": spot.get("lat"), "lon": spot.get("lon"),
                "notes": spot.get("notes",""), "best_time": spot.get("best_time",""),
            }, "mangalore_special")
    print(f"    After special:   {len(idx.all_records())}")

    # ── Sort into 27 domains ───────────────────────────────────
    print("\n  Sorting into 27 domains...")
    domain_store = _build_domain_store(idx)

    # ── Build non-place sections ───────────────────────────────
    print("  Building food dishes...")
    food_dishes = _build_food_dishes(specialties, wikidata, wikipedia_deep, special_store)

    print("  Building wildlife...")
    wildlife = _build_wildlife(open_data, special_store)

    print("  Building marine species...")
    marine = _build_marine_species(open_data)

    print("  Building festivals...")
    festivals = _build_festivals(specialties, wikidata, special_store)

    print("  Building historical events...")
    history = _build_historical_events(wikipedia_deep, special_store)

    print("  Building notable persons...")
    persons = _build_notable_persons(wikidata, special_store)

    print("  Building media...")
    media = _build_media(media_data, wikipedia_deep)

    print("  Building trending...")
    trending = _build_trending(trends)

    print("  Building day trips...")
    day_trips = _build_day_trips(specialties)

    # Override some domains with richer builders
    domain_store["food_dishes"]       = food_dishes
    domain_store["wildlife_species"]  = wildlife      # dict by subcategory
    domain_store["marine_species"]    = marine         # dict by subcategory
    domain_store["festivals_events"]  = festivals
    domain_store["historical_events"] = history
    domain_store["notable_persons"]   = persons
    domain_store["media_photos"]      = media
    domain_store["trending_articles"] = trending
    domain_store["day_trips"]         = day_trips

    # Seasons
    seasons = specialties.get("seasons", {})

    # Live data
    live = {
        "air_quality":     open_data.get("air_quality", {}),
        "walkable_routes": open_data.get("walkable_routes", []),
        "community_data":  special_store.get("community_profiles", {}).get("community_profiles", []),
    }

    # ── Assemble final store ───────────────────────────────────
    place_count = sum(
        len(v) if isinstance(v, list) else sum(len(x) for x in v.values() if isinstance(x, list))
        for v in domain_store.values()
    )
    multi_src = sum(
        1 for r in idx.all_records() if r.get("source_count", 0) > 1
    )

    coverage = _coverage_score(domain_store)

    final = {
        "meta": {
            "city_id":        city_id,
            "built_at":       _now(),
            "sources_loaded": sources_loaded,
            "total_records":  len(idx.all_records()),
            "taxonomy_version": "v2_27domains",
        },

        # 27 domain sections
        **domain_store,

        # Context sections
        "seasons":   seasons,
        "live":      live,

        "stats": {
            "total_unique_places":   len(idx.all_records()),
            "multi_source_verified": multi_src,
            "domain_counts": {d: len(v) if isinstance(v, list) else
                              sum(len(x) for x in v.values() if isinstance(x,list))
                              for d, v in domain_store.items()},
            "coverage": coverage,
        },
    }

    # ── Save ───────────────────────────────────────────────────
    os.makedirs("data_storage", exist_ok=True)
    output = f"data_storage/{city_id}_city_store.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    size = os.path.getsize(output) / (1024*1024)

    print(f"\n{'='*60}")
    print(f"  ✓  UNIFIED STORE COMPLETE")
    print(f"  Output: {output}  ({size:.1f} MB)")
    print(f"\n  DOMAIN COUNTS (27 domains):")
    for d in ALL_DOMAINS:
        v = domain_store.get(d)
        cnt = len(v) if isinstance(v, list) else sum(len(x) for x in v.values() if isinstance(x,list)) if isinstance(v,dict) else 0
        cov = coverage.get(d, "-")
        bar = ("█" * (cov//10) + "░"*(10-cov//10)) if isinstance(cov,int) else "          "
        print(f"    {d:<28} {cnt:>5}  [{bar}] {cov}%")
    print(f"\n  Total unique places: {len(idx.all_records())}")
    print(f"  Multi-source:        {multi_src}")
    print(f"  Overall coverage:    {coverage.get('overall',0)}%")
    print(f"{'='*60}\n")

    return final


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Build unified 27-domain city store")
    parser.add_argument("--city",    nargs="+", default=["mangalore"])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--include-special", action="store_true",
                        help="Run Mangalore special collector first")
    args = parser.parse_args()

    for city_id in args.city:
        if args.include_special and city_id == "mangalore":
            print("  Running Mangalore special collector first...")
            try:
                from mangalore_special.mangalore_deep_collector import build_mangalore_special_store
                build_mangalore_special_store()
            except Exception as e:
                print(f"  Special collector failed: {e}")

        build_unified_store(city_id.lower(), verbose=args.verbose)


if __name__ == "__main__":
    main()