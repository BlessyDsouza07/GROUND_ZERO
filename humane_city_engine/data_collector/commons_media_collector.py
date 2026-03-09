"""
data_collector/commons_media_collector.py

WIKIMEDIA COMMONS COLLECTOR — real, community-contributed photos.

WHY this matters for bias-free data:
  Stock photo libraries and hotel photo feeds are curated to sell.
  Google Maps photos are gated and commercially influenced.
  Wikimedia Commons photos are:
  - Uploaded by local photographers, travellers, historians
  - Freely licensed (CC BY, CC BY-SA, or public domain)
  - Categorised by place — searchable by city, landmark, category
  - Include EXIF data with GPS coordinates in many cases
  - Include rare historical photos of places

WHAT WE COLLECT per landmark:
  - Photo URLs (thumbnail + full)
  - Photographer (attribution)
  - License
  - Upload date
  - Description / caption
  - GPS if available
  - Category links (what other commons categories this is tagged in)

APIs USED:
  - Wikimedia Commons API (action=query) — free, no key
  - Wikipedia Pageimages API — free, no key
  License: Various CC licenses — all free for non-commercial use
"""

import requests
import json
import os
import time
from typing import List, Dict, Optional
from datetime import datetime


COMMONS_API   = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "HumaneCityEngine/3.0 (open-source city guide)"}

THUMB_WIDTH = 640  # px for thumbnail


def _get_commons_category_files(category: str, max_files: int = 12) -> List[Dict]:
    """
    Get files from a Wikimedia Commons category.
    Category names: "Category:Mangalore" → pass just "Mangalore"
    """
    params = {
        "action":    "query",
        "list":      "categorymembers",
        "cmtitle":   f"Category:{category}",
        "cmtype":    "file",
        "cmlimit":   str(max_files),
        "format":    "json",
    }
    try:
        resp = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        members = resp.json().get("query", {}).get("categorymembers", [])
        return [{"title": m["title"], "category": category} for m in members]
    except Exception as e:
        print(f"    Category error ({category}): {e}")
        return []


def _get_file_info(file_title: str) -> Optional[Dict]:
    """
    Get detailed info for one Commons file: URL, license, author, description.
    """
    params = {
        "action":   "query",
        "titles":   file_title,
        "prop":     "imageinfo",
        "iiprop":   "url|extmetadata|dimensions|mime",
        "iiurlwidth": THUMB_WIDTH,
        "format":   "json",
    }
    try:
        resp = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            ii_list = page.get("imageinfo", [])
            if ii_list:
                ii = ii_list[0]
                meta = ii.get("extmetadata", {})
                return {
                    "file":        file_title,
                    "url":         ii.get("url", ""),
                    "thumb_url":   ii.get("thumburl", ""),
                    "width":       ii.get("width"),
                    "height":      ii.get("height"),
                    "mime":        ii.get("mime", ""),
                    "license":     meta.get("LicenseShortName", {}).get("value", ""),
                    "license_url": meta.get("LicenseUrl", {}).get("value", ""),
                    "author":      meta.get("Artist", {}).get("value", ""),
                    "description": meta.get("ImageDescription", {}).get("value", "")[:200],
                    "date":        meta.get("DateTimeOriginal", {}).get("value", "")
                                or meta.get("DateTime", {}).get("value", ""),
                    "source":      "Wikimedia Commons",
                }
    except Exception as e:
        pass
    return None


