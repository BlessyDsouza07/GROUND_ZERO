"""
Domain model for the tourist-editable itinerary: after HIVE produces a
RecommendationQueue, the tourist can reorder it, drop places they don't
want, add places of their own choice, rate it, and confirm before actually
setting out. This is deliberately a SEPARATE persisted entity from
RecommendationQueue (which stays the ephemeral, regenerable HIVE output) —
ConfirmedItinerary is the tourist's edited, saved version of it.

original_order is captured once, on the first save, and never overwritten
on subsequent saves — it's the baseline PlaceFeedbackSignal deltas are
computed against (see feedback_service.py), so "moved 3 slots earlier"
means something stable across however many times the tourist fiddles with
the order before confirming.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ItineraryStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


@dataclass
class ItineraryItem:
    place_id: str
    place_name: str
    role: str
    order_index: int


@dataclass
class ConfirmedItinerary:
    profile_id: str
    items: list[ItineraryItem] = field(default_factory=list)
    original_order: list[str] = field(default_factory=list)  # place_ids, captured once on first save
    removed_place_ids: list[str] = field(default_factory=list)
    added_place_ids: list[str] = field(default_factory=list)  # tourist-added, beyond HIVE's original queue
    overall_rating: Optional[int] = None  # 1-5
    place_ratings: dict[str, str] = field(default_factory=dict)  # place_id -> "up" | "down"
    status: ItineraryStatus = ItineraryStatus.DRAFT
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None


@dataclass
class PlaceFeedbackSignal:
    """Aggregate, per-place counters fed by every tourist's edits across
    every trip — this is the real, bounded mechanism that closes the loop
    back into the dataset (see bias_signal_estimator.refine_with_community_feedback
    and scripts/apply_community_feedback.py), not a vague "AI learns"
    claim: specific counters, specific formula, specific script that
    applies them."""
    place_id: str
    thumbs_up: int = 0
    thumbs_down: int = 0
    times_removed: int = 0
    times_manually_added: int = 0
    times_moved_earlier: int = 0  # promoted up the order vs. original_order
    times_moved_later: int = 0
    last_updated_at: Optional[datetime] = None
