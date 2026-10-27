"""
ORM models for the itinerary feedback feature. Shares layer0's `Base` and
database — same reasoning as TouristProfileModel: one Postgres database
for the whole system (blueprint Table 12), not one per layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from layer0.infrastructure.db.session import Base


class ConfirmedItineraryModel(Base):
    __tablename__ = "confirmed_itineraries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)

    items: Mapped[list] = mapped_column(JSON, default=list)  # [{place_id, place_name, role, order_index}, ...]
    original_order: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    removed_place_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    added_place_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    overall_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    place_ratings: Mapped[dict] = mapped_column(JSON, default=dict)  # {place_id: "up"|"down"}
    status: Mapped[str] = mapped_column(String(20), default="draft")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlaceFeedbackSignalModel(Base):
    __tablename__ = "place_feedback_signals"

    place_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    thumbs_up: Mapped[int] = mapped_column(Integer, default=0)
    thumbs_down: Mapped[int] = mapped_column(Integer, default=0)
    times_removed: Mapped[int] = mapped_column(Integer, default=0)
    times_manually_added: Mapped[int] = mapped_column(Integer, default=0)
    times_moved_earlier: Mapped[int] = mapped_column(Integer, default=0)
    times_moved_later: Mapped[int] = mapped_column(Integer, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
