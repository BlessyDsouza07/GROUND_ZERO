"""
data_collector/generic_trend_collector.py

GENERIC TREND COLLECTOR
────────────────────────────────────────────────────────────
Called by rare_data_orchestrator as: build_trend_dataset(profile)

Collects trending signals from 100% free, legal, open sources:
  1. Wikipedia Pageviews API  — how many people read each article
  2. RSS news feeds           — recent local news headlines
  3. Wikipedia recent changes — which articles are being edited

Output: data_core/<city_id>_trends.json
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from xml.etree import ElementTree

import requests

HEADERS = {"User-Agent": "HumaneCityEngine/3.0 (trend collector, non-commercial)"}
PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents"
WIKI_REST     = "https://en.wikipedia.org/api/rest_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sleep(s: float = 1.0):
    time.sleep(s)


# ── 1. WIKIPEDIA PAGEVIEWS ─────────────────────────────────────

def fetch_pageviews(article: str, days: int = 30) -> Dict:
    """Fetch last N days of pageview data for a Wikipedia article."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    s_str = start.strftime("%Y%m%d")
    e_str = end.strftime("%Y%m%d")

    url = f"{PAGEVIEWS_API}/{article.replace(' ','_')}/daily/{s_str}/{e_str}"
    try:
        _sleep(0.4)
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            items = r.json().get("items", [])
            views = [item.get("views", 0) for item in items]
            total = sum(views)
            avg   = round(total / len(views), 1) if views else 0
            peak  = max(views) if views else 0
            return {
                "article":      article,
                "total_views":  total,
                "avg_daily":    avg,
                "peak_daily":   peak,
                "days_tracked": len(views),
                "trend":        _trend_direction(views),
                "source":       "Wikimedia Pageviews API",
            }
    except Exception as e:
        pass
    return {"article": article, "total_views": 0, "avg_daily": 0,
            "peak_daily": 0, "days_tracked": 0, "trend": "unknown", "source": "Wikimedia Pageviews API"}


def _trend_direction(views: List[int]) -> str:
    """Simple trend: compare first half vs second half."""
    if len(views) < 4:
        return "stable"
    mid   = len(views) // 2
    first = sum(views[:mid]) / mid
    second = sum(views[mid:]) / (len(views) - mid)
    if second > first * 1.15:  return "rising"
    if second < first * 0.85:  return "falling"
    return "stable"


# ── 2. RSS NEWS FEEDS ─────────────────────────────────────────

def fetch_rss(url: str, keywords: List[str], max_items: int = 20) -> List[Dict]:
    """Fetch RSS feed and filter for city-relevant articles."""
    try:
        _sleep(1.5)
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []

        root = ElementTree.fromstring(r.content)
        channel = root.find("channel")
        if channel is None:
            return []

        items = []
        kw_lower = [k.lower() for k in keywords]

        for item in channel.findall("item")[:50]:
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()

            # Relevance filter — must contain at least one keyword
            combined = (title + " " + desc).lower()
            if not any(kw in combined for kw in kw_lower):
                continue

            items.append({
                "title":       title,
                "description": desc[:200],
                "link":        link,
                "published":   pub,
                "source":      url,
                "matched_keywords": [kw for kw in keywords if kw.lower() in combined],
            })
            if len(items) >= max_items:
                break

        return items

    except Exception as e:
        print(f"      RSS error ({url[:50]}): {e}")
        return []


# ── 3. WIKIPEDIA RECENT CHANGES ───────────────────────────────

