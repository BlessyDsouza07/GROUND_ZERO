"""FEATURE (final-release-hardening pass, Oct 2026): saved_places — a
persistent bookmark a tourist can put on any place, independent of any
trip. This feature didn't exist at all before this pass; see
personal/models.py::SavedPlace for the full reasoning.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("place_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "place_id", name="uq_saved_places_user_place"),
    )
    op.create_index("ix_saved_places_user_id", "saved_places", ["user_id"])
    op.create_index("ix_saved_places_place_id", "saved_places", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_places_place_id", table_name="saved_places")
    op.drop_index("ix_saved_places_user_id", table_name="saved_places")
    op.drop_table("saved_places")
