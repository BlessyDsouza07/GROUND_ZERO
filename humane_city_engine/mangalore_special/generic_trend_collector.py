"""
data_collector/generic_trend_collector.py  [SCALABLE VERSION]

Builds trend signals (Wikipedia pageviews + RSS news) for ANY city.
Reads everything from CityProfile — no city-specific code here.

Output: data_core/<city_id>_trends.json
"""

import requests
import json
import os
import time
from typing import List, Dict
from datetime import datetime, timedelta

from city_profiles.city_profile import CityProfile

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

HEADERS = {"User-Agent": "HumaneCityEngine/3.0 (open-source city guide)"}
PAGEVIEWS_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def _fetch_pageviews(article: str, days: int = 30) -> Dict:
    """Fetch Wikipedia pageviews for one article."""
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=days)
    start_str = start.strftime("%Y%m%d") + "00"
    end_str   = end.strftime("%Y%m%d") + "00"

    url = f"{PAGEVIEWS_BASE}/en.wikipedia/all-access/all-agents/{article}/daily/{start_str}/{end_str}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            total = sum(i.get("views", 0) for i in items)
            if total > 0:
                return {
                    "title": article.replace("_", " "),
                    "wikipedia_views_30d": total,
                    "daily_avg": round(total / max(len(items), 1), 1),
                    "days_covered": len(items),
                    "source": "Wikipedia Pageviews API",
                }
    except Exception as e:
        pass

    return {}


def _fetch_rss_feed(feed_config, city_keywords: List[str]) -> List[Dict]:
    """Fetch and filter one RSS feed for city-relevant articles."""
    if not HAS_FEEDPARSER:
        return []

    items = []
    try:
        feed = feedparser.parse(feed_config.url)
        for entry in feed.entries[:20]:
            title = getattr(entry, "title", "")
            title_lower = title.lower()
            is_relevant = any(kw.lower() in title_lower for kw in city_keywords)
            items.append({
                "title": title,
                "link": getattr(entry, "link", ""),
                "published": getattr(entry, "published", ""),
                "source": feed_config.name,
                "language": feed_config.language,
                "is_city_relevant": is_relevant,
            })
        time.sleep(0.5)
    except Exception as e:
        print(f"    RSS error ({feed_config.name}): {e}")

    return items


def build_trend_dataset(profile: CityProfile) -> Dict:
    """
    Build trend dataset for any city using its CityProfile.

    Args:
        profile: CityProfile for the target city

    Returns:
        Dict saved to profile.trends_path
    """

    print(f"\n  Building trend dataset for {profile.display_name}...")
    os.makedirs("data_core", exist_ok=True)

    # ── RSS NEWS ──────────────────────────────────────────────
    all_rss = []
    if HAS_FEEDPARSER:
        print(f"  Fetching RSS feeds ({len(profile.rss_feeds)} configured)...")
        for feed_config in profile.rss_feeds:
            items = _fetch_rss_feed(feed_config, profile.search_keywords)
            all_rss.extend(items)
            relevant = sum(1 for i in items if i["is_city_relevant"])
            print(f"    {feed_config.name}: {len(items)} articles ({relevant} relevant)")
    else:
        print("  feedparser not installed — skipping RSS. Run: pip install feedparser")

    # ── WIKIPEDIA PAGEVIEWS ───────────────────────────────────
    print(f"  Fetching Wikipedia pageviews ({len(profile.wikipedia_articles)} articles)...")
    wiki_trends = []
    for article in profile.wikipedia_articles:
        result = _fetch_pageviews(article)
        if result:
            wiki_trends.append(result)
            print(f"    {result['title']}: {result['wikipedia_views_30d']:,} views")
        else:
            print(f"    {article}: no data")
        time.sleep(0.5)

    # ── ASSEMBLE ──────────────────────────────────────────────
    all_signals = wiki_trends + [
        {
            "title": item["title"],
            "source": item["source"],
            "is_city_relevant": item["is_city_relevant"],
            "published": item.get("published", ""),
        }
        for item in all_rss
    ]

    dataset = {
        "city":          profile.display_name,
        "city_id":       profile.city_id,
        "generated_at":  datetime.utcnow().isoformat(),
        "sources": ["Wikipedia Pageviews API", "RSS Feeds"],

        "wikipedia_trends": wiki_trends,
        "rss_articles": all_rss,
        "all_signals": all_signals,

        "summary": {
            "wikipedia_articles_tracked": len(wiki_trends),
            "rss_articles": len(all_rss),
            "rss_relevant": sum(1 for i in all_rss if i.get("is_city_relevant")),
            "total_signals": len(all_signals),
        }
    }

    with open(profile.trends_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Trend dataset saved ({len(all_signals)} signals): {profile.trends_path}")

    return dataset


if __name__ == "__main__":
    from city_profiles.mangalore_profile import MANGALORE
    build_trend_dataset(MANGALORE)