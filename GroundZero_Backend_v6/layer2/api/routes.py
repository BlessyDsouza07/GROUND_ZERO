from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from layer0.api.dependencies import get_db_session
from layer1.domain.repositories import TouristProfileRepository
from layer2.api.dependencies import get_hive_engine, get_profile_repository
from layer2.api.schemas import (
    MultiDayRecommendationOut,
    RecommendationItemOut,
    RecommendationQueueOut,
    RecommendationRequestIn,
)
from layer2.application.hive_engine import HiveEngine
from layer2.domain.entities import RecommendationQueue
from shared.ownership import ProfileNotOwned, enforce_profile_ownership

router = APIRouter(prefix="/hive", tags=["hive-engine"])

# SECURITY NOTE (audit response, Oct 2026): both endpoints below used to
# take a bare profile_id with no auth at all — the Flutter app itself
# never calls these directly (it goes through /trips/generate, which
# already enforces ownership), but they were still reachable by anyone.
# Now both require a signed-in user and the same profile-ownership
# check /trips/generate uses (shared/ownership.py).


def _queue_to_out(queue: RecommendationQueue) -> RecommendationQueueOut:
    return RecommendationQueueOut(
        profile_id=queue.profile_id,
        items=[
            RecommendationItemOut(
                place_id=i.place_id, place_name=i.place_name, role=i.role.value,
                scheduled_time=i.scheduled_time, travel_mode=i.travel_mode.value,
                travel_time_minutes=i.travel_time_minutes, travel_is_routed=i.travel_is_routed,
                estimated_cost=i.estimated_cost,
                reason_selected=i.reason_selected, personal_score=i.personal_score,
                weather_adjusted=i.weather_adjusted, weather_adjustment_note=i.weather_adjustment_note,
            )
            for i in queue.items
        ],
        total_estimated_cost=queue.total_estimated_cost,
        generated_at=queue.generated_at,
        geofence_radius_km=queue.geofence_radius_km,
        slots_requested=queue.slots_requested,
        slots_filled=queue.slots_filled,
        slots_dropped_closed=queue.slots_dropped_closed,
    )


async def _check_profile_ownership_or_403(db: AsyncSession, profile_id: str, user_id) -> None:
    try:
        await enforce_profile_ownership(db, profile_id, user_id)
    except ProfileNotOwned as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/recommendations", response_model=RecommendationQueueOut)
async def generate_recommendations(
    payload: RecommendationRequestIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    engine: HiveEngine = Depends(get_hive_engine),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
) -> RecommendationQueueOut:
    await _check_profile_ownership_or_403(db, payload.profile_id, user.id)
    profile = await profile_repo.get_by_id(payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"TouristProfile {payload.profile_id} not found")

    start_time = payload.start_time or datetime.now(timezone.utc)
    queue = await engine.build_recommendation_queue(
        profile, start_time, payload.pinned_place_ids,
        start_latitude=payload.start_latitude, start_longitude=payload.start_longitude,
    )
    return _queue_to_out(queue)


@router.post("/recommendations/multi-day", response_model=MultiDayRecommendationOut)
async def generate_multi_day_recommendations(
    payload: RecommendationRequestIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    engine: HiveEngine = Depends(get_hive_engine),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
) -> MultiDayRecommendationOut:
    """For a TouristProfile with trip_duration_hours=multi_day — generates
    one queue per day, with each day excluding places already used earlier
    in the same trip. Works fine (returns a single day) for non-multi-day
    profiles too, so a client can always call this instead of guessing."""
    await _check_profile_ownership_or_403(db, payload.profile_id, user.id)
    profile = await profile_repo.get_by_id(payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"TouristProfile {payload.profile_id} not found")

    start_time = payload.start_time or datetime.now(timezone.utc)
    queues = await engine.build_multi_day_recommendation_queue(profile, start_time, payload.pinned_place_ids)
    return MultiDayRecommendationOut(days=[_queue_to_out(q) for q in queues])
