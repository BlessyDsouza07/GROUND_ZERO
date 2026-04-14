"""
data_collector/wikipedia_enricher.py

Wikipedia REST API Enricher for Engine 1.

Wikipedia is:
  - Free, no API key, CC BY-SA 3.0
  - Human-written, verified factual descriptions
  - Available in English and Kannada
  - 3rd independent source for multi-source consensus

What this module does:
  - Looks up OSM entities that have a wikipedia= tag
  - Fetches clean summaries from Wikipedia REST API
  - Extracts page quality signals (stub vs full article)
  - Stores descriptions and links for transparency cards
  - Adds "public_media" as a verified source category

Source label: "public_media"
"""

import json
import os
import time
import requests
from typing import Optional, Dict, List
from utils.logger import get_logger
from utils.rate_limiter import sleep_between_calls, WIKI_DELAY

logger = get_logger("WikipediaEnricher")

WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"

HEADERS = {
    "User-Agent": "GroundZeroEngine/1.0 (educational project; respectful API use)"
}


# ============================================================
# FETCH ONE WIKIPEDIA SUMMARY
# ============================================================

def fetch_wikipedia_summary(title: str) -> Optional[Dict]:
    """
    Fetch Wikipedia page summary for a given title.

    Args:
        title: Wikipedia page title (e.g. "Panambur_Beach")

    Returns:
        Dict with description, extract, quality signals — or None
    """

    title_encoded = title.strip().replace(" ", "_")

    sleep_between_calls(WIKI_DELAY)

    try:
        response = requests.get(
            f"{WIKIPEDIA_REST}/{title_encoded}",
            headers=HEADERS,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            return normalize_wikipedia_response(data)

        elif response.status_code == 404:
            logger.debug(f"Wikipedia: no article for '{title}'")
            return None

        else:
            logger.warning(f"Wikipedia HTTP {response.status_code} for '{title}'")
            return None

    except Exception as e:
        logger.error(f"Wikipedia fetch error for '{title}': {e}")
        return None


# ============================================================
# NORMALIZE WIKIPEDIA RESPONSE
# ============================================================

def normalize_wikipedia_response(data: Dict) -> Dict:
    """
    Extract key fields from Wikipedia REST API response.

    Quality signals:
    - "stub" pages (very short) score lower
    - Pages with coordinates get a bonus (confirms geo accuracy)
    - Pages in multiple languages = stronger signal
    """

    extract = data.get("extract", "")
    title = data.get("title", "")
    page_id = data.get("pageid", 0)
    lang = data.get("lang", "en")

    # Quality estimate: longer articles = more established place
    word_count = len(extract.split()) if extract else 0
    is_stub = word_count < 50

    # Coordinates in Wikipedia confirm geo accuracy
    has_coordinates = bool(data.get("coordinates"))

    quality_score = 0.5  # base
    if not is_stub:      quality_score += 0.2
    if has_coordinates:  quality_score += 0.2
    if word_count > 200: quality_score += 0.1

    return {
        "wikipedia_title": title,
        "wikipedia_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "description": extract[:500] if extract else "",
        "word_count": word_count,
        "is_stub": is_stub,
        "has_coordinates": has_coordinates,
        "quality_score": round(min(quality_score, 1.0), 2),
        "source": "wikipedia",
        "source_category": "public_media",
        "page_id": page_id
    }


# ============================================================
# BATCH ENRICHMENT FROM OSM RAW FILE
# ============================================================

def enrich_from_osm_raw(
    osm_raw_path: str,
    output_path: str = "data_storage/raw/wikipedia_enrichment.json"
) -> Dict[str, Dict]:
    """
    Read OSM raw JSON, find all elements with wikipedia= tags,
    fetch their Wikipedia summaries.

    Returns:
        Dict: osm_id → wikipedia_data mapping
    """

    logger.info("WikipediaEnricher — Scanning OSM data for wikipedia= tags")

    with open(osm_raw_path, encoding="utf-8") as f:
        osm_data = json.load(f)

    enrichments: Dict[str, Dict] = {}
    checked = 0
    found = 0

    for element in osm_data.get("elements", []):
        tags = element.get("tags", {})
        wiki_tag = tags.get("wikipedia", "")

        if not wiki_tag:
            continue

        checked += 1

        # Wikipedia tags are in format "en:Article Title" or just "Article Title"
        if ":" in wiki_tag:
            lang, title = wiki_tag.split(":", 1)
            if lang != "en":
                # Try English Wikipedia anyway with just the title
                pass
        else:
            title = wiki_tag

        result = fetch_wikipedia_summary(title)

        if result:
            el_id = str(element.get("id"))
            enrichments[el_id] = result
            found += 1
            logger.debug(f"  ✓ '{title}' — quality: {result['quality_score']}")

    logger.info(f"  Wikipedia: checked {checked} tags, enriched {found} places")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enrichments, f, ensure_ascii=False, indent=2)

    return enrichments


# ============================================================
# STANDALONE RUN
# ============================================================

if __name__ == "__main__":
    # Quick test
    result = fetch_wikipedia_summary("Panambur Beach")
    if result:
        print(f"✅ Wikipedia test OK")
        print(f"   Title: {result['wikipedia_title']}")
        print(f"   Quality: {result['quality_score']}")
        print(f"   Description: {result['description'][:100]}...")
    else:
        print("❌ Wikipedia test failed")
