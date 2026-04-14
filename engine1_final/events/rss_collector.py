"""
events/rss_collector.py
========================================================

Public RSS Event Collector
--------------------------------------------------------

Fetches events from:
✔ Local news portals (RSS only)
✔ Cultural boards
✔ Festival announcement feeds
✔ Community event feeds

This module ONLY consumes official RSS feeds.
No scraping. No HTML parsing.

Compliance:
✔ Publicly available RSS only
✔ Source attribution included
✔ No permanent storage (TTL handled elsewhere)
✔ No personal data collection
✔ Past-event filtering enabled

========================================================
"""

import feedparser
import time
import hashlib
from datetime import datetime
from typing import List, Dict

from events.config_runtime import (
    REQUEST_DELAY_SECONDS,
    ENABLE_RATE_LIMITING,
    REJECT_EVENTS_WITHOUT_DATE,
    REJECT_PAST_EVENTS,
)

# =====================================================
# CONFIGURABLE RSS SOURCES
# =====================================================

RSS_EVENT_FEEDS = [
    {
        "name": "Udayavani Events",
        "url": "https://www.udayavani.com/category/events/feed"
    },
    {
        "name": "The Hindu - Karnataka",
        "url": "https://www.thehindu.com/news/national/karnataka/feeder/default.rss"
    },
    {
        "name": "Mangalore Today",
        "url": "https://www.mangaloretoday.com/rss"
    }
]


# =====================================================
# MAIN ENTRY FUNCTION
# =====================================================

from events.source_registry import SourceRegistry

def fetch_rss_events() -> List[Dict]:

    all_events = []

    for source in RSS_EVENT_FEEDS:

        if not SourceRegistry.validate_source(source["name"]):
            continue

        events = fetch_single_feed(source["url"], source["name"])
        all_events.extend(events)

        if ENABLE_RATE_LIMITING:
            time.sleep(REQUEST_DELAY_SECONDS)

    return all_events


# =====================================================
# FETCH SINGLE FEED
# =====================================================

def fetch_single_feed(feed_url: str, source_name: str) -> List[Dict]:

    try:
        feed = feedparser.parse(feed_url)
        events = []

        for entry in feed.entries:
            normalized = normalize_rss_entry(entry, source_name)
            if normalized:
                events.append(normalized)

        return events

    except Exception as e:
        print(f"RSS fetch failed for {source_name}: {str(e)}")
        return []


# =====================================================
# NORMALIZE ENTRY
# =====================================================

def normalize_rss_entry(entry, source_name: str) -> Dict:

    try:
        title = entry.get("title", "Untitled Event")
        link = entry.get("link")

        date_string = (
            entry.get("published")
            or entry.get("updated")
            or None
        )

        event_date = parse_date_safely(date_string)

        if REJECT_EVENTS_WITHOUT_DATE and not event_date:
            return None

        if REJECT_PAST_EVENTS and event_date:
            if event_date < datetime.utcnow():
                return None

        # Create stable unique ID
        unique_string = title + (link or "")
        event_id = "rss_" + hashlib.md5(unique_string.encode()).hexdigest()

        return {
            "id": event_id,
            "name": title,
            "category": "events",
            "type": "media_event",
            "venue": "See official article",
            "date": event_date.isoformat() if event_date else None,
            "source": source_name,
            "source_url": link,
            "status": "active"
        }

    except Exception:
        return None


# =====================================================
# SAFE DATE PARSER
# =====================================================

def parse_date_safely(date_string: str):

    if not date_string:
        return None

    try:
        parsed = feedparser._parse_date(date_string)
        if parsed:
            return datetime(*parsed[:6])
        return None
    except Exception:
        return None
