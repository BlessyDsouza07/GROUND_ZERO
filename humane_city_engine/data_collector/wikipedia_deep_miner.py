"""
data_collector/wikipedia_deep_miner.py

WIKIPEDIA DEEP TEXT MINER — structured knowledge extraction from Wikipedia.

WHY Wikipedia mining is underrated:
  Wikipedia articles on Indian cities contain deeply researched sections on:
  - History (neighbourhood by neighbourhood, not just 'founded in X')
  - Demographics (community breakdown — important for understanding what
    neighbourhoods have what food, festivals, culture)
  - Economy (what industries, what products — tells you what's locally made)
  - Culture (specific art forms, music styles, festivals with details)
  - Notable educational institutions (with founding dates)
  - Cuisine sections (often more detailed than food guides)
  - Transport sections (every bus route, ferry, auto stand — real local info)

  This collector:
  1. Fetches full article text via Wikipedia API
  2. Parses section-by-section into structured data
  3. Extracts: dates, places, food names, institution names, route info
  4. Also mines "See Also" and "Related" articles for breadth
  5. Fetches coordinates for all linked places

APIs:
  - Wikipedia REST API (CC BY-SA 3.0, free, no key)
  - Wikipedia MediaWiki API (same license)
"""

import requests
import json
import os
import re
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime


WIKI_REST  = "https://en.wikipedia.org/api/rest_v1"
WIKI_API   = "https://en.wikipedia.org/w/api.php"
HEADERS    = {"User-Agent": "HumaneCityEngine/3.0 (city guide research, non-commercial)"}


# ============================================================
# SECTION PARSER
# ============================================================

def _fetch_article_sections(title: str) -> List[Dict]:
    """
    Fetch all sections of a Wikipedia article.
    Returns [{section_title, section_text, depth}]
    """
    resp = requests.get(
        f"{WIKI_REST}/page/mobile-sections/{title.replace(' ', '_')}",
        headers=HEADERS,
        timeout=20
    )
    if resp.status_code != 200:
        return []

    data = resp.json()
    sections = []

    # Lead section
    lead = data.get("lead", {})
    lead_text = lead.get("sections", [{}])[0].get("text", "")
    if lead_text:
        sections.append({"title": "Introduction", "text": lead_text, "depth": 1})

    # Remaining sections
    for section in data.get("remaining", {}).get("sections", []):
        sections.append({
            "title": section.get("line", ""),
            "text":  section.get("text", ""),
            "depth": section.get("toclevel", 2),
        })

    return sections


def _extract_places_from_text(text: str) -> List[str]:
    """Extract place names mentioned in text (capitalised nouns in context)."""
    # Simple heuristic: words followed by common place suffixes, or in lists
    place_patterns = [
        r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*(?:\s+(?:Beach|Temple|Church|Mosque|Lake|River|Hill|Garden|Museum|Fort|Palace|Market|Street|Road|Bridge|Park|Gate|Tower)))\b',
        r'\b([A-Z][a-z]+(?:pura|giri|nagar|peta|katte|halli|betta|ghat|wadi|abad|pur))\b',
    ]
    found = []
    for pat in place_patterns:
        found.extend(re.findall(pat, text, re.MULTILINE))
    return list(set(found))


def _extract_food_from_text(text: str) -> List[str]:
    """Extract food item names from text."""
    # After removing HTML
    clean = re.sub(r'<[^>]+>', '', text)
    food_patterns = [
        r'\b([A-Z][a-z]+(?: [a-z]+){0,3}(?:\s+(?:dosa|idli|roti|curry|rice|masala|biryani|fry|roast|gassi|chutney|pickle|sweet|halwa|ladoo|barfi|ice cream|soup|broth|stew)))\b',
        r'\b([a-z]+(?: [a-z]+){0,2}(?:dosa|idli|rotti|gassi|ghee roast|tali|bun|baje|kadubu|undi|patrade|patrode|sanna|moode|kori))\b',
    ]
    found = []
    for pat in food_patterns:
        found.extend(re.findall(pat, clean, re.IGNORECASE))
    return list(set(f.strip() for f in found if len(f) > 3))


