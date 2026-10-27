from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from layer0.api.dependencies import (
    get_community_submission_service,
    get_etl_orchestrator,
    get_place_repository,
)
from layer0.api.schemas import EtlRunReportOut, SubmissionReviewIn
from layer0.api.security import require_admin_api_key
from layer0.application.community_workflow import CommunitySubmissionService, SubmissionRejected
from layer0.application.etl_orchestrator import EtlOrchestrator
from layer0.domain.repositories import PlaceRepository
from shared.config import Settings, get_settings

# dependencies= at the router level protects every route in this file,
# current and future, with one line — rather than requiring every new
# admin endpoint to remember to add the auth dependency individually.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_api_key)])


@router.post("/pipeline/run", response_model=EtlRunReportOut)
async def run_pipeline(
    orchestrator: EtlOrchestrator = Depends(get_etl_orchestrator),
    settings: Settings = Depends(get_settings),
) -> EtlRunReportOut:
    bbox = (settings.bbox_south, settings.bbox_west, settings.bbox_north, settings.bbox_east)
    report = await orchestrator.run(bbox)
    return EtlRunReportOut(**report.as_dict())


@router.get("/submissions/pending")
async def list_pending_submissions(
    service: CommunitySubmissionService = Depends(get_community_submission_service),
):
    submissions = await service.list_pending()
    return [
        {
            "id": s.id,
            "place_name": s.submitted_place.name,
            "category": s.submitted_place.category,
            "submitter_note": s.submitter_note,
            "submitted_at": s.submitted_at,
        }
        for s in submissions
    ]


@router.post("/submissions/{submission_id}/approve")
async def approve_submission(
    submission_id: str,
    payload: SubmissionReviewIn,
    service: CommunitySubmissionService = Depends(get_community_submission_service),
):
    try:
        place = await service.approve(submission_id, payload.reviewed_by)
    except SubmissionRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"place_id": place.id, "bias_index": place.bias_index, "grade": place.grade.value if place.grade else None}


@router.post("/submissions/{submission_id}/reject")
async def reject_submission(
    submission_id: str,
    payload: SubmissionReviewIn,
    service: CommunitySubmissionService = Depends(get_community_submission_service),
):
    try:
        submission = await service.reject(submission_id, payload.reviewed_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": submission.id, "status": submission.status}


@router.get("/places/pending")
async def list_pending_places(repo: PlaceRepository = Depends(get_place_repository)):
    """SECURITY FIX (final-release-hardening pass, Oct 2026): the review
    queue for tourist-added places (CustomPlaceService.add_or_find),
    which — unlike Community Submissions — are stored immediately (as
    verification_status="pending") rather than held in a separate
    submissions table, since the tourist needs their own pin usable right
    away. This lists them for an admin to review; POST
    /admin/places/{place_id}/verify promotes one to "verified" so it
    joins GET /places and HIVE's general recommendation pool for
    everyone, not just the tourist who added it. There is deliberately no
    reject/delete endpoint yet — a pending place that's never promoted
    simply never reaches anyone but its own tourist, which is a safe
    default, not a gap; a moderation UI for actively rejecting/deleting
    one is left for a future pass (it's effectively never-verified not
    quite the same as a Community Submission's explicit "rejected"
    status, and this module intentionally doesn't reuse PlaceRepository's
    upsert to delete anything)."""
    places = await repo.list_all()
    pending = [p for p in places if p.verification_status == "pending"]
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "description": p.description,
            "estimated_cost": p.estimated_cost,
            "source": [s.value for s in p.source],
        }
        for p in pending
    ]


@router.post("/places/{place_id}/verify")
async def verify_place(place_id: str, repo: PlaceRepository = Depends(get_place_repository)):
    """Promotes a pending tourist-added place to "verified" — see
    list_pending_places above and CustomPlaceService's module docstring
    for the full flow this closes."""
    place = await repo.get_by_id(place_id)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place {place_id} not found")
    if place.verification_status == "verified":
        return {"place_id": place.id, "verification_status": "verified", "already_verified": True}
    place.verification_status = "verified"
    stored = await repo.upsert(place)
    return {"place_id": stored.id, "verification_status": stored.verification_status, "already_verified": False}


@router.get("/stats")
async def pipeline_stats(repo: PlaceRepository = Depends(get_place_repository)):
    places = await repo.list_all()
    if not places:
        return {"total_places": 0}

    grade_counts: dict[str, int] = {}
    for p in places:
        key = p.grade.value if p.grade else "ungraded"
        grade_counts[key] = grade_counts.get(key, 0) + 1

    avg_bias = sum(p.bias_index for p in places if p.bias_index is not None) / max(
        1, sum(1 for p in places if p.bias_index is not None)
    )
    avg_freshness = sum(p.freshness_score for p in places) / len(places)
    stale_count = sum(1 for p in places if p.temporarily_unavailable)

    return {
        "total_places": len(places),
        "grade_distribution": grade_counts,
        "average_bias_index": round(avg_bias, 4),
        "average_freshness_score": round(avg_freshness, 4),
        "temporarily_unavailable_count": stale_count,
    }
