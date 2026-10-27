"""
Domain entities for Layer 2 — HIVE Recommendation Engine.

Slot role counts per blueprint Table 5. NOTE: Table 5's per-role half-day
counts (Grounding 1 + Signature 1 + Anchor 1 + Personal 4 + Local Secret 1
= 8) do not match Table 11 step 8's "7 slots for half-day" summary. This
implementation follows Table 5 (the authoritative per-role breakdown) —
flagged here and in the delivery notes for the blueprint owner to reconcile.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SlotRole(str, Enum):
    GROUNDING = "grounding"
    SIGNATURE = "signature"
    ANCHOR = "anchor"
    PERSONAL = "personal"
    LOCAL_SECRET = "local_secret"
    WILDCARD = "wildcard"  # counted within Personal per Table 5, tracked distinctly here for transparency
    TOURIST_PICK = "tourist_pick"  # a place the tourist added themselves — see hive_engine.pinned_place_ids


class TransportMode(str, Enum):
    WALK = "walk"
    AUTO = "auto"
    CAB = "cab"


# Table 5: (grounding, signature, anchor, personal_incl_wildcard, local_secret, wildcard_within_personal)
SLOT_COUNTS_FULL_DAY = {
    SlotRole.GROUNDING: 1, SlotRole.SIGNATURE: 1, SlotRole.ANCHOR: 1,
    SlotRole.PERSONAL: 9, SlotRole.LOCAL_SECRET: 1,
}
WILDCARD_COUNT_FULL_DAY = 1  # within the 9 Personal slots

SLOT_COUNTS_HALF_DAY = {
    SlotRole.GROUNDING: 1, SlotRole.SIGNATURE: 1, SlotRole.ANCHOR: 1,
    SlotRole.PERSONAL: 4, SlotRole.LOCAL_SECRET: 1,
}
WILDCARD_COUNT_HALF_DAY = 0


@dataclass
class ScoredPlace:
    """A candidate place after Personal Fit Score has been computed —
    the unit Slot Assembly operates on."""
    place_id: str
    name: str
    category: str
    raw_score: float
    bias_index: float
    personal_fit: float
    breakdown: dict[str, float] = field(default_factory=dict)  # component scores for explainability
    is_local_secret_eligible: bool = False
    # Ranking v2 tie-break score (see layer2/application/ranking.py). None =
    # legacy behaviour: sort by personal_fit alone.
    rank_score: float | None = None


@dataclass
class TransportEstimate:
    mode: TransportMode
    duration_minutes: int
    cost_inr: float
    is_routed: bool = False  # True when a real OSRM road route was used, not a haversine estimate


@dataclass
class RecommendationSlotItem:
    """One row of the Recommendation Queue (blueprint 5.6 OUTPUT section)."""
    place_id: str
    place_name: str
    role: SlotRole
    scheduled_time: datetime
    travel_mode: TransportMode
    travel_time_minutes: int
    estimated_cost: float
    reason_selected: str
    personal_score: float
    weather_adjusted: bool = False
    weather_adjustment_note: Optional[str] = None
    travel_is_routed: bool = False  # True when travel_time/mode came from a real OSRM route, not haversine


@dataclass
class RecommendationQueue:
    profile_id: str
    items: list[RecommendationSlotItem] = field(default_factory=list)
    total_estimated_cost: float = 0.0
    generated_at: Optional[datetime] = None
    geofence_radius_km: Optional[float] = None  # None when no tourist location was given, OR the geofence found nothing at any radius and was bypassed (see reachability.py)
    slots_requested: Optional[int] = None  # target count per blueprint's 5-role table for this trip_duration
    slots_filled: Optional[int] = None  # actual non-TOURIST_PICK slots in the final queue
    slots_dropped_closed: int = 0  # slots removed because the candidate was closed at its own scheduled time
