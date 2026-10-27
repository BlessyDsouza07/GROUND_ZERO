from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from layer0.api.dependencies import get_db_session
from layer2.api.dependencies import get_itinerary_feedback_service
from layer2.api.feedback_schemas import ConfirmedItineraryOut, ItineraryItemOut, SaveItineraryIn
from layer2.application.feedback_service import ItineraryFeedbackService
from layer2.domain.feedback_entities import ConfirmedItinerary, ItineraryItem
from shared.ownership import ProfileNotOwned, enforce_profile_ownership

router = APIRouter(prefix="/hive/itinerary", tags=["itinerary-feedback"])

# SECURITY FIX (4th audit response, Oct 2026): every route here used to
# take a bare profile_id with no auth dependency at all -- anyone who
# knew (or guessed) a profile_id could read, overwrite, or confirm that
# person's saved itinerary. Same shape of bug as /hive/recommendations
# had before the previous pass, just missed then because this router
# lives in its own file. Fixed the same way: require a signed-in user
# and the shared profile-ownership check.


async def _check_profile_ownership_or_403(db: AsyncSession, profile_id: str, user_id) -> None:
    try:
        await enforce_profile_ownership(db, profile_id, user_id)
    except ProfileNotOwned as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _to_out(itinerary: ConfirmedItinerary) -> ConfirmedItineraryOut:
    return ConfirmedItineraryOut(
        profile_id=itinerary.profile_id,
        items=[
            ItineraryItemOut(place_id=i.place_id, place_name=i.place_name, role=i.role, order_index=i.order_index)
            for i in itinerary.items
        ],
        removed_place_ids=itinerary.removed_place_ids,
        added_place_ids=itinerary.added_place_ids,
        place_ratings=itinerary.place_ratings,
        overall_rating=itinerary.overall_rating,
        status=itinerary.status.value,
        created_at=itinerary.created_at,
        updated_at=itinerary.updated_at,
        confirmed_at=itinerary.confirmed_at,
    )


@router.post("/{profile_id}/save", response_model=ConfirmedItineraryOut)
async def save_itinerary(
    profile_id: str,
    payload: SaveItineraryIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    service: ItineraryFeedbackService = Depends(get_itinerary_feedback_service),
) -> ConfirmedItineraryOut:
    await _check_profile_ownership_or_403(db, profile_id, user.id)
    items = [
        ItineraryItem(place_id=i.place_id, place_name=i.place_name, role=i.role, order_index=idx)
        for idx, i in enumerate(payload.items)
    ]
    itinerary = await service.save_draft(
        profile_id, items, payload.removed_place_ids, payload.added_place_ids,
        payload.place_ratings, payload.overall_rating,
    )
    return _to_out(itinerary)


@router.post("/{profile_id}/confirm", response_model=ConfirmedItineraryOut)
async def confirm_itinerary(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    service: ItineraryFeedbackService = Depends(get_itinerary_feedback_service),
) -> ConfirmedItineraryOut:
    await _check_profile_ownership_or_403(db, profile_id, user.id)
    try:
        itinerary = await service.confirm(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_out(itinerary)


@router.get("/{profile_id}", response_model=ConfirmedItineraryOut)
async def get_itinerary(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    service: ItineraryFeedbackService = Depends(get_itinerary_feedback_service),
) -> ConfirmedItineraryOut:
    await _check_profile_ownership_or_403(db, profile_id, user.id)
    itinerary = await service.get(profile_id)
    if itinerary is None:
        raise HTTPException(status_code=404, detail=f"No saved itinerary for profile {profile_id}")
    return _to_out(itinerary)
