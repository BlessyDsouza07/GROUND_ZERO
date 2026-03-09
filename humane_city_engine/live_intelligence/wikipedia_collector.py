"""
live_intelligence/wikipedia_collector.py  [NEW FILE]

PURPOSE:
    Fetch real, structured knowledge about Mangalore places
    from Wikipedia's free REST API.

WHY THIS FILE IS NEW:
    The original mangalore_specialty_collector.py had a Wikipedia
    scraper using BeautifulSoup that just searched paragraph text
    for food keywords. It was brittle, slow, and collected very little.

    This file uses the official Wikipedia REST API:
    - 100% FREE — no API key required
    - Legal: Wikipedia content is CC BY-SA 3.0
    - Structured: returns JSON directly, no HTML scraping
    - Covers: Places, history, culture, food for Mangalore

DATA COLLECTED:
    - Place summaries (temple histories, beach descriptions)
    - Cultural information
    - Cuisine descriptions
    - Notable landmark details

WHAT TO ADD TO city_bootstrap.py:
    from live_intelligence.wikipedia_collector import enrich_entities_with_wikipedia
    entities = enrich_entities_with_wikipedia(entities)
"""

import requests
import time
from typing import List, Optional, Dict

WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"

# Rate limit: Wikipedia asks for max 1 req/sec
REQUEST_DELAY = 1.0


# ============================================================
# FETCH SINGLE ARTICLE SUMMARY
# ============================================================

def get_wikipedia_summary(title: str) -> Optional[Dict]:
    """
    Fetch a Wikipedia article summary by page title.

    Returns:
        Dict with: title, description, extract (first paragraph),
                   thumbnail_url, coordinates, wiki_url
    OR None if not found.

    API: https://en.wikipedia.org/api/rest_v1/#/Page_content/get_page_summary__title_
    License: CC BY-SA 3.0
    """

    try:
        url = f"{WIKIPEDIA_API}/{requests.utils.quote(title)}"

        response = requests.get(
            url,
            headers={"User-Agent": "HumaneCityEngine/1.0 (city-guide-project)"},
            timeout=10
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        return {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "extract": data.get("extract", "")[:500],   # first ~500 chars
            "thumbnail": data.get("thumbnail", {}).get("source"),
            "coordinates": data.get("coordinates"),     # lat/lon if geo article
            "wiki_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "source": "Wikipedia",
            "license": "CC BY-SA 3.0"
        }

    except Exception as e:
        print(f"  Wikipedia API error for '{title}': {e}")
        return None


# ============================================================
# SEARCH WIKIPEDIA
# ============================================================

def search_wikipedia(query: str, limit: int = 5) -> List[Dict]:
    """
    Search Wikipedia for articles matching a query.
    Useful for finding relevant pages for place names.
    """

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "origin": "*"
    }

    try:
        response = requests.get(
            WIKIPEDIA_SEARCH,
            params=params,
            headers={"User-Agent": "HumaneCityEngine/1.0"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("query", {}).get("search", []):
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", "").replace("<span class='searchmatch'>", "").replace("</span>", ""),
                "pageid": item.get("pageid")
            })

        return results

    except Exception as e:
        print(f"  Wikipedia search error for '{query}': {e}")
        return []


# ============================================================
# MANGALORE-SPECIFIC KNOWLEDGE BASE
# All key Wikipedia articles pre-identified for Mangalore
# ============================================================

MANGALORE_WIKIPEDIA_PAGES = [
    # Beaches
    "Panambur Beach",
    "Tannirbhavi Beach",
    "Ullal Beach",
    "Surathkal Beach",

    # Temples & Religious sites
    "Kadri Manjunath Temple",
    "Kudroli Gokarnath Temple",
    "Mangaladevi Temple, Mangalore",
    "St Aloysius Chapel",
    "Milagres Church, Mangalore",
    "Bejai Church",
    "Mangalore Jama Masjid",
    "Idgah Mosque, Mangalore",

    # Historical / Heritage
    "Sultan Battery, Mangalore",
    "Mangalore Fort",
    "Ullal Fort",
    "Tippi Sahib of Mangalore",  # Historical context

    # Nature
    "Pilikula Nisargadhama",
    "Netravati River",
    "Gurpur River",
    "Phalguni River",

    # Food & Cuisine
    "Tulu Nadu cuisine",
    "Neer dosa",
    "Kori rotti",
    "Goli baje",
    "Mangalore bun",
    "Kane fish",

    # Culture
    "Tulu language",
    "Yakshagana",
    "Kambala (Karnataka)",
    "Mangalore Dasara",
    "Mangalorean Catholics",

    # City overview
    "Mangalore",
    "Dakshina Kannada",
]


