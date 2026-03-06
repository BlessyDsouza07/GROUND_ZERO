"""
events/ticketing_collector.py
========================================================

Ticketing Collector (SourceRegistry Enforced)
--------------------------------------------------------

Sources:
✔ Ticketmaster Discovery API
✔ Eventbrite API

Governed by:
✔ SourceRegistry validation
✔ Runtime configuration rules
✔ Rate limiting policy
✔ Past event filtering
✔ Attribution enforcement

Storage & TTL handled separately in:
historical_registry.py
========================================================
"""

import os
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

from events.config_runtime import (
    REQUEST_DELAY_SECONDS,
    ENABLE_RATE_LIMITING,
    REJECT_EVENTS_WITHOUT_DATE,
    REJECT_PAST_EVENTS,
)

from events.source_registry import SourceRegistry


# =========================================================
# ENVIRONMENT CONFIG
# =========================================================

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
EVENTBRITE_API_TOKEN = os.getenv("EVENTBRITE_API_TOKEN")

MANGALORE_LAT = 12.9141
MANGALORE_LON = 74.8560
SEARCH_RADIUS_KM = 50


# =========================================================
# MAIN ENTRY POINT
# =========================================================

def fetch_ticketing_events() -> List[Dict]:
    """
    Fetch events only from approved and active sources.
    """

    events: List[Dict] = []

    # ------------------------------
    # Ticketmaster
    # ------------------------------
    if SourceRegistry.validate_source("Ticketmaster"):
        events.extend(fetch_ticketmaster_events())

    # ------------------------------
    # Eventbrite
    # ------------------------------
    if SourceRegistry.validate_source("Eventbrite"):
        events.extend(fetch_eventbrite_events())

    return events


# =========================================================
# TICKETMASTER COLLECTOR
# =========================================================

def fetch_ticketmaster_events() -> List[Dict]:

    if not TICKETMASTER_API_KEY:
        print("⚠ Ticketmaster API key missing.")
        return []

    metadata = SourceRegistry.get_source_metadata("Ticketmaster")
    if not metadata:
        return []

    url = "https://app.ticketmaster.com/discovery/v2/events.json"

    params = {
        "apikey": TICKETMASTER_API_KEY,
        "latlong": f"{MANGALORE_LAT},{MANGALORE_LON}",
        "radius": SEARCH_RADIUS_KM,
        "unit": "km",
        "size": 50,
        "sort": "date,asc"
    }

    try:
        response = requests.get(url, params=params, timeout=10)

        if ENABLE_RATE_LIMITING:
            time.sleep(REQUEST_DELAY_SECONDS)

        if response.status_code != 200:
            print("Ticketmaster API error:", response.status_code)
            return []

        data = response.json()
        raw_events = data.get("_embedded", {}).get("events", [])

        normalized_events = []

        for event in raw_events:
            normalized = normalize_ticketmaster_event(event)
            if normalized:
                normalized_events.append(normalized)

        return normalized_events

    except Exception as e:
        print("Ticketmaster fetch failed:", str(e))
        return []


def normalize_ticketmaster_event(event: Dict) -> Optional[Dict]:

    try:
        event_date = event.get("dates", {}).get("start", {}).get("dateTime")

        if REJECT_EVENTS_WITHOUT_DATE and not event_date:
            return None

        parsed_date = parse_iso_datetime(event_date)

        if REJECT_PAST_EVENTS and parsed_date:
            if parsed_date < datetime.now(timezone.utc):
                return None

        status_code = event.get("dates", {}).get("status", {}).get("code", "active")

        venue = event.get("_embedded", {}).get("venues", [{}])[0].get("name")

        return {
            "id": f"tm_{event.get('id')}",
            "name": event.get("name"),
            "category": "events",
            "type": "ticketed_event",
            "venue": venue,
            "date": event_date,
            "source": "Ticketmaster",
            "source_url": event.get("url"),
            "status": normalize_status(status_code),
        }

    except Exception:
        return None


# =========================================================
# EVENTBRITE COLLECTOR
# =========================================================

def fetch_eventbrite_events() -> List[Dict]:

    if not EVENTBRITE_API_TOKEN:
        print("⚠ Eventbrite API token missing.")
        return []

    metadata = SourceRegistry.get_source_metadata("Eventbrite")
    if not metadata:
        return []

    url = "https://www.eventbriteapi.com/v3/events/search/"

    headers = {
        "Authorization": f"Bearer {EVENTBRITE_API_TOKEN}"
    }

    params = {
        "location.latitude": MANGALORE_LAT,
        "location.longitude": MANGALORE_LON,
        "location.within": f"{SEARCH_RADIUS_KM}km",
        "expand": "venue",
        "sort_by": "date"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)

        if ENABLE_RATE_LIMITING:
            time.sleep(REQUEST_DELAY_SECONDS)

        if response.status_code != 200:
            print("Eventbrite API error:", response.status_code)
            return []

        data = response.json()
        raw_events = data.get("events", [])

        normalized_events = []

        for event in raw_events:
            normalized = normalize_eventbrite_event(event)
            if normalized:
                normalized_events.append(normalized)

        return normalized_events

    except Exception as e:
        print("Eventbrite fetch failed:", str(e))
        return []


def normalize_eventbrite_event(event: Dict) -> Optional[Dict]:

    try:
        event_date = event.get("start", {}).get("utc")

        if REJECT_EVENTS_WITHOUT_DATE and not event_date:
            return None

        parsed_date = parse_iso_datetime(event_date)

        if REJECT_PAST_EVENTS and parsed_date:
            if parsed_date < datetime.now(timezone.utc):
                return None

        status = event.get("status", "live")

        venue = event.get("venue", {}).get("name")

        return {
            "id": f"eb_{event.get('id')}",
            "name": event.get("name", {}).get("text"),
            "category": "events",
            "type": "ticketed_event",
            "venue": venue,
            "date": event_date,
            "source": "Eventbrite",
            "source_url": event.get("url"),
            "status": normalize_status(status),
        }

    except Exception:
        return None


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def parse_iso_datetime(date_string: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(date_string.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_status(status_value: str) -> str:
    """
    Normalize different API status codes.
    """

    if not status_value:
        return "active"

    status_value = status_value.lower()

    if status_value in ["cancelled", "canceled"]:
        return "cancelled"

    if status_value in ["onsale", "live"]:
        return "active"

    return status_value
