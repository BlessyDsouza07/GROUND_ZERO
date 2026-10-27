"""Chunk 4 — Contributions + Notifications.

One table exists in this module: `ContributionRecord`, covering all
five contribution actions from the spec (kind = add_place |
suggest_update | local_tip | report_incorrect | add_media).

For `add_place` only, `submission_id` points at a real
`CommunitySubmission` row (layer0) and the existing User -> Submission
-> Community Data -> Validation -> Review -> Approved -> Master Data
pipeline in layer0/application/community_workflow.py is the moderation
authority — this table never re-implements that review logic, it only
remembers which signed-in user made which submission (layer0's own
CommunitySubmission has no submitter field, and /places/submissions
wasn't user-scoped until this pass).

The other four kinds (suggest_update, local_tip, report_incorrect,
add_media) are, honestly, logged here with `status="pending"` and a
`metadata_json` payload, but are NOT yet wired into an admin review
queue or into Master Data — there is no admin UI action that approves
a "suggest an update" or a "local tip" yet. This is disclosed in
README_PERSONAL.md rather than faked with an invented approval. Adding
that review queue later means giving admin/review_actions a `kind`
switch, not new architecture — the shape (user -> record -> status ->
reviewed_at) is already here waiting for it.

`add_media`'s `metadata_json["media_url"]` is a placeholder string the
same way Journal's media_url is (see trips/models.py's JournalEntry) —
no object-storage upload pipeline exists in this backend yet. See
README_PERSONAL.md's "What's real vs. placeholder" section.

Notifications need no table at all — see personal/service.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from layer0.infrastructure.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ContributionRecord(Base):
    __tablename__ = "contribution_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # layer0's community_submissions.id, stored as a plain string (not an
    # ORM FK relationship) — this module never queries that table
    # directly by join, it goes back through
    # CommunitySubmissionService/CommunitySubmissionRepository.get_by_id,
    # same as layer0's own admin routes do. Only populated for
    # kind="add_place"; the other four kinds have no layer0 submission.
    submission_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="add_place")
    # pending | approved | rejected. For add_place this mirrors the
    # layer0 submission's own status (read live, not duplicated here —
    # see PersonalService.list_my_contributions). For the other four
    # kinds, this column IS the authoritative status, and today nothing
    # ever moves it off "pending" — there's no review action wired up
    # yet, which is disclosed rather than faked.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # The existing place this contribution is about — null only for
    # add_place, where the place doesn't exist yet (that's the point of
    # the submission).
    place_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # The kind-specific payload (field/current_value/suggested_value for
    # suggest_update; tip/best_time/context for local_tip; issue_type/
    # description/evidence for report_incorrect; media_url/caption/source
    # for add_media). Kept as one flexible JSON column rather than four
    # near-duplicate tables, since none of these kinds has its own review
    # workflow yet to justify first-class columns.
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedPlace(Base):
    """SECURITY/FEATURE FIX (final-release-hardening pass, Oct 2026): a
    persistent "Save" / bookmark a tourist can put on any place, independent
    of any trip. Previously there was no Save feature at all in this
    backend — a review flagged this as a basic, expected piece of
    functionality that was simply missing. This table is deliberately the
    simplest possible shape: who saved what, and when. No notes, no
    folders/collections, no sharing — none of that was asked for; this is
    just a persistent bookmark list, the thing actually needed.

    `place_id` is stored as a plain string, not an ORM FK relationship,
    matching ContributionRecord.place_id just above — this module never
    joins against `places` directly, it goes back through
    PlaceRepository.get_by_id for display data, same pattern used
    throughout this module. `user_id` DOES get a real FK (CASCADE), same
    as ContributionRecord.user_id — `personal/` only runs inside this
    combined app (no standalone main.py of its own), so unlike layer0/
    layer1's nullable, FK-less ownership columns, there's no standalone
    deployment missing a `users` table to stay compatible with here.

    Unique constraint on (user_id, place_id): saving an already-saved
    place is a harmless no-op (service layer checks first and returns the
    existing row), not a duplicate row or a 500.
    """
    __tablename__ = "saved_places"
    __table_args__ = (UniqueConstraint("user_id", "place_id", name="uq_saved_places_user_place"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    place_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