def _get_wikipedia_page_image(article_title: str) -> Optional[Dict]:
    """Get the main image for a Wikipedia article."""
    params = {
        "action":  "query",
        "titles":  article_title,
        "prop":    "pageimages",
        "pithumbsize": THUMB_WIDTH,
        "format":  "json",
    }
    try:
        resp = requests.get(WIKIPEDIA_API, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb:
                return {
                    "thumb_url":  thumb.get("source", ""),
                    "width":      thumb.get("width"),
                    "height":     thumb.get("height"),
                    "source":     "Wikipedia",
                    "article":    article_title,
                    "license":    "CC BY-SA",
                }
    except Exception:
        pass
    return None


def _search_commons(query: str, max_results: int = 8) -> List[Dict]:
    """Full-text search on Wikimedia Commons for images related to a query."""
    params = {
        "action":     "query",
        "list":       "search",
        "srsearch":   f"{query} filetype:image",
        "srnamespace": "6",   # File namespace
        "srlimit":    str(max_results),
        "format":     "json",
    }
    try:
        resp = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json().get("query", {}).get("search", [])
    except Exception:
        return []


def collect_media_for_city(
    city_name:          str,
    commons_categories: List[str],
    wikipedia_articles: List[str],
    output_path:        str,
    max_per_category:   int = 8,
) -> Dict:
    """
    Collect Wikimedia Commons photos for a city.

    Args:
        city_name:           City display name
        commons_categories:  List of Commons category names to collect from
                             e.g. ["Mangalore", "Beaches in Karnataka", "Kadri Manjunath Temple"]
        wikipedia_articles:  List of Wikipedia article titles for page images
        output_path:         Where to save JSON
        max_per_category:    Max files per category

    Returns:
        Dict saved to output_path
    """

    print(f"\n  Commons Media Collector — {city_name}")
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    all_media: Dict[str, Dict] = {}  # keyed by file title for dedup

    # ── Category-based collection ──────────────────────────────
    print(f"  Scanning {len(commons_categories)} Commons categories...")
    for category in commons_categories:
        files = _get_commons_category_files(category, max_per_category)
        print(f"    Category '{category}': {len(files)} files")
        for f in files:
            title = f["title"]
            if title not in all_media:
                time.sleep(0.3)
                info = _get_file_info(title)
                if info:
                    info["commons_category"] = category
                    all_media[title] = info
        time.sleep(1)

    # ── Wikipedia page images ──────────────────────────────────
    print(f"  Fetching Wikipedia page images ({len(wikipedia_articles)} articles)...")
    wiki_images = []
    for article in wikipedia_articles:
        img = _get_wikipedia_page_image(article)
        if img:
            wiki_images.append(img)
        time.sleep(0.5)
    print(f"    Got {len(wiki_images)} Wikipedia images")

    # ── Summary ───────────────────────────────────────────────
    commons_list = list(all_media.values())
    # Filter to actual images (not SVGs or maps)
    photos = [m for m in commons_list if m.get("mime", "").startswith("image/jpeg") or "jpg" in m.get("url", "").lower()]
    all_items = photos + wiki_images

    print(f"  ✓ Total media: {len(all_items)} items ({len(photos)} Commons photos + {len(wiki_images)} Wikipedia images)")

    output = {
        "city":            city_name,
        "generated_at":    datetime.utcnow().isoformat(),
        "sources":         ["Wikimedia Commons", "Wikipedia"],
        "license_note":    "All items are freely licensed — check individual item license_url for attribution requirements",
        "commons_photos":  photos,
        "wikipedia_images": wiki_images,
        "all_media":       all_items,
        "summary": {
            "commons_photos":   len(photos),
            "wikipedia_images": len(wiki_images),
            "total":            len(all_items),
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  Saved → {output_path}")
    return output


def build_commons_categories_for_city(city_id: str, display_name: str) -> List[str]:
    """
    Generate a useful default list of Commons categories for any city.
    These are standard category naming conventions on Wikimedia Commons.
    """
    name = display_name
    return [
        name,
        f"Beaches in {name}",
        f"Temples in {name}",
        f"Churches in {name}",
        f"Markets in {name}",
        f"Streets in {name}",
        f"Buildings in {name}",
        f"Festivals in {name}",
        f"Food of {name}",
        f"Heritage buildings in {name}",
        f"People of {name}",
        f"Maps of {name}",
    ]


if __name__ == "__main__":
    from city_profiles.mangalore_profile import MANGALORE
    cats = build_commons_categories_for_city(MANGALORE.city_id, MANGALORE.display_name)
    collect_media_for_city(
        city_name          = MANGALORE.display_name,
        commons_categories = cats,
        wikipedia_articles = MANGALORE.wikipedia_articles[:10],
        output_path        = f"data_core/{MANGALORE.city_id}_media.json",
    )