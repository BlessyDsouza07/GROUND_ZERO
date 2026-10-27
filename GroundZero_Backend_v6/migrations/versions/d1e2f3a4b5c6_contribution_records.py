"""Chunk 4: contribution_records (links a user to a layer0 community submission).

Revision ID: d1e2f3a4b5c6
Revises: c8d2e3f4a5b6
Create Date: 2026-10-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1e2f3a4b5c6"
down_revision = "c8d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contribution_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contribution_records_user_id", "contribution_records", ["user_id"])
    op.create_index("ix_contribution_records_submission_id", "contribution_records", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_contribution_records_submission_id", table_name="contribution_records")
    op.drop_index("ix_contribution_records_user_id", table_name="contribution_records")
    op.drop_table("contribution_records")