def fetch_wiki_recent_changes(articles: List[str]) -> List[Dict]:
    """Check which Wikipedia articles were recently edited (signals relevance)."""
    try:
        _sleep(1)
        # Use Wikipedia API to get recent changes for specific pages
        titles = "|".join(articles[:20])  # API limit
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop":   "revisions",
                "titles": titles,
                "rvprop": "timestamp|comment|size",
                "rvlimit": 1,
                "format": "json",
            },
            headers=HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return []

        pages = r.json().get("query", {}).get("pages", {})
        changes = []
        for pid, page in pages.items():
            if pid == "-1":
                continue
            revs = page.get("revisions", [{}])
            if revs:
                rev = revs[0]
                # Was it edited in last 30 days?
                ts = rev.get("timestamp","")
                if ts:
                    edit_dt = datetime.fromisoformat(ts.replace("Z","+00:00"))
                    days_ago = (datetime.now(timezone.utc) - edit_dt).days
                    if days_ago <= 30:
                        changes.append({
                            "article":  page.get("title",""),
                            "edited_days_ago": days_ago,
                            "comment":  rev.get("comment","")[:100],
                            "signal":   "recently_edited",
                        })
        return changes

    except Exception as e:
        print(f"      Wiki recent changes error: {e}")
        return []


# ── 4. WIKIPEDIA ARTICLE SUMMARIES (trending topics) ──────────

