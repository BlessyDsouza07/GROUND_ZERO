"""HIVE 2 (traveller memory, geofence state) and privacy (consents, content reports).

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-10-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def _uid() -> sa.Column:
    return sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "hive_traveller_profiles",
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("affinities", sa.JSON, nullable=False),
        sa.Column("constraints", sa.JSON, nullable=False),
        sa.Column("visited_place_ids", sa.JSON, nullable=False),
        sa.Column("dismissed_place_ids", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "hive_traveller_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        _uid(),
        sa.Column("place_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(32)),
        sa.Column("rating", sa.Integer),
        sa.Column("context", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hive_events_user", "hive_traveller_events", ["user_id"])
    op.create_index("ix_hive_events_place", "hive_traveller_events", ["place_id"])
    op.create_index("ix_hive_events_created", "hive_traveller_events", ["created_at"])
    op.create_table(
        "hive_geofence_state",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        _uid(),
        sa.Column("place_id", sa.String(64), nullable=False),
        sa.Column("inside", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("entered_at", sa.DateTime(timezone=True)),
        sa.Column("last_notified_at", sa.DateTime(timezone=True)),
        sa.Column("notify_count", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "place_id", name="uq_geofence_user_place"),
    )
    op.create_index("ix_hive_geofence_user", "hive_geofence_state", ["user_id"])
    op.create_table(
        "privacy_consents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        _uid(),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("policy_version", sa.String(16), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "kind", name="uq_consent_user_kind"),
    )
    op.create_index("ix_consent_user", "privacy_consents", ["user_id"])
    op.create_table(
        "content_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        _uid(),
        sa.Column("target_kind", sa.String(24), nullable=False),
        sa.Column("target_ref", sa.String(300), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_user", "content_reports", ["user_id"])


def downgrade() -> None:
    for t in ("content_reports", "privacy_consents", "hive_geofence_state", "hive_traveller_events", "hive_traveller_profiles"):
        op.drop_table(t)
