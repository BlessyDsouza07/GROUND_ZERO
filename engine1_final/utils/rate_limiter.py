"""
utils/rate_limiter.py

Respectful API rate limiter.
Ensures Ground Zero never hammers free APIs.

All collectors import sleep_between_calls() after each request.
"""

import time

# Overpass (OSM) — they ask for 1 request/second max
OSM_DELAY = 1.5

# Wikipedia / Wikidata — generous public API, but be respectful
WIKI_DELAY = 0.5

# OpenTripMap free tier — 5000 calls/day → ~0.06/sec → 1 call per second safe
OTM_DELAY = 1.0

# Nominatim (city boundary) — 1 request/second policy
NOMINATIM_DELAY = 1.0

# Generic fallback
DEFAULT_DELAY = 1.0


def sleep_between_calls(seconds: float = DEFAULT_DELAY):
    """Sleep between API calls to respect rate limits."""
    time.sleep(seconds)
