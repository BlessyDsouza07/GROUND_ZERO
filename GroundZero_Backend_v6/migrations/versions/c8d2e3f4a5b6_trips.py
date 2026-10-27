"""Chunk 2: trips, trip_places, trip_journal_entries, trip_events.

Revision ID: c8d2e3f4a5b6
Revises: b7c1d2e3f4a5
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c8d2e3f4a5b6"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("budget_total", sa.Float, nullable=False),
        sa.Column("budget_remaining", sa.Float, nullable=False),
        sa.Column("energy_band", sa.String(length=20), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean, nullable=False),
        sa.Column("voice_guide_enabled", sa.Boolean, nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.String(length=300), nullable=True),
        sa.Column("origin_latitude", sa.Float, nullable=True),
        sa.Column("origin_longitude", sa.Float, nullable=True),
        sa.Column("geofence_radius_km", sa.Float, nullable=True),
        sa.Column("accommodation_place_id", sa.String(length=64), nullable=True),
        sa.Column("accommodation_name", sa.String(length=200), nullable=True),
        sa.Column("layer3_session_id", sa.String(length=64), nullable=True),
        sa.Column("overall_rating", sa.Integer, nullable=True),
        sa.Column("overall_feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trips_user_id", "trips", ["user_id"])

    op.create_table(
        "trip_places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("place_id", sa.String(length=64), nullable=False),
        sa.Column("place_name", sa.String(length=300), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("travel_mode", sa.String(length=20), nullable=True),
        sa.Column("travel_time_minutes", sa.Integer, nullable=True),
        sa.Column("estimated_cost", sa.Float, nullable=False),
        sa.Column("reason_selected", sa.Text, nullable=True),
        sa.Column("is_tourist_added", sa.Boolean, nullable=False),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("halt_minutes", sa.Float, nullable=True),
        sa.Column("amount_spent", sa.Float, nullable=True),
        sa.Column("energy_after", sa.String(length=20), nullable=True),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("experience_note", sa.Text, nullable=True),
        sa.Column("listened_to_guide", sa.Boolean, nullable=True),
    )
    op.create_index("ix_trip_places_trip_id", "trip_places", ["trip_id"])

    op.create_table(
        "trip_journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("trip_place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trip_places.id"), nullable=True),
        sa.Column("media_type", sa.String(length=10), nullable=False),
        sa.Column("media_url", sa.Text, nullable=False),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trip_journal_entries_trip_id", "trip_journal_entries", ["trip_id"])

    op.create_table(
        "trip_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("profile_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trip_events_trip_id", "trip_events", ["trip_id"])
    op.create_index("ix_trip_events_user_id", "trip_events", ["user_id"])
    op.create_index("ix_trip_events_created_at", "trip_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("trip_events")
    op.drop_table("trip_journal_entries")
    op.drop_table("trip_places")
    op.drop_table("trips")
