"""HTTP surface for the New Trip flow. See trips/service.py for the
question-order mapping and trips/README_TRIPS.md for what's reused vs
new. Every endpoint here requires a signed-in user (auth/dependencies.get_current_user)."""
from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependencies import get_current_user
from auth.models import User
from layer1.application.survey_service import InvalidSurveyAnswer, SurveySessionNotOwned

from trips.dependencies import get_trips_service
from trips.models import JournalEntry, Trip, TripPlace
from trips.schemas import (
    AddPlaceIn,
    ArriveIn,
    CheckoutIn,
    ConfirmTripIn,
    ExitTripIn,
    GenerateItineraryIn,
    ItineraryItemOut,
    JournalEntryIn,
    JournalEntryOut,
    JournalTimelineOut,
    MyTripsOut,
    RateTripIn,
    ReorderIn,
    ResumeDecisionIn,
    SearchPlaceOut,
    SkipIn,
    SurveyAnswerIn,
    SurveyFinalizeOut,
    SurveyStartOut,
    SurveyStateOut,
    TopUpBudgetIn,
    TripOut,
    TripStoryOut,
    TripSummaryOut,
)
from trips.service import TripsService, crowd_slider_to_tolerance, energy_slider_to_band

_IST = ZoneInfo("Asia/Kolkata")
router = APIRouter(prefix="/trips", tags=["trips"])


def _place_out(p: TripPlace) -> ItineraryItemOut:
    return ItineraryItemOut(
        trip_place_id=str(p.id), place_id=p.place_id, place_name=p.place_name, role=p.role,
        order_index=p.order_index, scheduled_time=p.scheduled_time, travel_mode=p.travel_mode,
        travel_time_minutes=p.travel_time_minutes, estimated_cost=p.estimated_cost,
        reason_selected=p.reason_selected, latitude=p.latitude, longitude=p.longitude,
        is_tourist_added=p.is_tourist_added, status=p.status,
    )


def _trip_out(t: Trip) -> TripOut:
    return TripOut(
        trip_id=str(t.id), status=t.status, profile_id=t.profile_id, budget_total=t.budget_total,
        budget_remaining=t.budget_remaining, energy_band=t.energy_band,
        notifications_enabled=t.notifications_enabled, voice_guide_enabled=t.voice_guide_enabled,
        geofence_radius_km=t.geofence_radius_km, origin_latitude=t.origin_latitude,
        origin_longitude=t.origin_longitude, scheduled_start_at=t.scheduled_start_at,
        started_at=t.started_at, layer3_session_id=t.layer3_session_id,
        places=[_place_out(p) for p in t.places],
    )


async def _get_owned_trip(trip_id: str, user: User, svc: TripsService) -> Trip:
    try:
        return await svc.get_trip(uuid.UUID(trip_id), user.id)
    except (LookupError, ValueError) as exc:
        raise HTTPException(404, str(exc) or "Trip not found")


