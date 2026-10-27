"""HIVE 2 persistence: the traveller's own memory, their consent choices,
and the minimum geofence state needed to avoid repeat alerts.

Privacy by design:
  * The profile only stores what the traveller said or did, each with its
    source and confidence, and can be viewed, edited, exported and deleted.
  * Raw location is NEVER stored. GeofenceState keeps only
    "inside / last notified" per place.
  * Everything cascades when the user account is deleted.
Generic SQLAlchemy types are used so the same models run on PostgreSQL and
in the SQLite-based tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from layer0.infrastructure.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TravellerProfile(Base):
    __tablename__ = "hive_traveller_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # {"local_food": {"weight": 0.9, "source": "explicit", "confidence": 1.0, "updated": "..."}}
    affinities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {"dietary": ["veg"], "accessibility": ["limited_walking"], "max_spend_per_place": 800,
    #  "companions": "family", "kids": true, "avoid": ["crowds"], "excluded_categories": [...]}
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    visited_place_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dismissed_place_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class TravellerEvent(Base):
    """Voluntary feedback signals. An 'impression' is logged but never treated as a like."""

    __tablename__ = "hive_traveller_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    place_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # shown|opened|saved|dismissed|navigated|visited|rated
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)  # dismissed: not_interested|closed|no_time|too_far|seen_it|other
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # hour, mode, rank (no coordinates)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class GeofenceState(Base):
    __tablename__ = "hive_geofence_state"
    __table_args__ = (UniqueConstraint("user_id", "place_id", name="uq_geofence_user_place"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    place_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inside: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notify_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ConsentRecord(Base):
    """One row per consent kind per user. Withdrawal is recorded, not erased,
    so there is proof of what the person agreed to and when."""

    __tablename__ = "privacy_consents"
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_consent_user_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # terms|adult|location|personalization|photos
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentReport(Base):
    """"Report this" for community photos/places/tips — needed for safe user-generated content."""

    __tablename__ = "content_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_kind: Mapped[str] = mapped_column(String(24), nullable=False)  # photo|place|tip|story
    target_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)  # privacy|unsafe|inaccurate|inappropriate|other
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
