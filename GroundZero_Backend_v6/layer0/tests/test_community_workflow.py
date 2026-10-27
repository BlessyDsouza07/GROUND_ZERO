import pytest

from layer0.application.bias_audit import BiasAuditService
from layer0.application.community_workflow import CommunitySubmissionService, SubmissionRejected
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import (
    AccessibilityInfo,
    BiasSignals,
    CommunitySubmission,
    Coordinates,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.domain.repositories import CommunitySubmissionRepository, PlaceRepository


class FakePlaceRepository(PlaceRepository):
    def __init__(self):
        self.stored: dict[str, Place] = {}
        self._counter = 0

    async def get_by_id(self, place_id):
        return self.stored.get(place_id)

    async def find_duplicates(self, place, radius_meters=75.0):
        return []

    async def upsert(self, place):
        if place.id is None:
            self._counter += 1
            place.id = f"place-{self._counter}"
        self.stored[place.id] = place
        return place

    async def bulk_upsert(self, places):
        return [await self.upsert(p) for p in places]

    async def list_all(self, category=None):
        return list(self.stored.values())

    async def list_stale(self, older_than_days):
        return []

    async def delete(self, place_id):
        self.stored.pop(place_id, None)

    async def record_visit(self, place_id):
        pass


class FakeSubmissionRepository(CommunitySubmissionRepository):
    def __init__(self):
        self.submissions: dict[str, CommunitySubmission] = {}
        self._counter = 0

    async def create(self, submission):
        self._counter += 1
        submission.id = f"submission-{self._counter}"
        self.submissions[submission.id] = submission
        return submission

    async def get_by_id(self, submission_id):
        return self.submissions.get(submission_id)

    async def list_pending(self):
        return [s for s in self.submissions.values() if s.status == "pending"]

    async def update_status(self, submission_id, status, reviewed_by, resulting_place_id=None):
        submission = self.submissions[submission_id]
        submission.status = status
        submission.reviewed_by = reviewed_by
        if resulting_place_id is not None:
            submission.submitted_place.id = resulting_place_id
        return submission


def _place(name="Test Place", local_percentage=0.0) -> Place:
    return Place(
        id=None, name=name, category="local_kitchen",
        coordinates=Coordinates(latitude=12.91, longitude=74.84),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.BUDGET, estimated_cost=100.0,
        bias_signals=BiasSignals(local_percentage=local_percentage), accessibility=AccessibilityInfo(),
    )


def _service():
    place_repo = FakePlaceRepository()
    sub_repo = FakeSubmissionRepository()
    service = CommunitySubmissionService(sub_repo, place_repo, BiasAuditService(), FreshnessService(180))
    return service, place_repo, sub_repo


@pytest.mark.asyncio
async def test_submit_creates_pending_submission():
    service, _, _ = _service()
    submission = await service.submit(_place(), "a note")
    assert submission.status == "pending"
    assert submission.id is not None


@pytest.mark.asyncio
async def test_approve_computes_bias_and_stores_place():
    service, place_repo, _ = _service()
    submission = await service.submit(_place(local_percentage=0.9), "genuine local spot")
    approved = await service.approve(submission.id, reviewed_by="admin1")
    assert approved.bias_index is not None
    assert approved.id in place_repo.stored


@pytest.mark.asyncio
async def test_approve_sets_resulting_place_id_on_the_submission():
    """Regression test: resulting_place_id was previously read everywhere
    but never written anywhere — this confirms the fix."""
    service, place_repo, sub_repo = _service()
    submission = await service.submit(_place(), "a note")
    approved_place = await service.approve(submission.id, reviewed_by="admin1")

    refetched = await sub_repo.get_by_id(submission.id)
    assert refetched.submitted_place.id == approved_place.id


@pytest.mark.asyncio
async def test_approve_twice_raises_submission_rejected():
    service, _, _ = _service()
    submission = await service.submit(_place(), "a note")
    await service.approve(submission.id, reviewed_by="admin1")
    with pytest.raises(SubmissionRejected):
        await service.approve(submission.id, reviewed_by="admin2")


@pytest.mark.asyncio
async def test_approve_unknown_submission_raises_value_error():
    service, _, _ = _service()
    with pytest.raises(ValueError):
        await service.approve("does-not-exist", reviewed_by="admin1")


@pytest.mark.asyncio
async def test_reject_marks_status_without_storing_place():
    service, place_repo, sub_repo = _service()
    submission = await service.submit(_place(), "a note")
    result = await service.reject(submission.id, reviewed_by="admin1")
    assert result.status == "rejected"
    assert len(place_repo.stored) == 0


@pytest.mark.asyncio
async def test_list_pending_excludes_reviewed_submissions():
    service, _, _ = _service()
    s1 = await service.submit(_place("Place A"), "note A")
    s2 = await service.submit(_place("Place B"), "note B")
    await service.approve(s1.id, reviewed_by="admin1")

    pending = await service.list_pending()
    assert len(pending) == 1
    assert pending[0].id == s2.id
