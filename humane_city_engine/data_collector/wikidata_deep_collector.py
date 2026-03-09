"""
data_collector/wikidata_deep_collector.py

WIKIDATA DEEP COLLECTOR — structured, linked open data for places.
LICENSE: CC0 — completely free and public domain.
API: https://query.wikidata.org/sparql (no key, ~30 req/min)

FIXES vs previous version:
  - QID lookup was returning wrong result (Q91020508 instead of Q42941)
    → Now uses wikidata_qid from CityProfile when available (hardcoded, exact)
    → Fallback query broadened to match municipalities/cities/urban areas
  - Heritage query used P1435 which is sparse in Indian data
    → Now uses P279*/P31 on architectural/religious structures directly
  - P131+ hierarchy traversal was too strict
    → Now tries both P131 (located in) AND P276 (location)
  - All queries now tested against Mangalore QID Q42941
"""

import requests
import json
import os
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone


SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "HumaneCityEngine/3.0 (open-source city guide research)",
    "Accept":     "application/sparql-results+json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sparql(query: str) -> List[Dict]:
    """Execute a SPARQL query against Wikidata. Returns flat list of result rows."""
    try:
        time.sleep(2.5)  # respect ~30 req/min rate limit
        resp = requests.get(
            SPARQL_ENDPOINT,
            params={"query": query, "format": "json"},
            headers=HEADERS,
            timeout=35
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        return [{k: v.get("value", "") for k, v in b.items()} for b in bindings]
    except Exception as e:
        print(f"    SPARQL error: {e}")
        return []


# ============================================================
# QID RESOLUTION — with profile override
# ============================================================

# Known correct QIDs — avoids wrong dynamic lookups
KNOWN_CITY_QIDS = {
    "mangalore":  "Q42941",
    "mangaluru":  "Q42941",
    "mysore":     "Q3397",
    "mysuru":     "Q3397",
    "udupi":      "Q583821",
    "goa":        "Q1191",
    "bengaluru":  "Q1355",
    "bangalore":  "Q1355",
    "mumbai":     "Q1156",
    "delhi":      "Q1353",
    "chennai":    "Q1352",
    "hyderabad":  "Q1361",
    "kolkata":    "Q1348",
    "pune":       "Q1538",
    "kochi":      "Q484582",
    "jaipur":     "Q39369",
    "ahmedabad":  "Q1114",
    "surat":      "Q170091",
    "lucknow":    "Q72970",
    "nagpur":     "Q956690",
    "indore":     "Q130614",
    "bhopal":     "Q171777",
    "patna":      "Q211734",
    "vadodara":   "Q3373764",
    "coimbatore": "Q207256",
    "madurai":    "Q204776",
    "visakhapatnam": "Q133936",
    "thiruvananthapuram": "Q588073",
}


def _get_city_qid(city_name: str, country_code: str = "IN",
                  profile_qid: Optional[str] = None) -> Optional[str]:
    """
    Resolve city to Wikidata QID.
    Priority: profile_qid > KNOWN_CITY_QIDS > dynamic SPARQL lookup
    """
    # 1. Use profile-provided QID (most reliable)
    if profile_qid:
        print(f"  City QID from profile: {profile_qid}")
        return profile_qid

    # 2. Check known QIDs table
    key = city_name.lower().strip()
    if key in KNOWN_CITY_QIDS:
        qid = KNOWN_CITY_QIDS[key]
        print(f"  City QID from known table: {qid} ({city_name})")
        return qid

    # 3. Dynamic SPARQL — broadened to catch municipalities & urban areas
    print(f"  Dynamic Wikidata QID lookup for: {city_name}")
    query = f"""
    SELECT ?city ?cityLabel WHERE {{
      {{
        ?city wdt:P31/wdt:P279* wd:Q515.
      }} UNION {{
        ?city wdt:P31/wdt:P279* wd:Q1093829.
      }} UNION {{
        ?city wdt:P31/wdt:P279* wd:Q1549591.
      }} UNION {{
        ?city wdt:P31 wd:Q2989457.
      }}
      ?city rdfs:label "{city_name}"@en.
      ?city wdt:P17 ?country.
      ?country wdt:P297 "{country_code}".
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 3
    """
    results = _sparql(query)
    if results:
        # Pick the one with the most complete label match
        for r in results:
            qid = r.get("city", "").split("/")[-1]
            label = r.get("cityLabel", "")
            if label.lower() == city_name.lower():
                print(f"  City QID (dynamic exact): {qid}")
                return qid
        qid = results[0].get("city", "").split("/")[-1]
        print(f"  City QID (dynamic first): {qid}")
        return qid

    print(f"  Warning: Could not resolve Wikidata QID for '{city_name}'")
    print(f"  Add wikidata_qid to the CityProfile to fix this.")
    return None


# ============================================================
# COLLECTORS — all fixed for Indian city data
# ============================================================

def collect_heritage_structures(city_qid: str) -> List[Dict]:
    """
    Buildings and structures of heritage significance.
    Uses broader P31 types since P1435 (heritage designation) is sparse in India.
    """
    query = f"""
    SELECT DISTINCT ?itemLabel ?item ?typeLabel ?inception ?architectLabel ?image WHERE {{
      {{
        ?item wdt:P131 wd:{city_qid}.
      }} UNION {{
        ?item wdt:P131/wdt:P131 wd:{city_qid}.
      }}
      ?item wdt:P31 ?type.
      ?type wdt:P279* ?base.
      FILTER(?base IN (
        wd:Q811979,   # architectural structure
        wd:Q570116,   # tourist attraction
        wd:Q839954,   # archaeological site
        wd:Q12518,    # tower
        wd:Q16970,    # church building
        wd:Q44539,    # mosque
        wd:Q17383,    # Hindu temple
        wd:Q24398318, # religious building
        wd:Q179049,   # palace
        wd:Q15243209, # historic monument
        wd:Q23413,    # castle
        wd:Q57660343  # heritage site
      ))
      OPTIONAL {{ ?item wdt:P571 ?inception. }}
      OPTIONAL {{ ?item wdt:P84  ?architect. }}
      OPTIONAL {{ ?item wdt:P18  ?image. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,kn". }}
    }}
    LIMIT 60
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "heritage_structure"
    print(f"  Heritage structures: {len(results)}")
    return results


def collect_places_of_worship(city_qid: str) -> List[Dict]:
    """All religious sites — using direct P131 which is how Indian POWs are linked."""
    query = f"""
    SELECT DISTINCT ?itemLabel ?item ?typeLabel ?inception ?religionLabel ?image WHERE {{
      {{
        ?item wdt:P131 wd:{city_qid}.
      }} UNION {{
        ?item wdt:P131/wdt:P131 wd:{city_qid}.
      }}
      {{
        ?item wdt:P31/wdt:P279* wd:Q1326856.
      }} UNION {{
        ?item wdt:P140 ?religion.
      }}
      OPTIONAL {{ ?item wdt:P571 ?inception. }}
      OPTIONAL {{ ?item wdt:P140 ?religion. }}
      OPTIONAL {{ ?item wdt:P18  ?image. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,kn". }}
    }}
    LIMIT 80
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "place_of_worship"
    print(f"  Places of worship: {len(results)}")
    return results


def collect_educational_institutions(city_qid: str) -> List[Dict]:
    """Universities, colleges, research institutes."""
    query = f"""
    SELECT DISTINCT ?itemLabel ?item ?typeLabel ?inception WHERE {{
      {{
        ?item wdt:P131 wd:{city_qid}.
      }} UNION {{
        ?item wdt:P131/wdt:P131 wd:{city_qid}.
      }}
      ?item wdt:P31 ?type.
      ?type wdt:P279* wd:Q2385804.
      OPTIONAL {{ ?item wdt:P571 ?inception. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 50
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "educational_institution"
    print(f"  Educational institutions: {len(results)}")
    return results


def collect_notable_persons(city_qid: str) -> List[Dict]:
    """People born in or associated with the city."""
    query = f"""
    SELECT DISTINCT ?personLabel ?person ?occupationLabel ?birthdate WHERE {{
      {{
        ?person wdt:P19 wd:{city_qid}.
      }} UNION {{
        ?person wdt:P551 wd:{city_qid}.
      }}
      ?person wdt:P31 wd:Q5.
      OPTIONAL {{ ?person wdt:P106 ?occupation. }}
      OPTIONAL {{ ?person wdt:P569 ?birthdate. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 80
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "notable_person"
    print(f"  Notable persons: {len(results)}")
    return results


def collect_local_foods(city_name: str, state: str) -> List[Dict]:
    """
    Foods and dishes linked to this city/region.
    Uses label-based filtering since few Indian foods have P495=India AND P1034=city.
    """
    # Search by name containing city/region keywords
    keywords = [city_name, state, "Tulu", "Udupi", "Mangalorean", "coastal Karnataka",
                "Dakshina Kannada", "Konkani"]

    all_foods = []
    seen = set()

    for kw in keywords[:4]:  # limit API calls
        query = f"""
        SELECT DISTINCT ?foodLabel ?food WHERE {{
          ?food wdt:P31/wdt:P279* wd:Q2095.
          ?food rdfs:label ?label.
          FILTER(LANG(?label) = "en")
          FILTER(CONTAINS(LCASE(?label), LCASE("{kw}")))
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 15
        """
        results = _sparql(query)
        for r in results:
            name = r.get("foodLabel", "")
            if name and name not in seen:
                seen.add(name)
                r["data_type"] = "local_food"
                r["matched_keyword"] = kw
                all_foods.append(r)

    print(f"  Local foods (Wikidata): {len(all_foods)}")
    return all_foods


def collect_festivals_events(city_qid: str) -> List[Dict]:
    """Officially recorded festivals."""
    query = f"""
    SELECT DISTINCT ?eventLabel ?event ?typeLabel WHERE {{
      {{
        ?event wdt:P131 wd:{city_qid}.
      }} UNION {{
        ?event wdt:P276 wd:{city_qid}.
      }}
      ?event wdt:P31 ?type.
      {{
        ?type wdt:P279* wd:Q132241.
      }} UNION {{
        ?type wdt:P279* wd:Q628858.
      }} UNION {{
        ?type wdt:P279* wd:Q186558.
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 30
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "festival"
    print(f"  Festivals: {len(results)}")
    return results


def collect_organisations(city_qid: str) -> List[Dict]:
    """NGOs, cultural bodies, notable organisations."""
    query = f"""
    SELECT DISTINCT ?orgLabel ?org ?typeLabel ?inception WHERE {{
      ?org wdt:P131 wd:{city_qid}.
      ?org wdt:P31 ?type.
      ?type wdt:P279* wd:Q43229.
      FILTER NOT EXISTS {{ ?org wdt:P31/wdt:P279* wd:Q2385804. }}
      FILTER NOT EXISTS {{ ?org wdt:P31/wdt:P279* wd:Q1326856. }}
      OPTIONAL {{ ?org wdt:P571 ?inception. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 40
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "organisation"
    print(f"  Organisations: {len(results)}")
    return results


def collect_infrastructure(city_qid: str) -> List[Dict]:
    """Bridges, ports, airports, lighthouses."""
    query = f"""
    SELECT DISTINCT ?itemLabel ?item ?typeLabel ?inception WHERE {{
      {{
        ?item wdt:P131 wd:{city_qid}.
      }} UNION {{
        ?item wdt:P131/wdt:P131 wd:{city_qid}.
      }}
      ?item wdt:P31 ?type.
      ?type wdt:P279* ?base.
      FILTER(?base IN (
        wd:Q12280,    # bridge
        wd:Q44782,    # port
        wd:Q1248784,  # airport
        wd:Q12323,    # dam
        wd:Q174782,   # lighthouse
        wd:Q7543858,  # road junction
        wd:Q55488,    # railway station
        wd:Q928830    # metro station
      ))
      OPTIONAL {{ ?item wdt:P571 ?inception. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 30
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "infrastructure"
    print(f"  Infrastructure: {len(results)}")
    return results


def collect_natural_areas(city_qid: str) -> List[Dict]:
    """Beaches, parks, forests, protected areas officially linked to city."""
    query = f"""
    SELECT DISTINCT ?itemLabel ?item ?typeLabel ?area WHERE {{
      {{
        ?item wdt:P131 wd:{city_qid}.
      }} UNION {{
        ?item wdt:P131/wdt:P131 wd:{city_qid}.
      }}
      ?item wdt:P31 ?type.
      ?type wdt:P279* ?base.
      FILTER(?base IN (
        wd:Q40080,    # beach
        wd:Q22698,    # park
        wd:Q179049,   # nature reserve
        wd:Q205495,   # forest reserve
        wd:Q473972,   # protected area
        wd:Q23442,    # island
        wd:Q4022,     # river
        wd:Q23397,    # lake
        wd:Q35509     # cape
      ))
      OPTIONAL {{ ?item wdt:P2046 ?area. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 30
    """
    results = _sparql(query)
    for r in results:
        r["data_type"] = "natural_area"
    print(f"  Natural areas: {len(results)}")
    return results


# ============================================================
# MASTER COLLECTOR
# ============================================================

def collect_wikidata_deep(
    city_name:    str,
    state:        str,
    country_code: str,
    output_path:  str,
    profile_qid:  Optional[str] = None,
) -> Dict:
    """
    Run all Wikidata collectors for a city.

    Args:
        city_name:    City display name e.g. "Mangalore"
        state:        State e.g. "Karnataka"
        country_code: ISO 2-letter e.g. "IN"
        output_path:  Where to save JSON
        profile_qid:  Wikidata QID from CityProfile (overrides dynamic lookup)
    """

    print(f"\n  Wikidata Deep Collector — {city_name}, {state}")
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    city_qid = _get_city_qid(city_name, country_code, profile_qid)

    all_data = {
        "city":         city_name,
        "state":        state,
        "city_qid":     city_qid,
        "generated_at": _now_iso(),
        "source":       "Wikidata",
        "license":      "CC0",
        "heritage_structures":        [],
        "places_of_worship":          [],
        "educational_institutions":   [],
        "notable_persons":            [],
        "local_foods":                [],
        "festivals":                  [],
        "organisations":              [],
        "infrastructure":             [],
        "natural_areas":              [],
    }

    if not city_qid:
        all_data["local_foods"] = collect_local_foods(city_name, state)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        return all_data

    collectors = [
        ("heritage_structures",        lambda: collect_heritage_structures(city_qid)),
        ("places_of_worship",          lambda: collect_places_of_worship(city_qid)),
        ("educational_institutions",   lambda: collect_educational_institutions(city_qid)),
        ("notable_persons",            lambda: collect_notable_persons(city_qid)),
        ("local_foods",                lambda: collect_local_foods(city_name, state)),
        ("festivals",                  lambda: collect_festivals_events(city_qid)),
        ("organisations",              lambda: collect_organisations(city_qid)),
        ("infrastructure",             lambda: collect_infrastructure(city_qid)),
        ("natural_areas",              lambda: collect_natural_areas(city_qid)),
    ]

    for key, fn in collectors:
        try:
            all_data[key] = fn()
        except Exception as e:
            print(f"  Collector '{key}' failed: {e}")

    total = sum(len(v) for v in all_data.values() if isinstance(v, list))
    print(f"\n  ✓ Wikidata total: {total} items")
    all_data["summary"] = {k: len(v) for k, v in all_data.items() if isinstance(v, list)}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"  Saved → {output_path}")
    return all_data


if __name__ == "__main__":
    from city_profiles.mangalore_profile import MANGALORE
    collect_wikidata_deep(
        city_name    = MANGALORE.display_name,
        state        = MANGALORE.state,
        country_code = MANGALORE.country_code,
        output_path  = f"data_core/{MANGALORE.city_id}_wikidata.json",
        profile_qid  = getattr(MANGALORE, "wikidata_qid", None),
    )