def _extract_dates_events(text: str) -> List[Dict]:
    """Extract year + event pairs from text."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Pattern: "In 1780, the..." or "established in 1935" or "since 1900"
    pattern = r'\b(1[0-9]{3}|20[0-2][0-9])\b[^.]{5,80}'
    matches = re.findall(pattern, clean)
    results = []
    for m in matches[:30]:  # limit
        year_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', m)
        if year_match:
            results.append({"year": int(year_match.group()), "context": m[:120].strip()})
    return results


def _fetch_linked_coordinates(title: str) -> List[Dict]:
    """
    Get coordinates for all place-links in an article using Wikipedia's
    geosearch capability — finds nearby articles.
    """
    # Geosearch: find Wikipedia articles near city
    params = {
        "action":    "query",
        "list":      "geosearch",
        "gspage":    title,
        "gsradius":  "50000",  # 50km radius
        "gslimit":   "100",
        "format":    "json",
    }
    try:
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        places = resp.json().get("query", {}).get("geosearch", [])
        return [
            {
                "name":    p.get("title", ""),
                "lat":     p.get("lat"),
                "lon":     p.get("lon"),
                "dist_m":  p.get("dist"),
                "source":  "Wikipedia Geosearch",
                "wiki_url": f"https://en.wikipedia.org/wiki/{p.get('title', '').replace(' ', '_')}",
            }
            for p in places
        ]
    except Exception as e:
        print(f"    Geosearch error: {e}")
        return []


def _fetch_article_summary(title: str) -> Optional[Dict]:
    """Fetch article summary with thumbnail and key facts."""
    try:
        resp = requests.get(
            f"{WIKI_REST}/page/summary/{title.replace(' ', '_')}",
            headers=HEADERS,
            timeout=10
        )
        if resp.status_code == 200:
            d = resp.json()
            return {
                "title":       d.get("title"),
                "description": d.get("description", ""),
                "extract":     d.get("extract", "")[:500],
                "thumbnail":   d.get("thumbnail", {}).get("source", ""),
                "coordinates": d.get("coordinates", {}),
                "wiki_url":    d.get("content_urls", {}).get("desktop", {}).get("page", ""),
            }
    except Exception:
        pass
    return None


def _fetch_categories(title: str) -> List[str]:
    """Get all Wikipedia categories for an article — reveals hidden classifications."""
    params = {
        "action":  "query",
        "titles":  title,
        "prop":    "categories",
        "cllimit": "50",
        "format":  "json",
    }
    try:
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            cats = page.get("categories", [])
            return [c["title"].replace("Category:", "") for c in cats]
    except Exception:
        pass
    return []


def _fetch_related_articles(title: str) -> List[str]:
    """Get articles linked from this one — expands the knowledge graph."""
    params = {
        "action":    "query",
        "titles":    title,
        "prop":      "links",
        "pllimit":   "100",
        "plnamespace": "0",  # article namespace only
        "format":    "json",
    }
    try:
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            links = page.get("links", [])
            return [l["title"] for l in links]
    except Exception:
        pass
    return []


# ============================================================
# MAIN MINER
# ============================================================

def mine_wikipedia_deep(
    primary_articles:  List[str],
    city_name:         str,
    output_path:       str,
    mine_linked:       bool = True,
) -> Dict:
    """
    Deep-mine Wikipedia for structured city knowledge.

    Args:
        primary_articles: Core Wikipedia articles to mine (from CityProfile.wikipedia_articles)
        city_name:        City display name (for geosearch centering)
        output_path:      Where to save JSON
        mine_linked:      If True, also mine top linked articles

    Returns:
        Dict saved to output_path
    """

    print(f"\n  Wikipedia Deep Miner — {city_name}")
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    all_articles: Dict[str, Dict] = {}
    all_foods:    List[str] = []
    all_places:   List[str] = []
    all_events:   List[Dict] = []
    nearby_places: List[Dict] = []

    # ── GEOSEARCH: find ALL Wikipedia articles near city ───────
    print(f"  Geosearch: all Wikipedia articles near {city_name}...")
    geo_nearby = _fetch_linked_coordinates(city_name)
    nearby_places = geo_nearby
    print(f"    Found {len(geo_nearby)} nearby geo-tagged articles")

    # ── MINE PRIMARY ARTICLES ──────────────────────────────────
    print(f"  Mining {len(primary_articles)} primary articles...")
    for title in primary_articles:
        print(f"    [{title}]")
        try:
            summary = _fetch_article_summary(title)
            sections = _fetch_article_sections(title)
            categories = _fetch_categories(title)

            article_data = {
                "title":      title,
                "summary":    summary,
                "sections":   sections,
                "categories": categories,
                "food_mentions":  [],
                "place_mentions": [],
                "date_events":    [],
            }

            for section in sections:
                text = section.get("text", "")
                article_data["food_mentions"].extend(_extract_food_from_text(text))
                article_data["place_mentions"].extend(_extract_places_from_text(text))
                article_data["date_events"].extend(_extract_dates_events(text))

            # Dedup
            article_data["food_mentions"]  = list(set(article_data["food_mentions"]))[:30]
            article_data["place_mentions"] = list(set(article_data["place_mentions"]))[:40]

            all_articles[title] = article_data
            all_foods.extend(article_data["food_mentions"])
            all_places.extend(article_data["place_mentions"])
            all_events.extend(article_data["date_events"][:5])

            # Mine related articles (one level deep)
            if mine_linked:
                linked = _fetch_related_articles(title)
                # Filter to Indian/local articles (rough heuristic)
                local_linked = [l for l in linked if any(
                    kw in l for kw in [city_name, "Karnataka", "Tulu", "India", "Beach", "Temple", "Church", "Fort"]
                )][:10]
                for linked_title in local_linked:
                    if linked_title not in all_articles:
                        time.sleep(0.5)
                        ls = _fetch_article_summary(linked_title)
                        if ls:
                            all_articles[linked_title] = {
                                "title":    linked_title,
                                "summary":  ls,
                                "from_link": title,
                                "categories": [],
                                "sections": [],
                            }

            time.sleep(1)

        except Exception as e:
            print(f"    Error mining '{title}': {e}")

    all_foods  = list(set(all_foods))
    all_places = list(set(all_places))

    print(f"\n  Wikipedia mining summary:")
    print(f"    Articles mined:      {len(all_articles)}")
    print(f"    Nearby geo articles: {len(nearby_places)}")
    print(f"    Food mentions:       {len(all_foods)}")
    print(f"    Place mentions:      {len(all_places)}")
    print(f"    Historical events:   {len(all_events)}")

    output = {
        "city":              city_name,
        "generated_at":      datetime.utcnow().isoformat(),
        "source":            "Wikipedia",
        "license":           "CC BY-SA 3.0 — https://creativecommons.org/licenses/by-sa/3.0/",
        "articles":          all_articles,
        "nearby_geo_places": nearby_places,
        "food_mentions":     all_foods,
        "place_mentions":    all_places,
        "historical_events": sorted(all_events, key=lambda x: x.get("year", 9999))[:100],
        "summary": {
            "articles_mined":     len(all_articles),
            "nearby_places":      len(nearby_places),
            "food_mentions":      len(all_foods),
            "place_mentions":     len(all_places),
            "historical_events":  len(all_events),
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  Saved → {output_path}")
    return output


if __name__ == "__main__":
    from city_profiles.mangalore_profile import MANGALORE
    mine_wikipedia_deep(
        primary_articles = MANGALORE.wikipedia_articles,
        city_name        = MANGALORE.display_name,
        output_path      = f"data_core/{MANGALORE.city_id}_wikipedia_deep.json",
    )