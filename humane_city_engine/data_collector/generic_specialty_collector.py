"""
data_collector/generic_specialty_collector.py  [SCALABLE VERSION]

Builds the specialty dataset (foods, must-visit, must-buy) for ANY city.
Reads everything from the CityProfile — no city-specific code here.

What it builds:
- food_items: from profile.signature_foods + Wikipedia/Wikidata confirmation
- must_visit: from profile.landmarks filtered by domain=explore/places
- must_eat: from profile.landmarks filtered by domain=food + signature_foods
- experiences: from profile.special_experiences
- day_trips: from profile.day_trip_cities

Output: data_core/<city_id>_specialties.json
"""

import requests
import json
import os
import time
from typing import List, Dict, Optional
from datetime import datetime

from city_profiles.city_profile import CityProfile


HEADERS = {"User-Agent": "HumaneCityEngine/3.0 (open-source city guide)"}
WIKIDATA_URL = "https://query.wikidata.org/sparql"


def _fetch_wikipedia_summary(title: str) -> Optional[str]:
    """Get Wikipedia summary for a topic."""
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("extract", "")[:400]
    except Exception:
        pass
    return None


def _confirm_foods_via_wikipedia(foods: List[str]) -> List[str]:
    """Confirm which foods have Wikipedia articles (adds credibility)."""
    confirmed = []
    for food in foods:
        wiki_title = food.replace(" ", "_")
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_title}"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("type") not in ("disambiguation",):
                    confirmed.append(food)
            time.sleep(0.3)
        except Exception:
            pass
    return confirmed


def _fetch_wikidata_local_foods(city_name: str, state: str) -> List[str]:
    """Query Wikidata for foods associated with this region."""
    query = f"""
    SELECT DISTINCT ?itemLabel WHERE {{
      ?item wdt:P31 wd:Q2095.       # instance of: food
      ?item wdt:P495 wd:Q668.       # country: India
      ?item rdfs:label ?label.
      FILTER(LANG(?label) = "en")
      FILTER(CONTAINS(LCASE(?label), LCASE("{city_name}")) ||
             CONTAINS(LCASE(?label), LCASE("{state}")))
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 20
    """
    try:
        resp = requests.get(
            WIKIDATA_URL,
            params={"query": query, "format": "json"},
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15
        )
        if resp.status_code == 200:
            results = resp.json().get("results", {}).get("bindings", [])
            return [r["itemLabel"]["value"] for r in results
                    if r.get("itemLabel", {}).get("value", "").replace(" ", "").isalpha() is False or True]
    except Exception:
        pass
    return []


def build_specialty_dataset(profile: CityProfile) -> Dict:
    """
    Build specialty dataset for any city using its CityProfile.

    Args:
        profile: CityProfile for the target city

    Returns:
        Dict saved to profile.specialties_path
    """

    print(f"\n  Building specialty dataset for {profile.display_name}...")
    os.makedirs("data_core", exist_ok=True)

    # ── FOODS ─────────────────────────────────────────────────
    print("  Fetching food data from Wikipedia...")
    confirmed_wiki = _confirm_foods_via_wikipedia(profile.signature_foods[:8])
    print(f"    Wikipedia confirmed: {len(confirmed_wiki)} foods")

    print("  Querying Wikidata for regional foods...")
    wikidata_foods = _fetch_wikidata_local_foods(profile.display_name, profile.state)
    print(f"    Wikidata: {len(wikidata_foods)} additional food items")

    all_foods = list(dict.fromkeys(
        profile.signature_foods + [f for f in wikidata_foods if f not in profile.signature_foods]
    ))

    # ── MUST VISIT — from profile landmarks ───────────────────
    must_visit = [
        {
            "name": lm.name,
            "subcategory": lm.subcategory,
            "lat": lm.lat,
            "lon": lm.lon,
            "notes": lm.notes,
            "best_time": lm.best_time,
            "tags": lm.tags,
        }
        for lm in profile.landmarks
        if lm.domain in ("explore", "places", "activities")
    ]

    # ── MUST EAT — food landmarks + signature dishes ──────────
    must_eat_spots = [
        {
            "name": lm.name,
            "subcategory": lm.subcategory,
            "lat": lm.lat,
            "lon": lm.lon,
            "notes": lm.notes,
            "best_time": lm.best_time,
        }
        for lm in profile.landmarks
        if lm.domain == "food"
    ]

    # ── EXPERIENCES ───────────────────────────────────────────
    experiences = [
        {"description": exp, "source": "curated"}
        for exp in profile.special_experiences
    ]

    # ── Wikipedia descriptions for key landmarks ──────────────
    wiki_descriptions = {}
    for lm in profile.landmarks:
        if lm.wikipedia_title:
            desc = _fetch_wikipedia_summary(lm.wikipedia_title)
            if desc:
                wiki_descriptions[lm.name] = desc
            time.sleep(0.3)
    print(f"  Wikipedia descriptions: {len(wiki_descriptions)} landmarks enriched")

    # ── ASSEMBLE DATASET ──────────────────────────────────────
    dataset = {
        "city":         profile.display_name,
        "city_id":      profile.city_id,
        "generated_at": datetime.utcnow().isoformat(),
        "sources": ["CityProfile curated seed", "Wikipedia REST API", "Wikidata SPARQL"],

        "food_culture":     profile.food_culture_notes,
        "local_ingredients": profile.local_ingredients,

        "food_items":       all_foods,
        "must_eat_spots":   must_eat_spots,
        "must_visit":       must_visit,
        "experiences":      experiences,
        "festivals":        profile.local_festivals,
        "day_trips":        profile.day_trip_cities,
        "seasons": {
            "peak_months":    profile.peak_season_months,
            "monsoon_months": profile.monsoon_months,
            "best_months":    profile.best_visit_months,
        },
        "wikipedia_descriptions": wiki_descriptions,

        "summary": {
            "food_items":    len(all_foods),
            "must_visit":    len(must_visit),
            "must_eat_spots": len(must_eat_spots),
            "experiences":   len(experiences),
            "day_trips":     len(profile.day_trip_cities),
        }
    }

    with open(profile.specialties_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Specialty dataset saved: {profile.specialties_path}")
    print(f"    Food items: {len(all_foods)}")
    print(f"    Must-visit: {len(must_visit)}")
    print(f"    Experiences: {len(experiences)}")

    return dataset


if __name__ == "__main__":
    from city_profiles.mangalore_profile import MANGALORE
    build_specialty_dataset(MANGALORE)