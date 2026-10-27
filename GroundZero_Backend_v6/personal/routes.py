"""HTTP surface for Chunk 4's Contributions + Notifications. Every route
requires a signed-in user — unlike layer0's bare POST /places/submissions,
every submission made here is tied to a real user via ContributionRecord.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from fastapi import HTTPException

from auth.dependencies import get_current_user
from auth.models import User

from .dependencies import get_personal_service
from .schemas import (
    AddMediaIn,
    AddPlaceIn,
    ContributionOut,
    LocalTipIn,
    MyContributionsOut,
    NotificationsOut,
    ReportIncorrectIn,
    SavedPlaceOut,
    SavedPlacesOut,
    SuggestUpdateIn,
)
from .service import PersonalService

router = APIRouter(prefix="/personal", tags=["personal"])


@router.post("/contributions", response_model=ContributionOut, status_code=201)
async def add_contribution(
    body: AddPlaceIn, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> ContributionOut:
    return await svc.submit_place(user.id, body)


@router.post("/contributions/suggest-update", response_model=ContributionOut, status_code=201)
async def add_suggest_update(
    body: SuggestUpdateIn, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> ContributionOut:
    try:
        return await svc.submit_suggest_update(user.id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/contributions/local-tip", response_model=ContributionOut, status_code=201)
async def add_local_tip(
    body: LocalTipIn, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> ContributionOut:
    try:
        return await svc.submit_local_tip(user.id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/contributions/report-incorrect", response_model=ContributionOut, status_code=201)
async def add_report_incorrect(
    body: ReportIncorrectIn, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> ContributionOut:
    try:
        return await svc.submit_report_incorrect(user.id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/contributions/add-media", response_model=ContributionOut, status_code=201)
async def add_media_contribution(
    body: AddMediaIn, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> ContributionOut:
    try:
        return await svc.submit_add_media(user.id, body)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/contributions", response_model=MyContributionsOut)
async def my_contributions(
    user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> MyContributionsOut:
    return await svc.list_my_contributions(user.id)


@router.get("/notifications", response_model=NotificationsOut)
async def notifications(
    user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> NotificationsOut:
    return await svc.notifications(user.id)


# ---------------------------------------------------------------------------
# Saved Places — persistent bookmark, independent of any trip (final-
# release-hardening pass, Oct 2026: this feature didn't exist at all
# before this pass).
# ---------------------------------------------------------------------------
@router.post("/saved-places/{place_id}", response_model=SavedPlaceOut, status_code=201)
async def save_place(
    place_id: str, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> SavedPlaceOut:
    try:
        return await svc.save_place(user.id, place_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/saved-places/{place_id}", status_code=204, response_model=None)
async def unsave_place(
    place_id: str, user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> None:
    await svc.unsave_place(user.id, place_id)
    return None


@router.get("/saved-places", response_model=SavedPlacesOut)
async def saved_places(
    user: User = Depends(get_current_user), svc: PersonalService = Depends(get_personal_service)
) -> SavedPlacesOut:
    return await svc.list_saved_places(user.id)
