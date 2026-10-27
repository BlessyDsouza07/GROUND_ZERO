from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Survey — Carol's exact 9-question order. See service.py for how each of
# these maps onto layer1's real SurveyStep machine.
# ---------------------------------------------------------------------------
class SurveyStartOut(BaseModel):
    session_id: str
    next_step: str  # "opening_prompt" — always the first thing asked


class SurveyAnswerIn(BaseModel):
    # The step this answer is FOR, so a stale/duplicate submit can't land
    # on the wrong question if two requests race.
    step: str
    value: Any


class SurveyStateOut(BaseModel):
    session_id: str
    next_step: Optional[str]  # None once complete
    progress_fraction: float
    done: bool


class SurveyFinalizeOut(BaseModel):
    profile_id: str


# ---------------------------------------------------------------------------
# Itinerary generation + editing
# ---------------------------------------------------------------------------
class GenerateItineraryIn(BaseModel):
    profile_id: str
    start_latitude: float = Field(ge=-90, le=90)
    start_longitude: float = Field(ge=-180, le=180)
    start_time: Optional[datetime] = None
    pinned_place_ids: list[str] = Field(default_factory=list)


class ItineraryItemOut(BaseModel):
    trip_place_id: str
    place_id: str
    place_name: str
    role: str
    order_index: int
    scheduled_time: Optional[datetime]
    travel_mode: Optional[str]
    travel_time_minutes: Optional[int]
    estimated_cost: float
    reason_selected: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    is_tourist_added: bool
    status: str


class TripOut(BaseModel):
    trip_id: str
    status: str
    profile_id: str
    budget_total: float
    budget_remaining: float
    energy_band: str
    notifications_enabled: bool
    voice_guide_enabled: bool
    geofence_radius_km: Optional[float]
    origin_latitude: Optional[float]
    origin_longitude: Optional[float]
    scheduled_start_at: Optional[datetime]
    started_at: Optional[datetime]
    layer3_session_id: Optional[str]
    places: list[ItineraryItemOut]


class AddPlaceIn(BaseModel):
    # Either an existing place id (from typeahead search) ...
    place_id: Optional[str] = None
    # ... or a brand-new tourist-described place (see CustomPlaceIn).
    name: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    category: Optional[str] = None
    note: Optional[str] = None
    estimated_cost: float = Field(default=0.0, ge=0)


class SearchPlaceOut(BaseModel):
    place_id: str
    name: str
    category: str
    latitude: float
    longitude: float
    estimated_cost: float


class ReorderIn(BaseModel):
    trip_place_ids: list[str]  # the full ordered list of trip_place ids


class RateTripIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: Optional[str] = None


class ConfirmTripIn(BaseModel):
    notifications_enabled: bool = True
    voice_guide_enabled: bool = True
    start_now: bool = True
    scheduled_start_at: Optional[datetime] = None
    accommodation_place_id: Optional[str] = None
    accommodation_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Live trip
# ---------------------------------------------------------------------------
class ArriveIn(BaseModel):
    trip_place_id: str
    listened_to_guide: Optional[bool] = None


class CheckoutIn(BaseModel):
    trip_place_id: str
    # ge=0: a negative amount_spent would silently *increase*
    # budget_remaining in service.py (budget_remaining -= amount_spent).
    # Fixed per security/correctness audit, Oct 2026.
    amount_spent: float = Field(default=0.0, ge=0)
    energy_after: Literal["low", "moderate", "high"]
    rating: int = Field(ge=1, le=5)
    experience_note: Optional[str] = None


class SkipIn(BaseModel):
    trip_place_id: str
    reason: Optional[str] = None


class ExitTripIn(BaseModel):
    reason: str


class ResumeDecisionIn(BaseModel):
    upgrade: bool  # True = regenerate against current budget/energy/geofence; False = stick with the original list
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class TopUpBudgetIn(BaseModel):
    additional_amount: float = Field(gt=0)


class JournalEntryIn(BaseModel):
    trip_place_id: Optional[str] = None
    media_type: Literal["photo", "video"]
    media_url: str
    caption: Optional[str] = None


class JournalEntryOut(BaseModel):
    id: str
    trip_place_id: Optional[str]
    media_type: str
    media_url: str
    caption: Optional[str]
    created_at: datetime


class JournalTimelineOut(BaseModel):
    trip_id: str
    entries: list[JournalEntryOut]
    places_visited: list[str]


# ---------------------------------------------------------------------------
# Chunk 4 — My Trips / Journey Story. Nothing here is fabricated: every
# field is computed from Trip/TripPlace/JournalEntry rows that already
# exist, never invented text.
# ---------------------------------------------------------------------------
class TripSummaryOut(BaseModel):
    trip_id: str
    status: str
    place_count: int
    visited_count: int
    next_place_name: Optional[str]  # the next not-yet-visited place, for the "biggest card" UI
    next_place_id: Optional[str]
    cover_place_name: Optional[str]  # for a completed trip's "journey cover"
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    scheduled_start_at: Optional[datetime]
    overall_rating: Optional[int]
    budget_total: float
    budget_remaining: float


class MyTripsOut(BaseModel):
    upcoming: list[TripSummaryOut]  # draft / scheduled / active / paused
    completed: list[TripSummaryOut]  # completed / ended_early


class TripStoryOut(BaseModel):
    trip_id: str
    title: str  # derived, e.g. "3 places in Mangaluru" — no invented narrative
    place_count: int
    visited_place_names: list[str]
    distance_km: float  # haversine sum between consecutive visited stops — real, computed
    duration_minutes: Optional[int]  # ended_at - started_at
    photo_count: int
    video_count: int
    highlights: list[str]  # place names with rating >= 4 — "what stayed with you"
    cover_place_name: Optional[str]