# ---------------------------------------------------------------------------
# Survey — see service.py module docstring for the exact 9-step mapping.
# The slider steps (q2_energy, q3_crowd_tolerance) accept a raw 0-100
# number as `value` and are converted to the underlying enum here, so the
# Flutter slider widget never needs to know the enum's own values exist.
# ---------------------------------------------------------------------------
@router.post("/survey/start", response_model=SurveyStartOut)
async def start_survey(
    user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> SurveyStartOut:
    # Audit fix (3rd pass): start/state/answer used to have no auth
    # dependency at all (only /finalize did) — a guessable session_id
    # let anyone read or advance someone else's in-progress survey
    # answers.
    #
    # SECURITY FIX (final-release-hardening pass, Oct 2026): that earlier
    # fix only proved the CALLER is signed in — it never bound the
    # session itself to that caller, so a different signed-in user who
    # obtained this session_id (it's returned in every response body)
    # could still read/advance/finalize it. svc.start_survey now records
    # user.id on the session at creation, and every other survey call
    # below verifies the requester against it (see
    # SurveySessionNotOwned in layer1/application/survey_service.py).
    session_id, next_step = await svc.start_survey(user.id)
    return SurveyStartOut(session_id=session_id, next_step=next_step)


@router.get("/survey/{session_id}", response_model=SurveyStateOut)
async def survey_state(
    session_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> SurveyStateOut:
    try:
        next_step, progress, done = await svc.get_survey_state(session_id, user.id)
    except SurveySessionNotOwned as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return SurveyStateOut(session_id=session_id, next_step=next_step, progress_fraction=progress, done=done)


@router.post("/survey/{session_id}/answer", response_model=SurveyStateOut)
async def answer_survey(
    session_id: str, body: SurveyAnswerIn,
    user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service),
) -> SurveyStateOut:
    value = body.value
    if body.step == "q2_energy":
        value = energy_slider_to_band(float(value))
    elif body.step == "q3_crowd_tolerance":
        value = crowd_slider_to_tolerance(float(value))
    try:
        next_step, progress, done = await svc.answer_survey(session_id, body.step, value, user.id)
    except SurveySessionNotOwned as exc:
        raise HTTPException(403, str(exc))
    except InvalidSurveyAnswer as exc:
        raise HTTPException(422, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return SurveyStateOut(session_id=session_id, next_step=next_step, progress_fraction=progress, done=done)


@router.post("/survey/{session_id}/finalize", response_model=SurveyFinalizeOut)
async def finalize_survey(
    session_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> SurveyFinalizeOut:
    try:
        profile = await svc.finalize_survey(session_id, user.id)
    except SurveySessionNotOwned as exc:
        raise HTTPException(403, str(exc))
    except InvalidSurveyAnswer as exc:
        raise HTTPException(422, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    await svc.db.commit()
    return SurveyFinalizeOut(profile_id=profile.id or "")


# ---------------------------------------------------------------------------
# Draft itinerary: generate, then add/remove/reorder/rate before confirming.
# ---------------------------------------------------------------------------
@router.post("/generate", response_model=TripOut)
async def generate_trip(
    body: GenerateItineraryIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    try:
        trip = await svc.generate_trip(
            user.id, body.profile_id, body.start_latitude, body.start_longitude,
            body.start_time, body.pinned_place_ids,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    await svc.db.commit()
    return _trip_out(trip)


@router.get("/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    return _trip_out(trip)


@router.get("/places/search", response_model=list[SearchPlaceOut])
async def search_places(
    query: str = "", svc: TripsService = Depends(get_trips_service)
) -> list[SearchPlaceOut]:
    """Typeahead for "add a place" — a simple case-insensitive name match
    over the Master Data Core. If nothing matches, the Flutter app's
    add-place form falls back to POST /trips/{id}/places with a
    name+lat+lng instead of a place_id, which creates a brand-new
    community/tourist-added place (see CustomPlaceService)."""
    all_places = await svc.place_repository.list_all()
    q = query.strip().lower()
    matches = [p for p in all_places if not q or q in p.name.lower()][:20]
    return [
        SearchPlaceOut(
            place_id=p.id or "", name=p.name, category=p.category,
            latitude=p.coordinates.latitude, longitude=p.coordinates.longitude,
            estimated_cost=p.estimated_cost,
        )
        for p in matches
    ]


@router.post("/{trip_id}/places", response_model=ItineraryItemOut)
async def add_place(
    trip_id: str, body: AddPlaceIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> ItineraryItemOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        place = await svc.add_place(
            trip, body.place_id, body.name, body.latitude, body.longitude,
            body.category, body.note, body.estimated_cost,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await svc.db.commit()
    return _place_out(place)


@router.delete("/{trip_id}/places/{trip_place_id}")
async def remove_place(
    trip_id: str, trip_place_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> dict:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        await svc.remove_place(trip, uuid.UUID(trip_place_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await svc.db.commit()
    return {"status": "ok"}


@router.put("/{trip_id}/reorder", response_model=TripOut)
async def reorder_places(
    trip_id: str, body: ReorderIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        await svc.reorder_places(trip, body.trip_place_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await svc.db.commit()
    trip = await _get_owned_trip(trip_id, user, svc)
    return _trip_out(trip)


@router.post("/{trip_id}/rate")
async def rate_trip(
    trip_id: str, body: RateTripIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> dict:
    trip = await _get_owned_trip(trip_id, user, svc)
    await svc.rate_draft(trip, body.rating, body.feedback)
    await svc.db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Confirm — hands off to layer3 for the live session, once it's confirmed.
# ---------------------------------------------------------------------------
@router.post("/{trip_id}/confirm", response_model=TripOut)
async def confirm_trip(
    trip_id: str, body: ConfirmTripIn, request: Request,
    user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service),
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        trip = await svc.confirm_trip(
            trip, body.notifications_enabled, body.voice_guide_enabled, body.start_now,
            body.scheduled_start_at, body.accommodation_place_id, body.accommodation_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Hand off to the real layer3 session orchestrator for everything
    # live-trip related (geofence arrival, silence filter, wallet, SOS,
    # ask engine) — mounted at /l3 in main.py. Best-effort: if layer3
    # isn't available in this deployment, the trip still confirms; the
    # Flutter app just won't get live narration/geofencing for it.
    orch = getattr(request.app.state, "layer3", None)
    if orch is not None and trip.status == "active":
        profile = await svc.profile_repository.get_by_id(trip.profile_id)
        queue = [
            {"place_id": p.place_id, "role": p.role, "priority": p.order_index}
            for p in sorted(trip.places, key=lambda x: x.order_index)
        ]
        result = orch.start_session(
            profile_id=trip.profile_id,
            profile=None,
            itinerary=None,
            queue=queue,
            session_id=str(trip.id),
            device_id=None,
            language=(profile.companion_language.value if profile else None),
            voice=None,
            group_session_id=None,
            wallet_remaining=int(trip.budget_remaining),
        )
        trip.layer3_session_id = result.get("session_id", str(trip.id))
        supervisor = getattr(request.app.state, "layer4", None)
        if supervisor is not None:
            supervisor.start(trip.layer3_session_id)

    await svc.db.commit()
    trip = await _get_owned_trip(trip_id, user, svc)
    return _trip_out(trip)


# ---------------------------------------------------------------------------
# Live trip
# ---------------------------------------------------------------------------
@router.post("/{trip_id}/arrive", response_model=ItineraryItemOut)
async def arrive(
    trip_id: str, body: ArriveIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> ItineraryItemOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        place = await svc.arrive(trip, uuid.UUID(body.trip_place_id), body.listened_to_guide)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    await svc.db.commit()
    return _place_out(place)


@router.post("/{trip_id}/checkout")
async def checkout(
    trip_id: str, body: CheckoutIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> dict:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        place, trip, suggest_rest = await svc.checkout(
            trip, uuid.UUID(body.trip_place_id), body.amount_spent, body.energy_after, body.rating, body.experience_note,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))

    pending = [p for p in trip.places if p.status == "pending"]
    remaining_cost = sum(p.estimated_cost for p in pending)
    budget_ok = remaining_cost <= trip.budget_remaining

    await svc.db.commit()
    return {
        "status": "ok",
        "budget_remaining": trip.budget_remaining,
        "remaining_itinerary_cost": remaining_cost,
        "budget_covers_rest_of_trip": budget_ok,
        "suggest_rest_stop": suggest_rest,
    }


@router.post("/{trip_id}/skip", response_model=ItineraryItemOut)
async def skip_place(
    trip_id: str, body: SkipIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> ItineraryItemOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    try:
        place = await svc.skip_place(trip, uuid.UUID(body.trip_place_id), body.reason)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    await svc.db.commit()
    return _place_out(place)


@router.post("/{trip_id}/budget/top-up", response_model=TripOut)
async def top_up_budget(
    trip_id: str, body: TopUpBudgetIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    await svc.top_up_budget(trip, body.additional_amount)
    await svc.db.commit()
    trip = await _get_owned_trip(trip_id, user, svc)
    return _trip_out(trip)


@router.post("/{trip_id}/pause", response_model=TripOut)
async def pause_trip(
    trip_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    trip = await svc.pause_trip(trip)
    await svc.db.commit()
    return _trip_out(trip)


@router.post("/{trip_id}/resume", response_model=TripOut)
async def resume_trip(
    trip_id: str, body: ResumeDecisionIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    """`upgrade=true` means: regenerate the remaining itinerary against
    the tourist's current budget/energy/position (a fresh HiveEngine
    call, pinning whatever's already been visited as excluded); `false`
    means: keep the original list and just carry on from where they left
    off. The Flutter app decides which to offer by comparing the
    resume position against `trip.geofence_radius_km` around
    `origin_latitude/longitude` itself (no extra backend call needed for
    that distance check) and only sends upgrade=true if the tourist
    actually picked that option."""
    trip = await _get_owned_trip(trip_id, user, svc)
    outside_geofence = body.latitude is not None and body.longitude is not None

    if body.upgrade and body.latitude is not None and body.longitude is not None:
        profile = await svc.profile_repository.get_by_id(trip.profile_id)
        if profile is None:
            raise HTTPException(404, "Tourist profile no longer exists")
        visited_ids = [p.place_id for p in trip.places if p.status in ("visited", "skipped")]
        from dataclasses import replace as _replace
        upgraded_profile = _replace(profile, budget=trip.budget_remaining, return_visitor_exclusions=visited_ids)
        queue = await svc.hive_engine.build_recommendation_queue(
            upgraded_profile, __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            start_latitude=body.latitude, start_longitude=body.longitude,
        )
        # Replace only the still-pending slots; visited/skipped history stays.
        for p in list(trip.places):
            if p.status == "pending":
                await svc.db.delete(p)
        await svc.db.flush()
        next_index = max([p.order_index for p in trip.places], default=-1) + 1
        for offset, item in enumerate(queue.items):
            # BUG FIX (6th audit response, Oct 2026): this upgrade/
            # regenerate path omitted latitude/longitude entirely, unlike
            # TripsService.generate_trip's otherwise-identical loop (see
            # service.py) which looks the place up and sets them from
            # place.coordinates -- so every TripPlace row created by a
            # resume-and-upgrade had NULL lat/long, breaking the map and
            # arrival geofencing for the rest of that trip. Same lookup
            # here.
            place = await svc.place_repository.get_by_id(item.place_id)
            svc.db.add(TripPlace(
                trip_id=trip.id, place_id=item.place_id, place_name=item.place_name,
                role=item.role.value if hasattr(item.role, "value") else str(item.role),
                order_index=next_index + offset, scheduled_time=item.scheduled_time,
                travel_mode=item.travel_mode.value if hasattr(item.travel_mode, "value") else str(item.travel_mode),
                travel_time_minutes=item.travel_time_minutes, estimated_cost=item.estimated_cost,
                reason_selected=item.reason_selected,
                latitude=place.coordinates.latitude if place else None,
                longitude=place.coordinates.longitude if place else None,
            ))
        trip.geofence_radius_km = queue.geofence_radius_km
        await svc.db.flush()

    trip = await svc.resume_trip(trip, outside_geofence, body.upgrade)
    await svc.db.commit()
    trip = await _get_owned_trip(trip_id, user, svc)
    return _trip_out(trip)


@router.post("/{trip_id}/exit", response_model=TripOut)
async def exit_trip(
    trip_id: str, body: ExitTripIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    trip = await svc.exit_trip(trip, body.reason)
    await svc.db.commit()
    return _trip_out(trip)


@router.post("/{trip_id}/complete", response_model=TripOut)
async def complete_trip(
    trip_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    trip = await svc.complete_trip(trip)
    await svc.db.commit()
    return _trip_out(trip)


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
@router.post("/{trip_id}/journal", response_model=JournalEntryOut)
async def add_journal_entry(
    trip_id: str, body: JournalEntryIn, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> JournalEntryOut:
    trip = await _get_owned_trip(trip_id, user, svc)
    trip_place_id = uuid.UUID(body.trip_place_id) if body.trip_place_id else None
    try:
        entry = await svc.add_journal_entry(trip, trip_place_id, body.media_type, body.media_url, body.caption)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    await svc.db.commit()
    return JournalEntryOut(
        id=str(entry.id), trip_place_id=str(entry.trip_place_id) if entry.trip_place_id else None,
        media_type=entry.media_type, media_url=entry.media_url, caption=entry.caption, created_at=entry.created_at,
    )


@router.get("/{trip_id}/journal", response_model=JournalTimelineOut)
async def journal_timeline(
    trip_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> JournalTimelineOut:
    """A "creative timeline" here means: every journal entry the tourist
    captured, in the order they captured it, grouped implicitly by
    being interleaved with which place was current — genuinely
    assembling a produced photo/video montage (transitions, music,
    auto-editing) is outside what this backend can honestly do without
    a media-processing pipeline that doesn't exist yet, so the Flutter
    app renders this ordered list as a scrollable day timeline instead.
    See trips/README_TRIPS.md."""
    trip = await _get_owned_trip(trip_id, user, svc)
    entries = await svc.journal_timeline(trip)
    return JournalTimelineOut(
        trip_id=trip_id,
        entries=[
            JournalEntryOut(
                id=str(e.id), trip_place_id=str(e.trip_place_id) if e.trip_place_id else None,
                media_type=e.media_type, media_url=e.media_url, caption=e.caption, created_at=e.created_at,
            )
            for e in entries
        ],
        places_visited=[p.place_name for p in trip.places if p.status == "visited"],
    )


@router.post("/{trip_id}/story-video")
async def make_story_video(
    trip_id: str, request: Request, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> dict:
    """Builds a shareable vertical video from the day's journal photos."""
    import asyncio

    from media.routes import MEDIA_DIR, path_for_url, public_base
    from media.story_video import build_story_video

    trip = await _get_owned_trip(trip_id, user, svc)
    entries = await svc.journal_timeline(trip)
    items = []
    for e in entries:
        if e.media_type != "photo":
            continue
        path = path_for_url(e.media_url)
        if path is None:
            continue
        stamp = e.created_at.astimezone(_IST).strftime("%I:%M %p").lstrip("0") if e.created_at else ""
        items.append((path, e.caption, stamp))
    if not items:
        raise HTTPException(422, "Add at least one photo to your journal first, then make your story.")
    when = (trip.scheduled_start_at or trip.created_at)
    subtitle = when.astimezone(_IST).strftime("%A, %d %B %Y") if when else ""
    places = [p.place_name for p in trip.places if p.status == "visited"] or [p.place_name for p in trip.places][:6]
    try:
        out = await asyncio.get_running_loop().run_in_executor(
            None, lambda: build_story_video("Your day in Mangaluru", subtitle, places, items, MEDIA_DIR)
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Couldn't render the video: {exc.__class__.__name__}. Is imageio-ffmpeg installed?")
    return {"url": f"{public_base(request)}/media/files/{out.name}", "photos": len(items)}


# ---------------------------------------------------------------------------
# Chunk 4 — My Trips / Journey Story
# ---------------------------------------------------------------------------
def _summary_out(t: Trip) -> TripSummaryOut:
    next_place = next((p for p in t.places if p.status == "pending"), None)
    visited = [p for p in t.places if p.status == "visited"]
    cover = visited[0].place_name if visited else (t.places[0].place_name if t.places else None)
    return TripSummaryOut(
        trip_id=str(t.id), status=t.status, place_count=len(t.places), visited_count=len(visited),
        next_place_name=next_place.place_name if next_place else None,
        next_place_id=str(next_place.id) if next_place else None,
        cover_place_name=cover, started_at=t.started_at, ended_at=t.ended_at,
        scheduled_start_at=t.scheduled_start_at, overall_rating=t.overall_rating,
        budget_total=t.budget_total, budget_remaining=t.budget_remaining,
    )


@router.get("", response_model=MyTripsOut)
async def my_trips(user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)) -> MyTripsOut:
    """"Your journeys" — the real, already-stored Trip rows, split into
    upcoming (still ahead of or in the middle of) vs completed. The
    "biggest card" / most-important-trip ordering is left to the
    Flutter side (upcoming[0] is the most recently created/active one),
    since deciding visual weight is a UI concern, not a data one."""
    trips = await svc.list_my_trips(user.id)
    upcoming = [t for t in trips if t.status in ("draft", "scheduled", "active", "paused")]
    completed = [t for t in trips if t.status in ("completed", "ended_early")]
    # Active/paused trips are the most important — surface them first.
    upcoming.sort(key=lambda t: {"active": 0, "paused": 0, "scheduled": 1, "draft": 2}.get(t.status, 3))
    return MyTripsOut(upcoming=[_summary_out(t) for t in upcoming], completed=[_summary_out(t) for t in completed])


@router.get("/{trip_id}/story", response_model=TripStoryOut)
async def trip_story(
    trip_id: str, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> TripStoryOut:
    """Every completed trip becomes a story — built entirely from data
    already on the Trip/TripPlace/JournalEntry rows (distance via
    haversine between visited stops, duration from started/ended
    timestamps, photo/video counts, highlights from the tourist's own
    ratings). No narrative text is generated or invented anywhere."""
    trip = await _get_owned_trip(trip_id, user, svc)
    story = await svc.trip_story(trip)
    return TripStoryOut(
        trip_id=trip_id, title=story["title"], place_count=story["place_count"],
        visited_place_names=story["visited_place_names"], distance_km=story["distance_km"],
        duration_minutes=story["duration_minutes"], photo_count=story["photo_count"],
        video_count=story["video_count"], highlights=story["highlights"],
        cover_place_name=story["cover_place_name"],
    )


@router.get("/{trip_id}/visits")
async def trip_visits(
    trip_id: str, request: Request, user: User = Depends(get_current_user), svc: TripsService = Depends(get_trips_service)
) -> dict:
    """Trip-owned replacement for the old device_id-keyed
    `/l3/visits/{device_id}` (5th audit response, Oct 2026): that
    endpoint had no real ownership model -- device_id isn't linked to
    a user anywhere in the schema, so it only ever checked that
    *someone* was signed in, not that the caller owned the data. This
    endpoint uses the one real, already-verified ownership check every
    other trip route uses (`_get_owned_trip`), then looks up visits by
    `Trip.layer3_session_id` -- the same real Layer 3 session link
    `/trips/{id}/confirm` already establishes -- instead of trusting a
    client-supplied device_id. The old device_id endpoint is left in
    place (still signed-in-required) for any caller that genuinely only
    has a device_id and no trip context; this is the one to use when a
    trip_id is available, which is the normal product flow."""
    trip = await _get_owned_trip(trip_id, user, svc)
    if not trip.layer3_session_id:
        return {"trip_id": trip_id, "place_ids": [], "visits": []}
    orch = getattr(request.app.state, "layer3", None)
    if orch is None:
        raise HTTPException(503, "Layer 3 session authority is unavailable")
    result = orch.visits_for_session(trip.layer3_session_id)
    return {"trip_id": trip_id, **result}
