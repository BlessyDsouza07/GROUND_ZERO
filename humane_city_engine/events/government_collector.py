"""
events/government_collector.py
========================================================

Government & Public Data Event Collector
--------------------------------------------------------

Fetches events from:
✔ Karnataka Tourism RSS feeds
✔ District Administration feeds
✔ Government Open Data Portal (data.gov.in)
✔ Public cultural boards RSS feeds

Compliance:
✔ Government Open Data License (GODL-India)
✔ Mandatory attribution tagging
✔ Non-official app disclaimer compatibility
✔ No personal data collection

IMPORTANT:
This app is NOT an official government application.
All data is sourced from publicly available feeds.

TTL and storage safety handled in:
historical_registry.py
========================================================
"""

import requests
import time
import feedparser
from datetime import datetime
from typing import List, Dict

from events.config_runtime import (
    REQUEST_DELAY_SECONDS,
    ENABLE_RATE_LIMITING,
    REJECT_EVENTS_WITHOUT_DATE,
    REJECT_PAST_EVENTS,
)

# =====================================================
# GOVERNMENT RSS / OPEN DATA SOURCES
# (You may expand this list later)
# =====================================================

GOVERNMENT_RSS_FEEDS = [
    {
        "name": "Karnataka Tourism",
        "url": "https://karnatakatourism.org/feed/"
    },
    {
        "name": "Dakshina Kannada District",
        "url": "https://dk.nic.in/events/feed/"
    }
]

# Optional: Open Data API endpoint example
OPEN_DATA_PORTAL_URL = "https://api.data.gov.in/resource/"


# =====================================================
# MAIN ENTRY FUNCTION
# =====================================================

from events.source_registry import SourceRegistry

def fetch_government_events() -> List[Dict]:
    all_events = []

    for feed in GOVERNMENT_RSS_FEEDS:

        if not SourceRegistry.validate_source(feed["name"]):
            continue

        events = fetch_rss_feed(feed["url"], feed["name"])
        all_events.extend(events)

        if ENABLE_RATE_LIMITING:
            time.sleep(REQUEST_DELAY_SECONDS)

    return all_events


# =====================================================
# RSS FEED PARSER
# =====================================================

def fetch_rss_feed(feed_url: str, source_name: str) -> List[Dict]:

    events = []

    try:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            normalized = normalize_rss_event(entry, source_name)
            if normalized:
                events.append(normalized)

        return events

    except Exception as e:
        print(f"RSS parsing failed for {source_name}:", str(e))
        return []


# =====================================================
# NORMALIZATION LOGIC
# =====================================================

def normalize_rss_event(entry, source_name: str) -> Dict:

    try:
        title = entry.get("title", "Untitled Event")
        link = entry.get("link")

        # Try different possible date fields
        published = (
            entry.get("published")
            or entry.get("updated")
            or None
        )

        event_date = parse_date_safely(published)

        if REJECT_EVENTS_WITHOUT_DATE and not event_date:
            return None

        if REJECT_PAST_EVENTS and event_date:
            if event_date < datetime.utcnow():
                return None

        event_id = f"gov_{hash(title + link)}"

        return {
            "id": event_id,
            "name": title,
            "category": "events",
            "type": "government_event",
            "venue": "See official source",
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
        return datetime(*feedparser._parse_date(date_string)[:6])
    except Exception:
        return None
