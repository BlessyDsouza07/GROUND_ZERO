from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from layer0.api.dependencies import get_place_repository
from layer0.domain.repositories import PlaceRepository
from layer1.api.dependencies import get_db_session, get_profile_repository, get_survey_service
from layer1.api.schemas import (
    AnswerIn,
    MarkVisitedIn,
    MarkVisitedOut,
    StartSurveyIn,
    SurveyStateOut,
    TouristProfileOut,
    VisitedPlaceOut,
)
from layer1.application.survey_service import InvalidSurveyAnswer, SurveyService, SurveySessionNotOwned, SurveyStep
from layer1.domain.repositories import TouristProfileRepository
from shared.ownership import ProfileNotOwned, enforce_profile_ownership

router = APIRouter(prefix="/survey", tags=["soul-survey"])

# SECURITY NOTE (audit response, Oct 2026): this is the pre-chunk-4
# "Layer 1" survey API, superseded for the signed-in Flutter product by
# /trips/survey/* (trips/routes.py), which additionally records who
# finalized each profile. It stayed mounted (not removed) because
# layer1/main.py also runs this exact router standalone, outside this
# app, for layer1's own test/dev use — removing it here would either
# break that or require forking the router. Instead, every endpoint
# below now requires a signed-in user, and the two that read or write
# profile-specific data (mark/get visited places) additionally enforce
# the same profile-ownership check /trips/survey/finalize and
# /trips/generate use (shared.ownership) — closing the "anonymous
# access" and "any user can act on any profile_id" gaps an audit
# flagged, without rewriting this module's survey-session storage.
#
# SECURITY FIX (final-release-hardening pass, Oct 2026): this router
# shares the exact same SurveyService/session store as /trips/survey/*
# (both get it from layer1.api.dependencies.get_session_store), so the
# session-ownership binding added there (SurveySessionNotOwned) applies
# here automatically — this router just needed to start passing user.id
# into start_session/get_session/answer/finalize below, same as
# trips/routes.py does, to actually enforce it rather than silently
# allow any other signed-in caller through.


def _state_out(session, service: SurveyService) -> SurveyStateOut:
    return SurveyStateOut(
        session_id=session.id,
        current_step=session.current_step.value,
        progress_fraction=session.progress_fraction,
        is_complete=session.current_step == SurveyStep.COMPLETE,
    )


@router.post("/start", response_model=SurveyStateOut)
async def start_survey(
    payload: StartSurveyIn,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service),
) -> SurveyStateOut:
    session = await service.start_session(
        device_id=payload.device_id, join_group_session_id=payload.join_group_session_id,
        user_id=str(user.id),
    )
    return _state_out(session, service)


@router.get("/{session_id}", response_model=SurveyStateOut)
async def get_survey_state(
    session_id: str,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service),
) -> SurveyStateOut:
    try:
        session = await service.get_session(session_id, requesting_user_id=str(user.id))
    except SurveySessionNotOwned as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _state_out(session, service)


@router.post("/{session_id}/answer", response_model=SurveyStateOut)
async def answer_question(
    session_id: str,
    payload: AnswerIn,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service),
) -> SurveyStateOut:
    try:
        session = await service.answer(session_id, payload.answer, requesting_user_id=str(user.id))
    except SurveySessionNotOwned as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidSurveyAnswer as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _state_out(session, service)


def _profile_out(profile) -> TouristProfileOut:
    return TouristProfileOut(
        id=profile.id or "",
        purpose=profile.purpose.value,
        energy_band=profile.energy_band.value,
        crowd_tolerance=profile.crowd_tolerance.value,
        budget=profile.budget,
        dietary_flags=[f.value for f in profile.dietary_flags],
        group_config=profile.group_config.value,
        group_session_id=profile.group_session_id,
        curiosity_text=profile.curiosity_text,
        curiosity_vector=profile.curiosity_vector.weights,
        trip_duration_hours=profile.trip_duration_hours.value,
        multi_day_count=profile.multi_day_count,
        start_time_preference=profile.start_time_preference.value,
        accessibility_flags=[f.value for f in profile.accessibility_flags],
        companion_language=profile.companion_language.value,
        voice_personality=profile.voice_personality.value,
        return_visitor_exclusions=profile.return_visitor_exclusions,
    )


@router.post("/{session_id}/finalize", response_model=TouristProfileOut)
async def finalize_survey(
    session_id: str,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service),
) -> TouristProfileOut:
    try:
        profile = await service.finalize(session_id, requesting_user_id=str(user.id))
    except SurveySessionNotOwned as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidSurveyAnswer as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _profile_out(profile)


@router.get("/group/{group_session_id}/members", response_model=list[TouristProfileOut])
async def list_group_members(
    group_session_id: str,
    user: User = Depends(get_current_user),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
) -> list[TouristProfileOut]:
    """Blueprint 4.7: other group members join by entering the shared code.
    This lets the app show 'Jia and Dion have joined' before everyone's
    finished their own survey. Group membership is its own authorization
    rule (anyone holding the shared code is meant to see this, by
    design) — the group code itself is the credential, same as before;
    this now just also requires being signed in at all."""
    profiles = await profile_repo.list_by_group_session(group_session_id)
    return [_profile_out(p) for p in profiles]


async def _check_profile_ownership_or_403(db: AsyncSession, profile_id: str, user_id: uuid.UUID) -> None:
    try:
        await enforce_profile_ownership(db, profile_id, user_id)
    except ProfileNotOwned as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/profile/{profile_id}/visited", response_model=MarkVisitedOut)
async def mark_places_visited(
    profile_id: str,
    payload: MarkVisitedIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
) -> MarkVisitedOut:
    """The write side of Return Visitor Check (blueprint 4.5). An
    architectural audit found `get_visited_place_ids` had no
    corresponding write path anywhere — the app should call this once a
    tourist has actually been somewhere on their itinerary, so a future
    trip on the same device can offer to skip it. Now requires a signed-
    in user who owns this profile (see shared/ownership.py) — this
    writes personal travel-history data, so it must not be callable
    against an arbitrary profile_id."""
    await _check_profile_ownership_or_403(db, profile_id, user.id)
    try:
        visited = await profile_repo.mark_visited(profile_id, payload.place_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MarkVisitedOut(profile_id=profile_id, visited_place_ids=visited)


@router.get("/profile/{profile_id}/visited", response_model=list[VisitedPlaceOut])
async def get_visited_places(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
    place_repo: PlaceRepository = Depends(get_place_repository),
) -> list[VisitedPlaceOut]:
    """The read side of Return Visitor Check (blueprint 4.5), previously
    missing: `return_visitor_exclusions` silently blocked previously-
    visited places from ever being recommended again, with no way for
    the tourist to see that list and choose to go back to one anyway.
    A place they genuinely want to revisit isn't a bug to route around —
    it's a `pinned_place_ids` entry on their NEXT /hive/recommendations
    call, which bypasses hard filters (including this exclusion) exactly
    the way a tourist-added place already does. Now requires a signed-
    in user who owns this profile — this is someone's travel history,
    not public data."""
    await _check_profile_ownership_or_403(db, profile_id, user.id)
    place_ids = await profile_repo.get_visited_place_ids(profile_id)
    out: list[VisitedPlaceOut] = []
    for pid in place_ids:
        place = await place_repo.get_by_id(pid)
        if place is None:
            continue
        out.append(VisitedPlaceOut(place_id=pid, name=place.name, category=place.category))
    return out
