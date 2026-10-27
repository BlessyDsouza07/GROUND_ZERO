"""Shared "does this tourist_profile belong to this signed-in user?"
check, factored out so both `trips/service.py` (trip generation) and
`layer1/api/routes.py` (the legacy survey API, old visited-places API)
enforce the exact same rule instead of drifting.

UPDATE (final-release-hardening pass, Oct 2026): `tourist_profiles` now
has a real `user_id` column (migrations/versions/
a4b5c6d7e8f9_tourist_profile_ownership.py, layer1/domain/entities.py::
TouristProfile.user_id) stamped at finalize time
(layer1/application/survey_service.py::finalize). That column is now
the authoritative ownership record and is checked FIRST. The original
TripEvent-log inference (described below) is kept as a fallback purely
for profiles finalized before this column existed, where `user_id` is
NULL on the row itself but a `survey_completed` TripEvent may still
have the real owner on record — new profiles never need the fallback.

Original reasoning, kept for context: `tourist_profiles` (layer1, used
standalone outside this app too) deliberately had no `user_id` column
of its own — adding one would touch layer1's domain entity and its
independent standalone API (layer1/main.py), which an earlier pass
wasn't willing to risk destabilizing for a fix that didn't strictly
need it. The real risk an audit flagged is session hijacking: someone
who obtains (guesses, leaks, replays) another user's profile_id could
otherwise read or act on survey answers that aren't theirs. Every
profile that has ever been finalized through THIS app's
`/trips/survey/*/finalize` already gets a `survey_completed` TripEvent
recording exactly which user finalized it (trips/service.py::
finalize_survey) — so for pre-existing rows, ownership can still be
checked against that log, with no schema change needed for THOSE rows.
A profile with neither a `user_id` column value nor a matching
TripEvent (e.g. generated directly against a standalone layer1
deployment, outside this app entirely) is left unrestricted, since
this app has no record to check against — the same trust boundary
that already existed.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from layer1.infrastructure.db.models import TouristProfileModel
from trips.models import TripEvent


class ProfileNotOwned(Exception):
    """Raised when `profile_id` is on record as belonging to a
    different signed-in user than the one making the request."""


async def enforce_profile_ownership(db: AsyncSession, profile_id: str, user_id: uuid.UUID) -> None:
    try:
        profile_uuid = uuid.UUID(profile_id)
    except (ValueError, AttributeError, TypeError):
        profile_uuid = None

    owner_id = None
    if profile_uuid is not None:
        result = await db.execute(
            select(TouristProfileModel.user_id).where(TouristProfileModel.id == profile_uuid)
        )
        owner_id = result.scalar_one_or_none()

    if owner_id is None:
        # Fallback for rows finalized before the user_id column existed.
        result = await db.execute(
            select(TripEvent.user_id)
            .where(TripEvent.event_type == "survey_completed", TripEvent.profile_id == profile_id)
            .order_by(TripEvent.created_at.desc())
            .limit(1)
        )
        owner_id = result.scalar_one_or_none()

    if owner_id is not None and owner_id != user_id:
        raise ProfileNotOwned("This profile does not belong to your account.")
