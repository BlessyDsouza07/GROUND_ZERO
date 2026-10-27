"""Chunk 4 follow-up (security/completeness audit, Oct 2026):
contribution_records grows status/place_id/metadata_json/reviewed_at,
and submission_id becomes nullable, so all five contribution actions
(add_place, suggest_update, local_tip, report_incorrect, add_media)
can be logged in one table instead of only add_place.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("contribution_records", "submission_id", nullable=True)
    op.add_column(
        "contribution_records",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column("contribution_records", sa.Column("place_id", sa.String(length=64), nullable=True))
    op.add_column("contribution_records", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.add_column("contribution_records", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_contribution_records_place_id", "contribution_records", ["place_id"])
    op.alter_column("contribution_records", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_contribution_records_place_id", table_name="contribution_records")
    op.drop_column("contribution_records", "reviewed_at")
    op.drop_column("contribution_records", "metadata_json")
    op.drop_column("contribution_records", "place_id")
    op.drop_column("contribution_records", "status")
    op.alter_column("contribution_records", "submission_id", nullable=False)