# ============================================================
# BUILD MANGALORE KNOWLEDGE HUB
# ============================================================

def build_mangalore_knowledge() -> Dict:
    """
    Fetch Wikipedia summaries for all key Mangalore articles.

    Returns a structured knowledge dict ready to merge with entities.
    Respects Wikipedia's rate limit (1 req/sec).
    """

    knowledge = {
        "places": [],
        "food": [],
        "culture": [],
        "history": [],
        "nature": [],
        "fetched_count": 0,
        "failed_count": 0
    }

    print(f"  Fetching Wikipedia knowledge ({len(MANGALORE_WIKIPEDIA_PAGES)} articles)...")

    for title in MANGALORE_WIKIPEDIA_PAGES:

        summary = get_wikipedia_summary(title)

        if summary and summary.get("extract"):

            # Categorize
            if any(kw in title.lower() for kw in ["beach", "park", "river", "lake", "forest"]):
                knowledge["nature"].append(summary)
            elif any(kw in title.lower() for kw in ["dosa", "rotti", "fish", "bun", "cuisine", "food"]):
                knowledge["food"].append(summary)
            elif any(kw in title.lower() for kw in ["temple", "church", "mosque", "chapel", "dargah"]):
                knowledge["places"].append(summary)
            elif any(kw in title.lower() for kw in ["fort", "battery", "history", "historical"]):
                knowledge["history"].append(summary)
            else:
                knowledge["culture"].append(summary)

            knowledge["fetched_count"] += 1

        else:
            knowledge["failed_count"] += 1

        # Respect Wikipedia rate limit
        time.sleep(REQUEST_DELAY)

    print(f"  Wikipedia: {knowledge['fetched_count']} articles fetched, "
          f"{knowledge['failed_count']} not found")

    return knowledge


# ============================================================
# ENRICH ENTITY WITH WIKIPEDIA DESCRIPTION
# (called from city_bootstrap.py after normalization)
# ============================================================

def enrich_entities_with_wikipedia(entities: list) -> list:
    """
    For each BaseEntity, search Wikipedia and attach
    a real description if found.

    Adds to decision_trace: WIKI_DESCRIPTION:<text>

    Args:
        entities: List[BaseEntity] from normalizer

    Returns:
        Same list, entities now have Wikipedia descriptions attached
    """

    enriched = 0

    for entity in entities:

        # Only search for well-known types worth Wikipedia enrichment
        if entity.category not in [
            "tourism", "historic", "attraction", "museum",
            "beach", "temple", "church", "mosque", "viewpoint",
            "natural", "park", "nature_reserve"
        ]:
            continue

        # Search Wikipedia for this place
        results = search_wikipedia(f"{entity.name} Mangalore", limit=1)

        if results:
            top = results[0]
            summary = get_wikipedia_summary(top["title"])

            if summary and summary.get("extract"):
                entity.decision_trace.append(
                    f"WIKI_DESCRIPTION:{summary['extract'][:300]}"
                )
                entity.decision_trace.append(
                    f"WIKI_URL:{summary.get('wiki_url', '')}"
                )

                # Having a Wikipedia article = strong authenticity signal
                # Bump structural score slightly
                entity.structural_score = min(entity.structural_score + 0.05, 1.0)

                enriched += 1
                time.sleep(REQUEST_DELAY)

    print(f"  Wikipedia enrichment: {enriched} entities enriched")

    return entities


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    import json

    print("Testing Wikipedia API...")

    summary = get_wikipedia_summary("Panambur Beach")
    if summary:
        print("\nPanambur Beach summary:")
        print(f"  Description: {summary['description']}")
        print(f"  Extract: {summary['extract'][:200]}...")

    print("\n\nBuilding full Mangalore knowledge hub (this takes ~60 seconds)...")
    knowledge = build_mangalore_knowledge()
    print(f"\nTotal articles:")
    for k, v in knowledge.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} articles")