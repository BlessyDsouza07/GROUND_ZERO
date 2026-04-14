"""
events/live_events_rss.py

Free live events collector — no API keys needed.

Sources:
  - Karnataka Tourism RSS
  - Dakshina Kannada District RSS
  - Udayavani events feed
  - The Hindu Karnataka feed
  - Mangalore Today RSS

Called by:
  - realtime_pipeline/live_update_scheduler.py (Engine 4)
  - Can also be called standalone from Engine 1 for event seeding
"""

import feedparser
import hashlib
import time
from datetime import datetime
from typing import List, Dict

from events.config_runtime import (
    REQUEST_DELAY_SECONDS,
    ENABLE_RATE_LIMITING,
    REJECT_PAST_EVENTS,
)
from utils.logger import get_logger

logger = get_logger("LiveEventsRSS")

# ──────────────────────────────────────────────────────────
# ALL FREE RSS SOURCES IN ONE PLACE
# ──────────────────────────────────────────────────────────

ALL_RSS_FEEDS = [
    {"name": "Karnataka Tourism",       "url": "https://karnatakatourism.org/feed/",                          "type": "government"},
    {"name": "Dakshina Kannada Dist",   "url": "https://dk.nic.in/events/feed/",                              "type": "government"},
    {"name": "Udayavani Events",        "url": "https://www.udayavani.com/category/events/feed",              "type": "media"},
    {"name": "The Hindu Karnataka",     "url": "https://www.thehindu.com/news/national/karnataka/feeder/default.rss", "type": "media"},
    {"name": "Mangalore Today",         "url": "https://www.mangaloretoday.com/rss",                          "type": "media"},
]


def fetch_all_live_events(include_rss: bool = True) -> List[Dict]:
    """
    Fetch events from all configured free RSS sources.
    Returns deduplicated list of event dicts.
    """

    all_events: List[Dict] = []
    seen_signatures = set()

    if not include_rss:
        return []

    for feed in ALL_RSS_FEEDS:
        try:
            logger.info(f"  RSS: fetching from {feed['name']}")
            parsed = feedparser.parse(feed["url"])

            for entry in parsed.entries:
                event = _normalize_entry(entry, feed["name"], feed["type"])
                if not event:
                    continue

                sig = hashlib.md5(
                    (event["name"] + (event.get("date") or "")).encode()
                ).hexdigest()

                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    all_events.append(event)

            if ENABLE_RATE_LIMITING:
                time.sleep(REQUEST_DELAY_SECONDS)

        except Exception as e:
            logger.warning(f"  RSS failed for {feed['name']}: {e}")
            continue

    logger.info(f"  Live events collected: {len(all_events)}")
    return all_events


def _normalize_entry(entry, source_name: str, source_type: str):
    """Normalize a feedparser entry to a clean event dict."""
    try:
        title = entry.get("title", "").strip()
        if not title:
            return None

        link = entry.get("link", "")

        date_raw = entry.get("published") or entry.get("updated") or None
        event_date = _parse_date(date_raw)

        if REJECT_PAST_EVENTS and event_date and event_date < datetime.utcnow():
            return None

        return {
            "id": "rss_" + hashlib.md5((title + link).encode()).hexdigest(),
            "name": title,
            "category": "events",
            "type": f"{source_type}_event",
            "venue": "See official source",
            "date": event_date.isoformat() if event_date else None,
            "source": source_name,
            "source_url": link,
            "status": "active"
        }
    except Exception:
        return None


def _parse_date(date_string):
    if not date_string:
        return None
    try:
        parsed = feedparser._parse_date(date_string)
        if parsed:
            return datetime(*parsed[:6])
        return None
    except Exception:
        return None
