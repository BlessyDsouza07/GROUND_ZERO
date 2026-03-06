# events/historical_registry.py

"""
Ground Zero – Historical Cultural Registry
-------------------------------------------

Purpose:
Registry of officially recognized recurring cultural events.

This module DOES NOT:
- Generate events
- Store descriptions
- Create schedules
- Fabricate metadata

This module ONLY:
- Registers verified recurring cultural references
- Links to official authority sources
- Enables recurrence validation inside Engine 3
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime


# ============================================================
# DATA MODEL
# ============================================================

@dataclass(frozen=True)
class HistoricalEvent:

    name: str
    category: str  # festival | sports | religious | cultural | traditional
    official_authority: str
    official_url: str
    recurrence_type: str  # annual | seasonal | monthly | variable
    city: str
    country: str
    verified: bool
    last_verified: str
    notes: Optional[str] = None  # For internal reference only


# ============================================================
# REGISTRY
# ============================================================

HISTORICAL_EVENTS: List[HistoricalEvent] = [

    HistoricalEvent(
        name="Mangalore Dasara",
        category="festival",
        official_authority="Sri Gokarnanatheshwara Temple Trust",
        official_url="https://kudroli.org",
        recurrence_type="annual",
        city="Mangalore",
        country="India",
        verified=True,
        last_verified="2026-02-16"
    ),

    HistoricalEvent(
        name="Kambala",
        category="traditional",
        official_authority="Karnataka Kambala Association",
        official_url="https://kambala.in",
        recurrence_type="seasonal",
        city="Mangalore",
        country="India",
        verified=True,
        last_verified="2026-02-16"
    ),

    HistoricalEvent(
        name="Karavali Utsav",
        category="cultural",
        official_authority="Dakshina Kannada District Administration",
        official_url="https://dakshinakannada.nic.in",
        recurrence_type="annual",
        city="Mangalore",
        country="India",
        verified=True,
        last_verified="2026-02-16"
    )
]


# ============================================================
# REGISTRY UTILITIES
# ============================================================

def get_all_historical_events(city: Optional[str] = None) -> List[HistoricalEvent]:
    """
    Returns historical events.
    Optionally filter by city.
    """

    if city:
        return [
            event for event in HISTORICAL_EVENTS
            if event.city.lower() == city.lower()
        ]

    return HISTORICAL_EVENTS


def get_verified_events() -> List[HistoricalEvent]:
    """
    Returns only verified entries.
    """

    return [
        event for event in HISTORICAL_EVENTS
        if event.verified
    ]


def registry_snapshot() -> List[Dict]:
    """
    Returns serializable version for:
    - Transparency reporting
    - Bias audits
    - Public documentation
    """

    return [asdict(event) for event in HISTORICAL_EVENTS]


def validate_registry() -> bool:
    """
    Ensures:
    - No duplicate names
    - Valid URLs
    - Recurrence type valid
    """

    valid_recurrence = {"annual", "seasonal", "monthly", "variable"}

    seen = set()

    for event in HISTORICAL_EVENTS:

        if event.name in seen:
            raise ValueError(f"Duplicate historical event: {event.name}")
        seen.add(event.name)

        if not event.official_url.startswith("http"):
            raise ValueError(f"Invalid URL for {event.name}")

        if event.recurrence_type not in valid_recurrence:
            raise ValueError(
                f"Invalid recurrence type for {event.name}"
            )

    return True


# ============================================================
# SAFE EXECUTION TEST
# ============================================================

if __name__ == "__main__":

    print("Validating Historical Registry...")
    validate_registry()
    print("Registry valid.")
    print(f"Total entries: {len(HISTORICAL_EVENTS)}")
