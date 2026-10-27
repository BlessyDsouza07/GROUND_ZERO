"""Explore's HTTP surface.

Auth posture (the one real architectural change this chunk makes):
every GET route below is reachable signed-out, per Carol's spec
("browsing/exploring must be allowed before sign-up"). Only
`POST /explore/add-to-journey` requires a signed-in user — it reuses
`auth.dependencies.get_current_user`, the exact same bearer-token
dependency every `/trips/*` route already requires, so there's no new
auth mechanism, just a router that doesn't force it everywhere.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_user
from auth.models import User
from trips.dependencies import get_trips_service
from trips.models import Trip
from trips.service import TripsService

from .dependencies import get_explore_service
from .mood_profiles import EXPERIENCE_CATEGORIES, MOOD_LABELS, MOOD_TAGLINES
from .schemas import (
    AddToJourneyIn,
    AddToJourneyOut,
    BeyondTheObviousOut,
    EventOut,
    ExperienceCategoryOut,
    MoodOut,
    SituationOut,
    PickOut,
    PlaceCardOut,
    PlaceDetailOut,
    RightNowOut,
    SearchResultOut,
)
from .service import ExploreService

logger = logging.getLogger("groundzero.explore")

router = APIRouter(prefix="/explore", tags=["explore"])

_SUGGESTED_SEARCHES = ["Quiet places", "Sunset spots", "Rain-friendly", "Family friendly", "Local food", "Beaches"]


def _events_today_count() -> Optional[int]:
    try:
        import live_events.app.main as events_app_module
        from live_events.app.models import Event
    except Exception:
        return None
    db = events_app_module.SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
        return db.query(Event).filter(Event.start_at >= start, Event.start_at < end).count()
    except Exception:
        logger.exception("Explore: could not read live_events count (non-fatal — Right Now will omit it)")
        return None
    finally:
        db.close()


def _events_today_list(limit: int = 10) -> list[dict]:
    try:
        import live_events.app.main as events_app_module
        from live_events.app.models import Event
    except Exception:
        return []
    db = events_app_module.SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
        rows = (
            db.query(Event)
            .filter(Event.start_at >= start, Event.start_at < end, Event.status == "ACTIVE")
            .order_by(Event.start_at.asc())
            .limit(limit)
            .all()
        )
        return [
            dict(
                id=e.id, title=e.title,
                start_at=e.start_at.isoformat() if e.start_at else None,
                venue=e.venue, address=e.address, source_url=e.source_url,
            )
            for e in rows
        ]
    except Exception:
        logger.exception("Explore: could not read live_events list (non-fatal — Happening Today will be empty)")
        return []
    finally:
        db.close()


@router.get("/moods", response_model=list[MoodOut])
async def list_moods() -> list[MoodOut]:
    return [MoodOut(slug=slug, label=label, tagline=MOOD_TAGLINES[slug]) for slug, label in MOOD_LABELS.items()]


@router.get("/context", response_model=RightNowOut)
async def right_now(
    lat: Optional[float] = None, lng: Optional[float] = None,
    svc: ExploreService = Depends(get_explore_service),
) -> RightNowOut:
    events_count = _events_today_count()
    data = await svc.right_now(lat, lng, events_count)
    return RightNowOut(**data)


@router.get("/situation", response_model=SituationOut)
async def situation(
    lat: float, lng: float, approx: bool = False, accuracy: Optional[float] = None, svc: ExploreService = Depends(get_explore_service),
) -> SituationOut:
    return SituationOut(**(await svc.situation(lat, lng, approx, accuracy)))


@router.get("/happening-today", response_model=list[EventOut])
async def happening_today() -> list[EventOut]:
    return [EventOut(**e) for e in _events_today_list()]


@router.get("/picks", response_model=list[PickOut])
async def groundzero_picks(
    mood: str, lat: Optional[float] = None, lng: Optional[float] = None, limit: int = 12,
    svc: ExploreService = Depends(get_explore_service),
) -> list[PickOut]:
    if mood not in MOOD_LABELS:
        raise HTTPException(400, f"Unknown mood '{mood}'. Valid moods: {sorted(MOOD_LABELS)}")
    cards = await svc.picks(mood, lat, lng, limit=limit)
    return [PickOut(**c) for c in cards]


@router.get("/beyond-the-obvious", response_model=list[BeyondTheObviousOut])
async def beyond_the_obvious(
    lat: Optional[float] = None, lng: Optional[float] = None, limit: int = 10,
    svc: ExploreService = Depends(get_explore_service),
) -> list[BeyondTheObviousOut]:
    cards = await svc.beyond_the_obvious(lat, lng, limit=limit)
    return [BeyondTheObviousOut(**c) for c in cards]


@router.get("/experiences", response_model=list[ExperienceCategoryOut])
async def experience_categories(
    lat: Optional[float] = None, lng: Optional[float] = None,
    svc: ExploreService = Depends(get_explore_service),
) -> list[ExperienceCategoryOut]:
    cats = await svc.experience_categories(lat, lng)
    return [ExperienceCategoryOut(**c) for c in cats]


@router.get("/experiences/{slug}", response_model=list[PlaceCardOut])
async def experience_category(
    slug: str, lat: Optional[float] = None, lng: Optional[float] = None, limit: int = 40,
    svc: ExploreService = Depends(get_explore_service),
) -> list[PlaceCardOut]:
    if slug not in {e.slug for e in EXPERIENCE_CATEGORIES}:
        raise HTTPException(404, f"Unknown experience category '{slug}'")
    cards = await svc.experience_category(slug, lat, lng, limit=limit)
    return [PlaceCardOut(**c) for c in cards]


@router.get("/search", response_model=SearchResultOut)
async def search(
    q: str = "", lat: Optional[float] = None, lng: Optional[float] = None,
    category: Optional[str] = None, max_distance_km: Optional[float] = None, open_now: bool = False,
    limit: int = 30, svc: ExploreService = Depends(get_explore_service),
) -> SearchResultOut:
    results = await svc.search(q, lat, lng, category=category, max_distance_km=max_distance_km, open_now=open_now, limit=limit)
    return SearchResultOut(results=[PlaceCardOut(**c) for c in results], suggested_searches=_SUGGESTED_SEARCHES)


@router.get("/place/{place_id}", response_model=PlaceDetailOut)
async def place_detail(
    place_id: str, lat: Optional[float] = None, lng: Optional[float] = None,
    svc: ExploreService = Depends(get_explore_service),
) -> PlaceDetailOut:
    detail = await svc.place_detail(place_id, lat, lng)
    if detail is None:
        raise HTTPException(404, "Place not found")
    return PlaceDetailOut(**detail)


async def _find_draft_trip(db: AsyncSession, user_id) -> Optional[Trip]:
    # selectinload(Trip.places) — same reason as TripsService.get_trip()
    # (see trips/README_TRIPS.md): TripsService.add_place() reads
    # trip.places synchronously to compute the next order_index, and a
    # plain select() without eager-loading triggers an unawaited lazy
    # load under asyncio (MissingGreenlet), not a lazy "just works" read.
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.places))
        .where(Trip.user_id == user_id, Trip.status == "draft")
        .order_by(Trip.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/add-to-journey", response_model=AddToJourneyOut)
async def add_to_journey(
    body: AddToJourneyIn,
    user: User = Depends(get_current_user),  # the one Explore route that DOES require sign-in
    svc: TripsService = Depends(get_trips_service),
) -> AddToJourneyOut:
    """Wires Explore's "ADD TO MY JOURNEY" CTA directly into the existing
    chunk-2 trip-planning flow — no new place-adding mechanism, this calls
    the exact same `TripsService.add_place` chunk 2's own "add a place to
    my itinerary" screen uses.

    If the tourist has no draft trip yet (the common case — they were
    browsing Explore before ever starting New Trip), there is nothing to
    add this place TO yet. Rather than silently creating a half-formed
    trip with made-up answers, this reports `no_active_trip` and hands
    back the place_id so the Flutter app can route into the New Trip
    survey and pass it as a `pinned_place_id` — `TripsService.generate_trip`
    already accepts `pinned_place_ids` (chunk 2), so the place a tourist
    discovered in Explore really does show up in the itinerary HIVE
    builds for them, not just acknowledged and dropped."""
    if body.trip_id:
        try:
            trip = await svc.get_trip(uuid.UUID(body.trip_id), user.id)
        except (LookupError, ValueError):
            raise HTTPException(404, "Trip not found")
    else:
        trip = await _find_draft_trip(svc.db, user.id)

    if trip is None:
        return AddToJourneyOut(
            status="no_active_trip", trip_id=None, trip_place_id=None,
            message="You don't have a trip in progress yet. Start New Trip — this place will already be pinned in it.",
        )

    try:
        trip_place = await svc.add_place(trip, body.place_id, None, None, None, None, None, 0.0)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await svc.db.commit()

    return AddToJourneyOut(
        status="added", trip_id=str(trip.id), trip_place_id=str(trip_place.id),
        message="Added to your journey.",
    )
