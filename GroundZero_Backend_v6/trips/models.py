"""SQLAlchemy models for the New Trip flow.

Deliberately NOT reinventing what already exists elsewhere in this
backend:
  - the 9-question survey logic lives in layer1 (SurveyService) — this
    module only drives it in the exact question order Carol asked for
    and auto-fills the questions she chose not to ask (see service.py).
  - itinerary generation is layer2's HiveEngine, unchanged.
  - live-trip mechanics (geofence arrival, silence filter, wallet,
    pause/resume, SOS, ask engine) already exist in layer3, mounted at
    `/l3`. This module does not duplicate that state machine — a Trip
    row here just remembers which layer3 session_id belongs to which
    of OUR trips/users, plus the handful of things layer3 doesn't track
    (journal media, per-trip notification/voice toggles, exit reason,
    community "add my own place" bookkeeping) so the Flutter app has one
    coherent place to read/write from.

Trip.id is a plain uuid string (not a FK-constrained relationship to
auth.models.User at the DB level via ORM relationship, just a column) —
kept intentionally simple; the auth check happens in routes.py by
comparing trip.user_id to the authenticated user's id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from layer0.infrastructure.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Layer 1 TouristProfile.id (string uuid) — the survey answers this
    # trip was generated from.
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # draft -> the itinerary was generated and can still be edited
    #          (add/remove/reorder/rate) but hasn't been confirmed.
    # scheduled -> confirmed, but the tourist chose "start later".
    # active / paused / completed / ended_early -> mirrors layer3's
    #          session status once one exists (see service.py.sync_status).
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    budget_total: Mapped[float] = mapped_column(Float, nullable=False)
    budget_remaining: Mapped[float] = mapped_column(Float, nullable=False)
    energy_band: Mapped[str] = mapped_column(String(20), nullable=False, default="moderate")

    notifications_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    voice_guide_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    origin_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    accommodation_place_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accommodation_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # The layer3 orchestrator's own session_id, once /confirm calls
    # session_start. None while status == "draft".
    layer3_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    overall_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    places: Mapped[list["TripPlace"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripPlace.order_index"
    )
    journal_entries: Mapped[list["JournalEntry"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class TripPlace(Base):
    __tablename__ = "trip_places"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False, index=True)

    place_id: Mapped[str] = mapped_column(String(64), nullable=False)
    place_name: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # pending -> visited -> (checked out); or skipped / removed.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    travel_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    travel_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason_selected: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_tourist_added: Mapped[bool] = mapped_column(default=False, nullable=False)

    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    halt_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    amount_spent: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_after: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    listened_to_guide: Mapped[bool | None] = mapped_column(nullable=True)

    trip: Mapped[Trip] = relationship(back_populates="places")


class JournalEntry(Base):
    __tablename__ = "trip_journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False, index=True)
    trip_place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trip_places.id"), nullable=True)

    media_type: Mapped[str] = mapped_column(String(10), nullable=False)  # photo | video
    media_url: Mapped[str] = mapped_column(Text, nullable=False)  # wherever it was uploaded to
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    trip: Mapped[Trip] = relationship(back_populates="journal_entries")


class TripEvent(Base):
    """The honest behavioral log: every choice the tourist makes, before
    and after confirming, recorded so it can eventually improve
    personalization and the recommendation model. Nothing downstream
    consumes this yet (there is no training pipeline in this repo) — it
    is stored as structured fact, not claimed as "used to train
    anything" it isn't. See trips/README_TRIPS.md."""

    __tablename__ = "trip_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
