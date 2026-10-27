"""SECURITY FIX (final-release-hardening pass, Oct 2026): community_submissions
grows a submitter_user_id column.

Until now a CommunitySubmission row recorded no submitter at all — once
POST /submissions was auth-gated (an earlier pass), every call still
required a signed-in user, but nothing on the row said WHICH one. This adds
the real column: nullable, no FK to `users`, because layer0 also runs
standalone (layer0/main.py) with no `users` table on its own sys.path at
all — a submission created there has no user to record and stays
unrestricted, same trust boundary as layer1's TouristProfile.user_id
(migrations/versions/a4b5c6d7e8f9_tourist_profile_ownership.py) and for
the identical reason. Existing rows get NULL (unowned, unchanged
behavior); new submissions made through this app's authenticated
POST /places/submissions now get the real signed-in user's id
(layer0/api/routes.py::submit_place -> layer0/application/
community_workflow.py::CommunitySubmissionService.submit).

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "community_submissions",
        sa.Column("submitter_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_community_submissions_submitter_user_id", "community_submissions", ["submitter_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_community_submissions_submitter_user_id", table_name="community_submissions")
    op.drop_column("community_submissions", "submitter_user_id")
