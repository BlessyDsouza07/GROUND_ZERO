"""
ORM model for TouristProfile. Deliberately shares layer0's `Base` and
database — the blueprint's tech-stack table (Table 12) specifies one
Postgres database for the whole system, with Session table alongside
Place and TouristProfile, not three separate databases per layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from layer0.infrastructure.db.session import Base


class TouristProfileModel(Base):
    __tablename__ = "tourist_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    energy_band: Mapped[str] = mapped_column(String(20), nullable=False)
    crowd_tolerance: Mapped[str] = mapped_column(String(30), nullable=False)
    budget: Mapped[float] = mapped_column(Float, nullable=False)

    dietary_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    group_config: Mapped[str] = mapped_column(String(20), default="solo")
    group_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    curiosity_text: Mapped[str] = mapped_column(String, default="")
    curiosity_vector: Mapped[dict] = mapped_column(JSON, default=dict)

    trip_duration_hours: Mapped[str] = mapped_column(String(20), default="full_day")
    multi_day_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time_preference: Mapped[str] = mapped_column(String(20), default="flexible")

    accessibility_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    companion_language: Mapped[str] = mapped_column(String(20), default="english")
    voice_personality: Mapped[str] = mapped_column(String(30), default="warm_local_friend")

    return_visitor_exclusions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    visited_log: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # SECURITY FIX (final-release-hardening pass, Oct 2026): see
    # layer1/domain/entities.py::TouristProfile.user_id and
    # migrations/versions/a4b5c6d7e8f9_tourist_profile_ownership.py.
    # No FK constraint to `users` on purpose — this table is also used by
    # layer1's standalone deployment, which has no `users` table at all;
    # a plain nullable UUID column avoids coupling the two.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
