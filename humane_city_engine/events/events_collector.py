# events/events_collector.py

"""
Ground Zero – Unified Events Orchestrator
------------------------------------------

Combines:
- GovernmentEventCollector
- RSSCollector
- TicketingCollector

STRICT RULES:
- No content modification
- No synthetic enrichment
- No ranking
- No filtering
- Only aggregation + deduplication
- Deterministic behavior

Feeds:
Engine 1 → Structured Data Hub
Engine 3 → Bias & Authenticity
Database → Persistent storage
"""

import logging
from typing import List, Dict, Set
from hashlib import sha256

from events.source_registry import get_all_sources
from events.government_collector import GovernmentEventCollector
from events.rss_collector import RSSCollector
from events.ticketing_collector import (
    EventbriteCollector,
    TicketmasterCollector,
    MeetupCollector
)


LOGGER = logging.getLogger("EventsCollector")


# ============================================================
# DEDUPLICATION
# ============================================================

def generate_event_signature(event: Dict) -> str:
    """
    Generates deterministic hash signature
    based on name + start_date + website.
    """

    raw = f"{event.get('name','')}-{event.get('start_date','')}-{event.get('website','')}"
    return sha256(raw.encode("utf-8")).hexdigest()


def deduplicate_events(events: List[Dict]) -> List[Dict]:
    """
    Removes duplicate events using deterministic hashing.
    """

    seen: Set[str] = set()
    unique_events: List[Dict] = []

    for event in events:
        signature = generate_event_signature(event)

        if signature not in seen:
            seen.add(signature)
            event["event_signature"] = signature
            unique_events.append(event)

    return unique_events


# ============================================================
# MAIN ORCHESTRATOR
# ============================================================

class EventsCollector:

    def __init__(self, config: Dict):
        """
        config example:

        {
            "city": "Mangalore",
            "latitude": 12.9141,
            "longitude": 74.8560,
            "eventbrite_token": "...",
            "ticketmaster_key": "...",
            "meetup_key": "...",
            "gov_rss_feeds": [
                {"name": "...", "url": "..."}
            ],
            "tourism_rss_feeds": [
                {"name": "...", "url": "..."}
            ]
        }
        """

        self.config = config

    # --------------------------------------------------------
    # COLLECT FROM ALL SOURCES
    # --------------------------------------------------------

    def collect_all(self) -> List[Dict]:

        all_events: List[Dict] = []

        LOGGER.info("Starting unified event collection")

        # ----------------------------------------------------
        # GOVERNMENT RSS
        # ----------------------------------------------------

        for feed in self.config.get("gov_rss_feeds", []):
            collector = GovernmentEventCollector(
                source_name=feed["name"],
                rss_url=feed["url"]
            )
            all_events.extend(collector.fetch_events())

        # ----------------------------------------------------
        # TOURISM / CULTURAL RSS
        # ----------------------------------------------------

        for feed in self.config.get("tourism_rss_feeds", []):
            collector = RSSCollector(
                source_name=feed["name"],
                feed_url=feed["url"]
            )
            all_events.extend(collector.fetch_events())

        # ----------------------------------------------------
        # EVENTBRITE
        # ----------------------------------------------------

        if self.config.get("eventbrite_token"):
            eb = EventbriteCollector(
                token=self.config["eventbrite_token"]
            )
            all_events.extend(
                eb.fetch_events(
                    latitude=self.config["latitude"],
                    longitude=self.config["longitude"]
                )
            )

        # ----------------------------------------------------
        # TICKETMASTER
        # ----------------------------------------------------

        if self.config.get("ticketmaster_key"):
            tm = TicketmasterCollector(
                api_key=self.config["ticketmaster_key"]
            )
            all_events.extend(
                tm.fetch_events(
                    latitude=self.config["latitude"],
                    longitude=self.config["longitude"]
                )
            )

        # ----------------------------------------------------
        # MEETUP (OPTIONAL)
        # ----------------------------------------------------

        if self.config.get("meetup_key"):
            mu = MeetupCollector(
                api_key=self.config["meetup_key"]
            )
            all_events.extend(
                mu.fetch_events(
                    latitude=self.config["latitude"],
                    longitude=self.config["longitude"]
                )
            )

        LOGGER.info(f"Collected total {len(all_events)} raw events")

        # ----------------------------------------------------
        # DEDUPLICATE
        # ----------------------------------------------------

        unique_events = deduplicate_events(all_events)

        LOGGER.info(f"{len(unique_events)} unique events after deduplication")

        return unique_events


# ============================================================
# SAFE EXECUTION TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    config = {
        "city": "Mangalore",
        "latitude": 12.9141,
        "longitude": 74.8560,
        "eventbrite_token": None,
        "ticketmaster_key": None,
        "meetup_key": None,
        "gov_rss_feeds": [],
        "tourism_rss_feeds": []
    }

    collector = EventsCollector(config)
    events = collector.collect_all()

    print(f"Final unique events: {len(events)}")
