"""SECURITY FIX (final-release-hardening pass, Oct 2026): tourist_profiles
grows a user_id column — a direct ownership record, not an inference.

Until now shared/ownership.py::enforce_profile_ownership had no real
ownership column to check: it inferred the owner of a TouristProfile by
searching the TripEvent log for the most recent 'survey_completed' event
referencing that profile_id, and only rejected access when that log
happened to name a DIFFERENT user. A profile with no matching log entry
(log never written, log entry expired/pruned, or the finalize call that
created it predates this feature) was treated as unowned and anyone could
read it. This migration adds the real column: nullable, no FK to `users`,
because layer1 also runs standalone (layer1/main.py) with no `users` table
on its own sys.path at all — a profile created there has no user to record
and stays unrestricted, same trust boundary as before this column existed.
Existing rows get NULL (unowned, unchanged behavior for them); new profiles
finalized through this app's authenticated /trips/survey/*/finalize now get
the real signed-in user's id stamped on creation (layer1/application/
survey_service.py::finalize) and shared/ownership.py checks this column
directly instead of the TripEvent-log inference.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tourist_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_tourist_profiles_user_id", "tourist_profiles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tourist_profiles_user_id", table_name="tourist_profiles")
    op.drop_column("tourist_profiles", "user_id")
