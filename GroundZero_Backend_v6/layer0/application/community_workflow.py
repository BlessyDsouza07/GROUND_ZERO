"""
Community Submissions workflow (blueprint 3.1, source #7):

  User submits place -> Pending queue -> Admin review -> Approve
    -> Automatically enters Master Data Core -> Bias audit
    -> Freshness update -> Visible to tourists

This is the ONLY path by which a place can enter the Master Data Core
without having come from an automated collector. Nothing here fabricates
data — the admin is a human reviewing a human's submission.
"""
from __future__ import annotations

from datetime import datetime, timezone

from layer0.application.bias_audit import BiasAuditService
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import CommunitySubmission, Place
from layer0.domain.repositories import CommunitySubmissionRepository, PlaceRepository


class SubmissionRejected(Exception):
    pass


class CommunitySubmissionService:
    def __init__(
        self,
        submission_repo: CommunitySubmissionRepository,
        place_repo: PlaceRepository,
        bias_audit: BiasAuditService,
        freshness: FreshnessService,
    ):
        self.submission_repo = submission_repo
        self.place_repo = place_repo
        self.bias_audit = bias_audit
        self.freshness = freshness

    async def submit(
        self, place: Place, submitter_note: str | None, submitter_user_id: str | None = None,
    ) -> CommunitySubmission:
        submission = CommunitySubmission(
            id=None,
            submitted_place=place,
            submitter_note=submitter_note,
            status="pending",
            submitted_at=datetime.now(timezone.utc),
            # SECURITY FIX (final-release-hardening pass, Oct 2026): see
            # layer0/domain/entities.py::CommunitySubmission.submitter_user_id.
            # Optional and defaulted so this service's other/older callers
            # (if any) keep working unchanged.
            submitter_user_id=submitter_user_id,
        )
        return await self.submission_repo.create(submission)

    async def list_pending(self) -> list[CommunitySubmission]:
        return await self.submission_repo.list_pending()

    async def approve(self, submission_id: str, reviewed_by: str) -> Place:
        submission = await self.submission_repo.get_by_id(submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")
        if submission.status != "pending":
            raise SubmissionRejected(
                f"Submission {submission_id} is already {submission.status}, cannot re-approve"
            )

        place = submission.submitted_place
        place.last_verified_at = datetime.now(timezone.utc)

        breakdown = self.bias_audit.compute(place.bias_signals)
        place.bias_index = breakdown.bias_index
        place.grade = self.bias_audit.grade_for(breakdown.bias_index)
        place.freshness_score = self.freshness.score(place)

        stored = await self.place_repo.upsert(place)
        await self.submission_repo.update_status(submission_id, "approved", reviewed_by, resulting_place_id=stored.id)
        return stored

    async def reject(self, submission_id: str, reviewed_by: str) -> CommunitySubmission:
        submission = await self.submission_repo.get_by_id(submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")
        return await self.submission_repo.update_status(submission_id, "rejected", reviewed_by)
