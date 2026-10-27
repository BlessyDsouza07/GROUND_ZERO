"""SECURITY FIX (final-release-hardening pass, Oct 2026): places grows a
verification_status column. Until now POST /places/custom (and the
identical path through POST /trips/{id}/places) wrote a tourist's own
self-reported place straight into the shared Master Data Core with no
review at all — immediately visible to every other tourist via GET
/places, /places/nearby, and HIVE's recommendation pool, indistinguishable
from the vetted, ETL-collected places around it. Community Submissions
(blueprint 3.1's #7 source) already has a real admin-approval queue for
exactly this kind of human-submitted data; tourist-added places had no
equivalent gate.

All 708 existing rows get 'verified' (server_default) — this migration
does not second-guess already-live Master Data, it only stops new
tourist-added places from silently joining it unreviewed. New
tourist-added places are created 'pending' (layer0/application/
custom_place_service.py) and excluded from HIVE's general candidate pool
and the public /places listing until an admin promotes them via the new
POST /admin/places/{id}/verify (layer0/api/admin.py) — see that file's
docstring for the detail. Pinning a place a tourist just added into their
OWN trip is unaffected: HiveEngine resolves pinned_place_ids by id
regardless of verification_status, same as before.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("verification_status", sa.String(length=20), nullable=False, server_default="verified"),
    )
    op.create_check_constraint(
        "ck_places_verification_status",
        "places",
        "verification_status IN ('verified', 'pending')",
    )
    op.create_index("ix_places_verification_status", "places", ["verification_status"])
    op.alter_column("places", "verification_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_places_verification_status", table_name="places")
    op.drop_constraint("ck_places_verification_status", "places", type_="check")
    op.drop_column("places", "verification_status")