def fetch_trending_summaries(articles: List[str]) -> List[Dict]:
    """Get current Wikipedia summaries to detect content freshness."""
    summaries = []
    for article in articles[:20]:  # limit API calls
        try:
            _sleep(0.5)
            r = requests.get(
                f"{WIKI_REST}/page/summary/{article.replace(' ','_')}",
                headers=HEADERS, timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                summaries.append({
                    "article":     article,
                    "title":       data.get("title",""),
                    "description": data.get("description",""),
                    "extract":     data.get("extract","")[:300],
                    "thumbnail":   data.get("thumbnail",{}).get("source",""),
                    "last_edited": data.get("timestamp",""),
                })
        except:
            pass
    return summaries


# ════════════════════════════════════════════════════════════════
# MASTER BUILDER
# ════════════════════════════════════════════════════════════════

def build_trend_dataset(profile) -> Dict:
    """
    Main entry point called by rare_data_orchestrator.
    Uses profile.wikipedia_articles, profile.rss_feeds,
    profile.search_keywords, profile.trends_path.
    """
    print(f"\n  Trend Collector — {profile.display_name}")
    os.makedirs(os.path.dirname(profile.trends_path)
                if os.path.dirname(profile.trends_path) else ".", exist_ok=True)

    # ── Wikipedia pageviews ──
    print(f"  Fetching pageviews for {len(profile.wikipedia_articles)} articles...")
    pageviews = []
    for article in profile.wikipedia_articles:
        pv = fetch_pageviews(article, days=30)
        pageviews.append(pv)
    pageviews.sort(key=lambda x: -x.get("total_views", 0))

    top_articles = [p["article"] for p in pageviews[:5] if p["total_views"] > 0]
    print(f"    Top article: {pageviews[0]['article'] if pageviews else 'none'} "
          f"({pageviews[0].get('total_views',0):,} views/30d)" if pageviews else "")

    # ── RSS feeds ──
    all_articles = []
    print(f"  Fetching {len(profile.rss_feeds)} RSS feeds...")
    for feed in profile.rss_feeds:
        items = fetch_rss(feed.url, profile.search_keywords)
        for item in items:
            item["feed_name"] = feed.name
            item["feed_language"] = feed.language
        all_articles.extend(items)
        print(f"    {feed.name}: {len(items)} relevant articles")

    # ── Recent Wikipedia edits ──
    print(f"  Checking recent Wikipedia edits...")
    recent_edits = fetch_wiki_recent_changes(profile.wikipedia_articles)
    print(f"    Recently edited articles: {len(recent_edits)}")

    # ── Article summaries (current descriptions) ──
    print(f"  Fetching article summaries...")
    summaries = fetch_trending_summaries(profile.wikipedia_articles)
    print(f"    Summaries fetched: {len(summaries)}")

    # ── Assemble ──
    trending_keywords = _extract_trending_keywords(all_articles, profile.search_keywords)

    dataset = {
        "city":              profile.display_name,
        "city_id":           profile.city_id,
        "generated_at":      _now(),
        "window_days":       30,
        "sources": [
            "Wikimedia Pageviews API (CC0)",
            "RSS feeds (fair use, headlines only)",
            "Wikipedia API (CC BY-SA 3.0)",
        ],

        # Pageview signals
        "pageviews": {
            "articles":          pageviews,
            "top_articles":      top_articles,
            "total_views_30d":   sum(p.get("total_views",0) for p in pageviews),
            "rising_articles":   [p["article"] for p in pageviews if p.get("trend") == "rising"],
            "falling_articles":  [p["article"] for p in pageviews if p.get("trend") == "falling"],
        },

        # News signals
        "news": {
            "articles":            all_articles,
            "total_articles":      len(all_articles),
            "feeds_scanned":       len(profile.rss_feeds),
            "trending_keywords":   trending_keywords,
        },

        # Wikipedia edit signals
        "wikipedia_activity": {
            "recently_edited":     recent_edits,
            "edit_count_30d":      len(recent_edits),
            "summaries":           summaries,
        },

        # Derived intelligence
        "trend_signals": {
            "hot_topics":          _hot_topics(pageviews, all_articles),
            "seasonal_relevance":  _seasonal_relevance(profile),
            "city_search_volume":  "medium",   # qualitative — no paid API
            "tourist_interest_index": _tourist_interest(pageviews),
        },
    }

    with open(profile.trends_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(profile.trends_path) / 1024
    print(f"  ✓ Trends saved → {profile.trends_path}  ({size_kb:.0f} KB)")
    print(f"    Pageviews tracked: {len(pageviews)}")
    print(f"    News articles:     {len(all_articles)}")
    print(f"    Wiki edits (30d):  {len(recent_edits)}")

    return dataset


def _extract_trending_keywords(articles: List[Dict], base_keywords: List[str]) -> List[Dict]:
    """Count keyword frequency across news headlines."""
    counts: Dict[str, int] = {}
    for article in articles:
        text = (article.get("title","") + " " + article.get("description","")).lower()
        for kw in base_keywords:
            if kw.lower() in text:
                counts[kw] = counts.get(kw, 0) + 1
    return [{"keyword": k, "mentions": v}
            for k, v in sorted(counts.items(), key=lambda x: -x[1])]


def _hot_topics(pageviews: List[Dict], articles: List[Dict]) -> List[str]:
    """Identify hot topics from high pageviews + news coverage."""
    hot = []
    # Articles with >500 daily avg views
    hot += [p["article"] for p in pageviews if p.get("avg_daily", 0) > 500]
    # Topics appearing 3+ times in news
    topic_counts: Dict[str, int] = {}
    for a in articles:
        for kw in a.get("matched_keywords", []):
            topic_counts[kw] = topic_counts.get(kw, 0) + 1
    hot += [k for k, v in topic_counts.items() if v >= 3]
    return list(dict.fromkeys(hot))  # deduplicate preserving order


def _seasonal_relevance(profile) -> Dict:
    """Current month seasonal relevance for this city."""
    current_month = datetime.now(timezone.utc).month
    is_peak    = current_month in getattr(profile, "peak_season_months", [])
    is_monsoon = current_month in getattr(profile, "monsoon_months", [])
    return {
        "current_month":   current_month,
        "is_peak_season":  is_peak,
        "is_monsoon":      is_monsoon,
        "season_label":    "peak" if is_peak else "monsoon" if is_monsoon else "shoulder",
        "visit_recommended": is_peak and not is_monsoon,
    }


def _tourist_interest(pageviews: List[Dict]) -> float:
    """0–1 index: how much global interest does this city have right now."""
    total = sum(p.get("total_views", 0) for p in pageviews)
    # Scale: 0 = no interest, 1 = >100k views in 30 days across articles
    return round(min(1.0, total / 100000), 3)


if __name__ == "__main__":
    # Quick test with Mangalore profile
    import sys
    sys.path.insert(0, ".")
    from city_profiles.mangalore_profile import profile
    build_trend_dataset(profile)