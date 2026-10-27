"""itinerary feedback + place feedback signals

Revision ID: a1b2c3d4e5f6
Revises: 7796b31154e4
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = '1547c464d7fe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confirmed_itineraries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("original_order", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("removed_place_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("added_place_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("overall_rating", sa.Integer(), nullable=True),
        sa.Column("place_ratings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_confirmed_itineraries_profile_id", "confirmed_itineraries", ["profile_id"])

    op.create_table(
        "place_feedback_signals",
        sa.Column("place_id", sa.String(length=36), primary_key=True),
        sa.Column("thumbs_up", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thumbs_down", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_manually_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_moved_earlier", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_moved_later", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("place_feedback_signals")
    op.drop_index("ix_confirmed_itineraries_profile_id", table_name="confirmed_itineraries")
    op.drop_table("confirmed_itineraries")
