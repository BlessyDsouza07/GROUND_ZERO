"""
ORM models for Layer 0. Real PostGIS geography column (via GeoAlchemy2) so
the 300m-proximity work in Layer 3 (out of current scope, but the schema
should already support it — blueprint 6, Table 12) uses native
`ST_DWithin` instead of application-side haversine loops.

Normalization notes:
  - `places` is the Master Data Core.
  - `bias_signals` is a 1:1 child table (not columns on `places`) so the
    raw inputs to the Bias Audit stay separately versionable/auditable
    from the derived `bias_index`.
  - `community_submissions` references `places` only after approval; the
    submitted (unapproved) Place data lives inline as JSON until then, so
    unapproved submissions never pollute the `places` table or its
    indexes.
  - Enum-like fields use Postgres ENUM types via SQLAlchemy Enum, not free
    text, so bad category/price_band data can't be inserted at the DB
    layer even if application validation is bypassed.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from layer0.infrastructure.db.session import Base


class PriceBandEnum(str, enum.Enum):
    free = "free"
    budget = "budget"
    moderate = "moderate"
    premium = "premium"


class CrowdLevelEnum(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    variable = "variable"


class EnergyRequirementEnum(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"


class GradeEnum(str, enum.Enum):
    authentic = "authentic"
    balanced = "balanced"
    commercialised = "commercialised"


class SubmissionStatusEnum(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class PlaceModel(Base):
    __tablename__ = "places"
    # eager_defaults: without this, any UPDATE (i.e. re-upserting a place
    # that already exists — which happens on every second ETL run, every
    # re-scoring pass) crashes with sqlalchemy.exc.MissingGreenlet the
    # moment repository_impl._model_to_place() reads model.updated_at.
    # Reason: updated_at has a server-side `onupdate=func.now()`, so after
    # flush SQLAlchemy marks it "expired" and needs a synchronous DB round
    # trip to refresh it — which can't happen inside an async session
    # without an event loop to await it. eager_defaults=True makes
    # SQLAlchemy fetch server-generated values via RETURNING as part of
    # the same flush, so no follow-up round trip (and no crash) is needed.
    # Confirmed via a live reproduction against real PostgreSQL: upserting
    # a brand-new place worked; re-upserting that same place crashed with
    # this exact error until this flag was added.
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("estimated_cost >= 0", name="ck_places_cost_non_negative"),
        CheckConstraint(
            "bias_index IS NULL OR (bias_index >= 0 AND bias_index <= 1)",
            name="ck_places_bias_index_range",
        ),
        CheckConstraint(
            "freshness_score >= 0 AND freshness_score <= 1",
            name="ck_places_freshness_range",
        ),
        CheckConstraint(
            "verification_status IN ('verified', 'pending')",
            name="ck_places_verification_status",
        ),
        UniqueConstraint("name", "category", "location", name="uq_places_name_category_location"),
        Index("ix_places_location", "location", postgresql_using="gist"),
        Index("ix_places_category", "category"),
        Index("ix_places_temporarily_unavailable", "temporarily_unavailable"),
        Index("ix_places_verification_status", "verification_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)

    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )

    opening_hours_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    days_open: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    opens_at: Mapped[str | None] = mapped_column(String(5), nullable=True)
    closes_at: Mapped[str | None] = mapped_column(String(5), nullable=True)

    price_band: Mapped[PriceBandEnum] = mapped_column(Enum(PriceBandEnum, name="price_band_enum"), nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    bias_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[GradeEnum | None] = mapped_column(Enum(GradeEnum, name="grade_enum"), nullable=True)

    energy_requirement: Mapped[EnergyRequirementEnum] = mapped_column(
        Enum(EnergyRequirementEnum, name="energy_requirement_enum"),
        default=EnergyRequirementEnum.moderate,
    )
    crowd_level: Mapped[CrowdLevelEnum] = mapped_column(
        Enum(CrowdLevelEnum, name="crowd_level_enum"), default=CrowdLevelEnum.moderate
    )
    season_suitability: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    tide_dependency: Mapped[bool] = mapped_column(Boolean, default=False)
    dwell_time_typical_minutes: Mapped[int] = mapped_column(Integer, default=45)

    accessibility_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    wheelchair: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stairs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sensory_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    parking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    washrooms: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    food_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pet_friendly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    family_friendly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kid_friendly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    photography_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    best_time: Mapped[str | None] = mapped_column(String(50), nullable=True)

    freshness_score: Mapped[float] = mapped_column(Float, default=0.0)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    temporarily_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)

    etiquette_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wiki_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport_access: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SECURITY FIX (final-release-hardening pass, Oct 2026): see
    # migrations/versions/f3a4b5c6d7e8_place_verification_status.py and
    # layer0/domain/entities.py::Place.verification_status.
    verification_status: Mapped[str] = mapped_column(String(20), default="verified", server_default="verified")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bias_signals: Mapped["BiasSignalsModel"] = relationship(
        back_populates="place", uselist=False, cascade="all, delete-orphan"
    )


class BiasSignalsModel(Base):
    """Raw bias-audit inputs, versioned separately from the derived
    bias_index stored on PlaceModel — see module docstring."""
    __tablename__ = "bias_signals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    media_mentions: Mapped[int] = mapped_column(Integer, default=0)
    local_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    commercial_flags: Mapped[int] = mapped_column(Integer, default=0)
    tourist_popularity: Mapped[float] = mapped_column(Float, default=0.0)
    sponsored_indicator: Mapped[bool] = mapped_column(Boolean, default=False)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    place: Mapped["PlaceModel"] = relationship(back_populates="bias_signals")


class CommunitySubmissionModel(Base):
    __tablename__ = "community_submissions"

    id: Mapped[uuid.UUID] = _uuid_pk()

    # Submitted place data lives as JSON until approved — never written into
    # `places` (and never indexed/searchable there) until an admin approves it.
    submitted_place_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    submitter_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[SubmissionStatusEnum] = mapped_column(
        Enum(SubmissionStatusEnum, name="submission_status_enum"), default=SubmissionStatusEnum.pending
    )
    resulting_place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id", ondelete="SET NULL"), nullable=True
    )

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SECURITY FIX (final-release-hardening pass, Oct 2026): see
    # layer0/domain/entities.py::CommunitySubmission.submitter_user_id.
    # No FK to `users` on purpose — this table is also used by layer0's
    # standalone deployment, which has no `users` table at all.
    submitter_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
