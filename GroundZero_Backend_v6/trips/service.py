"""Orchestration for the New Trip flow.

This module is deliberately thin. It does not reimplement anything that
already works elsewhere in the codebase — it drives the real layer1
SurveyService (question logic), the real layer2 HiveEngine (itinerary
generation), and the real layer3 Orchestrator (live-trip mechanics), and
adds only the pieces that don't already exist anywhere: a per-user Trip
record the Flutter app can read as one coherent object, journal storage,
draft-itinerary editing, and a full behavioral-event log.

Question order vs Carol's spec
-------------------------------
layer1.SurveyService asks nine-ish questions in ITS OWN fixed order
(Purpose, Energy, Crowd, Budget, Dietary, Group, Accessibility, Curiosity
text, Duration, Start time, Return-visitor, Voice personality, Group
session). Carol's chunk-2 spec asks for a different nine, in a different
order, and explicitly does NOT want a "purpose", "group size" or "voice
personality" question at all.

Rather than fork the survey engine, _AUTO_FILLED below lists every step
Carol didn't ask for. Whenever the live session lands on one of those,
`_auto_advance` answers it with a sensible default (or with whatever the
free-text opening answer already inferred — see profile_extractor.py)
and moves straight on, silently. From the Flutter app's point of view the
question sequence is exactly:

  1. opening_prompt      (free text — "what do you want to explore")
  2. q2_energy            (slider  0-100 -> EnergyBand)
  3. q3_crowd_tolerance   (slider  0-100 -> CrowdTolerance)
  4. q4_budget            (number stepper, INR)
  5. q5_dietary           (choice list; allergy detail carried separately)
  6. accessibility        (yes/no + detail)
  7. q8_trip_duration     ("how long are you in Mangaluru")
  8. q9_start_time        ("start now or schedule later")
  9. return_visitor_check ("have you visited before")

which is exactly her list. Everything else (purpose, group config, voice
personality, group session setup) is filled in automatically.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from layer0.application.custom_place_service import CustomPlaceService
from layer0.domain.repositories import PlaceRepository
from layer1.application.survey_service import InvalidSurveyAnswer, SurveyService, SurveyStep
from layer1.domain.entities import (
    CrowdTolerance,
    EnergyBand,
    GroupConfig,
    Purpose,
    TouristProfile,
    VoicePersonality,
)
from layer1.domain.repositories import TouristProfileRepository
from layer2.domain.entities import SlotRole

from shared.ownership import ProfileNotOwned, enforce_profile_ownership
from trips.models import JournalEntry, Trip, TripEvent, TripPlace

if TYPE_CHECKING:
    # Deferred: layer2.application.hive_engine transitively imports the
    # third-party `opening-hours-py` package, which fails to build in some
    # environments (a native-extension setup.py bug in that package, not
    # ours — see trips/README_TRIPS.md). This annotation-only import (with
    # `from __future__ import annotations` at the top of this file) keeps
    # trips.service importable even when that package can't build, while
    # the real HiveEngine object still works fine wherever it's actually
    # constructed and passed in (trips/dependencies.py).
    from layer2.application.hive_engine import HiveEngine

# Steps Carol did not ask for. Value is the default answer used when the
# opening free-text sentence didn't already infer one (see
# survey_service._apply_opening_prompt_inference — those inferred steps
# are skipped automatically by the survey machine itself and never reach
# this dict).
_AUTO_FILLED: dict[SurveyStep, Any] = {
    SurveyStep.Q1_PURPOSE: Purpose.UNDECIDED.value,
    SurveyStep.Q6_GROUP_CONFIG: GroupConfig.SOLO.value,
    SurveyStep.VOICE_PERSONALITY: VoicePersonality.WARM_LOCAL_FRIEND.value,
    SurveyStep.GROUP_SESSION_SETUP: True,
}

# The literal UI question this step corresponds to, for the frontend to
# key its wizard screens off of. None once the survey is COMPLETE.
_UI_STEP_NAME = {
    SurveyStep.OPENING_PROMPT: "opening_prompt",
    SurveyStep.Q2_ENERGY: "q2_energy",
    SurveyStep.Q3_CROWD_TOLERANCE: "q3_crowd_tolerance",
    SurveyStep.Q4_BUDGET: "q4_budget",
    SurveyStep.Q5_DIETARY: "q5_dietary",
    SurveyStep.ACCESSIBILITY: "accessibility",
    SurveyStep.Q8_TRIP_DURATION: "q8_trip_duration",
    SurveyStep.RETURN_VISITOR_CHECK: "return_visitor_check",
    SurveyStep.Q9_START_TIME: "q9_start_time",
}


def energy_slider_to_band(value: float) -> str:
    """0-100 slider -> EnergyBand. Thresholds are an even three-way split;
    nothing in the blueprint docs specifies otherwise."""
    if value < 34:
        return EnergyBand.LOW.value
    if value < 67:
        return EnergyBand.MODERATE.value
    return EnergyBand.HIGH.value


def crowd_slider_to_tolerance(value: float) -> str:
    """0-100 slider ("how okay are you with crowds") -> the four-bucket
    CrowdTolerance enum, low end = avoids crowds entirely, high end =
    loves them."""
    if value < 26:
        return CrowdTolerance.AVOID_ENTIRELY.value
    if value < 51:
        return CrowdTolerance.PREFER_QUIET.value
    if value < 76:
        return CrowdTolerance.FINE.value
    return CrowdTolerance.LOVE_THEM.value


class TripsService:
    def __init__(
        self,
        db: AsyncSession,
        survey_service: SurveyService,
        profile_repository: TouristProfileRepository,
        hive_engine: HiveEngine,
        place_repository: PlaceRepository,
        custom_place_service: CustomPlaceService,
    ):
        self.db = db
        self.survey_service = survey_service
        self.profile_repository = profile_repository
        self.hive_engine = hive_engine
        self.place_repository = place_repository
        self.custom_place_service = custom_place_service

    # -- behavioral logging --------------------------------------------------
    async def log_event(
        self,
        event_type: str,
        *,
        trip_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        profile_id: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Records everything, honestly: this table is not yet read by any
        training pipeline in this repo (there isn't one). It exists so
        that when one is built, the data it needs has been collected
        since day one instead of starting from nothing."""
        event = TripEvent(
            trip_id=trip_id, user_id=user_id, profile_id=profile_id,
            event_type=event_type, payload=payload or {},
        )
        self.db.add(event)
        await self.db.flush()

    # -- survey ---------------------------------------------------------------
    # SECURITY FIX (final-release-hardening pass, Oct 2026): every method
    # below now threads user_id through to survey_service, which binds
    # the session to its creator and rejects any other authenticated
    # caller — see SurveySessionNotOwned's docstring. trips/routes.py
    # passes the real authenticated user.id into all four.
    async def start_survey(self, user_id: uuid.UUID, device_id: Optional[str] = None) -> tuple[str, str]:
        session = await self.survey_service.start_session(device_id=device_id, user_id=str(user_id))
        return session.id, _UI_STEP_NAME[session.current_step]

    async def _auto_advance(self, session_id: str, user_id: uuid.UUID):
        session = await self.survey_service.get_session(session_id, requesting_user_id=str(user_id))
        while session.current_step in _AUTO_FILLED and session.current_step.value not in session.inferred_steps:
            session = await self.survey_service.answer(session_id, _AUTO_FILLED[session.current_step], requesting_user_id=str(user_id))
        return session

    async def answer_survey(self, session_id: str, step: str, value: Any, user_id: uuid.UUID) -> tuple[Optional[str], float, bool]:
        session = await self.survey_service.get_session(session_id, requesting_user_id=str(user_id))
        if session.current_step.value != step:
            raise InvalidSurveyAnswer(
                f"This survey is currently on '{session.current_step.value}', not '{step}' — "
                "the two are probably out of sync (e.g. a duplicate/late submit)."
            )
        session = await self.survey_service.answer(session_id, value, requesting_user_id=str(user_id))
        session = await self._auto_advance(session_id, user_id)
        done = session.current_step == SurveyStep.COMPLETE
        next_ui_step = None if done else _UI_STEP_NAME.get(session.current_step)
        return next_ui_step, session.progress_fraction, done

    async def get_survey_state(self, session_id: str, user_id: uuid.UUID) -> tuple[Optional[str], float, bool]:
        session = await self._auto_advance(session_id, user_id)
        done = session.current_step == SurveyStep.COMPLETE
        next_ui_step = None if done else _UI_STEP_NAME.get(session.current_step)
        return next_ui_step, session.progress_fraction, done

    async def finalize_survey(self, session_id: str, user_id: uuid.UUID) -> TouristProfile:
        profile = await self.survey_service.finalize(session_id, requesting_user_id=str(user_id))
        await self.log_event(
            "survey_completed", user_id=user_id, profile_id=profile.id,
            payload={
                "purpose": profile.purpose.value,
                "energy_band": profile.energy_band.value,
                "crowd_tolerance": profile.crowd_tolerance.value,
                "budget": profile.budget,
                "trip_duration_hours": profile.trip_duration_hours.value,
                "curiosity_text": profile.curiosity_text,
            },
        )
        return profile

    # -- itinerary generation + the draft trip -------------------------------
    async def generate_trip(
        self,
        user_id: uuid.UUID,
        profile_id: str,
        start_latitude: float,
        start_longitude: float,
        start_time: Optional[datetime],
        pinned_place_ids: list[str],
    ) -> Trip:
        profile = await self.profile_repository.get_by_id(profile_id)
        if profile is None:
            raise ValueError(f"Tourist profile {profile_id} not found")
        await self._enforce_profile_ownership(profile_id, user_id)

        effective_start = start_time or datetime.now(timezone.utc)
        queue = await self.hive_engine.build_recommendation_queue(
            profile, effective_start, pinned_place_ids,
            start_latitude=start_latitude, start_longitude=start_longitude,
        )

        trip = Trip(
            user_id=user_id,
            profile_id=profile_id,
            status="draft",
            budget_total=profile.budget,
            budget_remaining=profile.budget - queue.total_estimated_cost,
            energy_band=profile.energy_band.value,
            origin_latitude=start_latitude,
            origin_longitude=start_longitude,
            geofence_radius_km=queue.geofence_radius_km,
            scheduled_start_at=effective_start,
        )
        self.db.add(trip)
        await self.db.flush()

        for index, item in enumerate(queue.items):
            place = await self.place_repository.get_by_id(item.place_id)
            self.db.add(TripPlace(
                trip_id=trip.id,
                place_id=item.place_id,
                place_name=item.place_name,
                role=item.role.value if hasattr(item.role, "value") else str(item.role),
                order_index=index,
                latitude=place.coordinates.latitude if place else None,
                longitude=place.coordinates.longitude if place else None,
                scheduled_time=item.scheduled_time,
                travel_mode=item.travel_mode.value if hasattr(item.travel_mode, "value") else str(item.travel_mode),
                travel_time_minutes=item.travel_time_minutes,
                estimated_cost=item.estimated_cost,
                reason_selected=item.reason_selected,
                is_tourist_added=(item.place_id in set(pinned_place_ids)),
            ))
        await self.db.flush()

        await self.log_event(
            "itinerary_generated", trip_id=trip.id, user_id=user_id, profile_id=profile_id,
            payload={
                "slots_requested": queue.slots_requested, "slots_filled": queue.slots_filled,
                "slots_dropped_closed": queue.slots_dropped_closed,
                "geofence_radius_km": queue.geofence_radius_km,
                "total_estimated_cost": queue.total_estimated_cost,
            },
        )
        return await self.get_trip(trip.id, user_id)

    async def _enforce_profile_ownership(self, profile_id: str, user_id: uuid.UUID) -> None:
        """Delegates to `shared.ownership.enforce_profile_ownership` (see
        that module's docstring for the full reasoning) — factored out
        so `layer1/api/routes.py`'s legacy survey/visited-places
        endpoints enforce the identical rule instead of drifting.
        Translates to `PermissionError` so `trips/routes.py`'s existing
        `except PermissionError -> 403` mapping stays unchanged."""
        try:
            await enforce_profile_ownership(self.db, profile_id, user_id)
        except ProfileNotOwned as exc:
            raise PermissionError(str(exc)) from exc

    async def get_trip(self, trip_id: uuid.UUID, user_id: uuid.UUID) -> Trip:
        # selectinload (not a manual re-query + assignment to trip.places)
        # so the ORM's own relationship loader populates the collection —
        # assigning a freshly-queried list directly to a relationship
        # attribute makes SQLAlchemy lazy-load the OLD collection first
        # (to diff against it), which under asyncio raises MissingGreenlet
        # unless that lazy-load is itself awaited, which a plain
        # attribute assignment never does.
        result = await self.db.execute(
            select(Trip).options(selectinload(Trip.places)).where(Trip.id == trip_id)
        )
        trip = result.scalar_one_or_none()
        if trip is None or trip.user_id != user_id:
            raise LookupError("Trip not found")
        return trip

    async def add_place(
        self, trip: Trip,
        place_id: Optional[str], name: Optional[str], latitude: Optional[float], longitude: Optional[float],
        category: Optional[str], note: Optional[str], estimated_cost: float,
    ) -> TripPlace:
        if trip.status != "draft":
            raise ValueError("Places can only be added before the trip is confirmed")

        if place_id:
            place = await self.place_repository.get_by_id(place_id)
            if place is None:
                raise ValueError(f"Place {place_id} not found")
            was_new = False
        else:
            if not (name and latitude is not None and longitude is not None):
                raise ValueError("Provide either place_id, or name+latitude+longitude for a new place")
            result = await self.custom_place_service.add_or_find(
                name=name, lat=latitude, lon=longitude, category=category, note=note,
                estimated_cost=estimated_cost,
            )
            place = result.place
            was_new = result.was_newly_created

        next_index = max([p.order_index for p in trip.places], default=-1) + 1
        trip_place = TripPlace(
            trip_id=trip.id, place_id=place.id or "", place_name=place.name,
            role=SlotRole.TOURIST_PICK.value, order_index=next_index,
            latitude=place.coordinates.latitude, longitude=place.coordinates.longitude,
            estimated_cost=place.estimated_cost if place_id else estimated_cost,
            is_tourist_added=True,
        )
        self.db.add(trip_place)
        await self.db.flush()

        await self.log_event(
            "place_added", trip_id=trip.id, user_id=trip.user_id,
            payload={"place_id": trip_place.place_id, "name": trip_place.place_name, "newly_created": was_new},
        )
        return trip_place

    async def remove_place(self, trip: Trip, trip_place_id: uuid.UUID) -> None:
        if trip.status != "draft":
            raise ValueError("Places can only be removed before the trip is confirmed")
        target = next((p for p in trip.places if p.id == trip_place_id), None)
        if target is None:
            raise LookupError("Place not in this trip")
        await self.db.delete(target)
        await self.db.flush()
        await self.log_event(
            "place_removed", trip_id=trip.id, user_id=trip.user_id,
            payload={"place_id": target.place_id, "name": target.place_name},
        )

    async def reorder_places(self, trip: Trip, ordered_ids: list[str]) -> None:
        if trip.status != "draft":
            raise ValueError("Places can only be reordered before the trip is confirmed")
        by_id = {str(p.id): p for p in trip.places}
        if set(by_id.keys()) != set(ordered_ids):
            raise ValueError("The reordered list must contain exactly the trip's current places")
        for index, pid in enumerate(ordered_ids):
            by_id[pid].order_index = index
        await self.db.flush()
        await self.log_event("places_reordered", trip_id=trip.id, user_id=trip.user_id, payload={"order": ordered_ids})

    async def rate_draft(self, trip: Trip, rating: int, feedback: Optional[str]) -> None:
        trip.overall_rating = rating
        trip.overall_feedback = feedback
        await self.db.flush()
        await self.log_event(
            "itinerary_rated", trip_id=trip.id, user_id=trip.user_id,
            payload={"rating": rating, "feedback": feedback, "stage": trip.status},
        )

    # -- confirm + live trip ---------------------------------------------------
    async def confirm_trip(
        self, trip: Trip, notifications_enabled: bool, voice_guide_enabled: bool,
        start_now: bool, scheduled_start_at: Optional[datetime],
        accommodation_place_id: Optional[str], accommodation_name: Optional[str],
    ) -> Trip:
        if trip.status != "draft":
            raise ValueError("Trip is already confirmed")
        trip.notifications_enabled = notifications_enabled
        trip.voice_guide_enabled = voice_guide_enabled
        trip.accommodation_place_id = accommodation_place_id
        trip.accommodation_name = accommodation_name
        if start_now:
            trip.status = "active"
            trip.started_at = datetime.now(timezone.utc)
        else:
            trip.status = "scheduled"
            trip.scheduled_start_at = scheduled_start_at or trip.scheduled_start_at
        await self.db.flush()
        await self.log_event(
            "trip_confirmed", trip_id=trip.id, user_id=trip.user_id,
            payload={
                "notifications_enabled": notifications_enabled, "voice_guide_enabled": voice_guide_enabled,
                "start_now": start_now, "accommodation_name": accommodation_name,
            },
        )
        return trip

    async def arrive(self, trip: Trip, trip_place_id: uuid.UUID, listened_to_guide: Optional[bool]) -> TripPlace:
        target = self._require_place(trip, trip_place_id)
        target.arrived_at = datetime.now(timezone.utc)
        target.listened_to_guide = listened_to_guide
        await self.db.flush()
        await self.log_event(
            "place_arrived", trip_id=trip.id, user_id=trip.user_id,
            payload={"place_id": target.place_id, "listened_to_guide": listened_to_guide},
        )
        return target

    async def checkout(
        self, trip: Trip, trip_place_id: uuid.UUID, amount_spent: float,
        energy_after: str, rating: int, experience_note: Optional[str],
    ) -> tuple[TripPlace, Trip, bool]:
        """Records the per-place checkout (spend/energy/rating), decrements
        the remaining budget, and returns whether the tourist should be
        offered a rest stop next (low energy). Re-checking whether the
        REST of the itinerary is still affordable is the caller's job
        (routes.py) once it knows how many places are still pending —
        this method only updates the numbers it owns."""
        target = self._require_place(trip, trip_place_id)
        now = datetime.now(timezone.utc)
        target.left_at = now
        if target.arrived_at:
            target.halt_minutes = round((now - target.arrived_at).total_seconds() / 60.0, 1)
        target.amount_spent = amount_spent
        target.energy_after = energy_after
        target.rating = rating
        target.experience_note = experience_note
        target.status = "visited"

        trip.budget_remaining = max(0.0, trip.budget_remaining - amount_spent)
        trip.energy_band = energy_after
        await self.db.flush()

        suggest_rest = energy_after == "low"
        await self.log_event(
            "place_checked_out", trip_id=trip.id, user_id=trip.user_id,
            payload={
                "place_id": target.place_id, "amount_spent": amount_spent, "energy_after": energy_after,
                "rating": rating, "halt_minutes": target.halt_minutes, "budget_remaining": trip.budget_remaining,
            },
        )
        return target, trip, suggest_rest

    async def skip_place(self, trip: Trip, trip_place_id: uuid.UUID, reason: Optional[str]) -> TripPlace:
        target = self._require_place(trip, trip_place_id)
        target.status = "skipped"
        target.experience_note = reason
        await self.db.flush()
        await self.log_event(
            "place_skipped", trip_id=trip.id, user_id=trip.user_id,
            payload={"place_id": target.place_id, "reason": reason},
        )
        return target

    async def top_up_budget(self, trip: Trip, additional_amount: float) -> Trip:
        trip.budget_total += additional_amount
        trip.budget_remaining += additional_amount
        await self.db.flush()
        await self.log_event(
            "budget_topped_up", trip_id=trip.id, user_id=trip.user_id,
            payload={"additional_amount": additional_amount, "budget_remaining": trip.budget_remaining},
        )
        return trip

    async def pause_trip(self, trip: Trip) -> Trip:
        trip.status = "paused"
        await self.db.flush()
        await self.log_event("trip_paused", trip_id=trip.id, user_id=trip.user_id)
        return trip

    async def resume_trip(self, trip: Trip, outside_geofence: bool, upgrade: bool) -> Trip:
        trip.status = "active"
        await self.db.flush()
        await self.log_event(
            "trip_resumed", trip_id=trip.id, user_id=trip.user_id,
            payload={"was_outside_geofence": outside_geofence, "upgraded": upgrade},
        )
        return trip

    async def exit_trip(self, trip: Trip, reason: str) -> Trip:
        trip.status = "ended_early"
        trip.exit_reason = reason
        trip.ended_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.log_event("trip_exited", trip_id=trip.id, user_id=trip.user_id, payload={"reason": reason})
        return trip

    async def complete_trip(self, trip: Trip) -> Trip:
        trip.status = "completed"
        trip.ended_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.log_event("trip_completed", trip_id=trip.id, user_id=trip.user_id)
        return trip

    def _require_place(self, trip: Trip, trip_place_id: uuid.UUID) -> TripPlace:
        target = next((p for p in trip.places if p.id == trip_place_id), None)
        if target is None:
            raise LookupError("Place not in this trip")
        return target

    # -- journal ----------------------------------------------------------------
    async def add_journal_entry(
        self, trip: Trip, trip_place_id: Optional[uuid.UUID], media_type: str, media_url: str, caption: Optional[str],
    ) -> JournalEntry:
        # BUG FIX (6th audit response, Oct 2026): trip_place_id was never
        # checked against this trip's own places, unlike arrive/checkout/
        # skip_place which all route through _require_place. The route
        # already confirms the *trip* belongs to the caller, but nothing
        # stopped a caller from passing a trip_place_id belonging to a
        # DIFFERENT trip (anyone's) and having it linked into their own
        # journal entry -- an IDOR via foreign-key insertion. Reuse the
        # existing membership check instead of inventing a new one.
        if trip_place_id is not None:
            self._require_place(trip, trip_place_id)
        entry = JournalEntry(
            trip_id=trip.id, trip_place_id=trip_place_id, media_type=media_type, media_url=media_url, caption=caption,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.log_event(
            "journal_entry_added", trip_id=trip.id, user_id=trip.user_id,
            payload={"media_type": media_type, "trip_place_id": str(trip_place_id) if trip_place_id else None},
        )
        return entry

    async def journal_timeline(self, trip: Trip) -> list[JournalEntry]:
        result = await self.db.execute(
            select(JournalEntry).where(JournalEntry.trip_id == trip.id).order_by(JournalEntry.created_at)
        )
        return list(result.scalars().all())

    # -- Chunk 4: My Trips / Journey Story ---------------------------------
    # Everything below reads existing Trip/TripPlace/JournalEntry rows —
    # no new table, no invented numbers.
    async def list_my_trips(self, user_id: uuid.UUID) -> list[Trip]:
        result = await self.db.execute(
            select(Trip).options(selectinload(Trip.places))
            .where(Trip.user_id == user_id)
            .order_by(Trip.created_at.desc())
        )
        return list(result.scalars().all())

    async def trip_story(self, trip: Trip) -> dict:
        visited = [p for p in trip.places if p.status == "visited"]
        distance_km = _haversine_path_km(visited)
        duration_minutes = None
        if trip.started_at and trip.ended_at:
            duration_minutes = int((trip.ended_at - trip.started_at).total_seconds() // 60)
        entries = await self.journal_timeline(trip)
        photo_count = sum(1 for e in entries if e.media_type == "photo")
        video_count = sum(1 for e in entries if e.media_type == "video")
        highlights = [p.place_name for p in visited if (p.rating or 0) >= 4]
        place_count = len(trip.places)
        title = f"{place_count} place{'s' if place_count != 1 else ''} in Mangaluru"
        return {
            "place_count": place_count,
            "visited_place_names": [p.place_name for p in visited],
            "distance_km": round(distance_km, 1),
            "duration_minutes": duration_minutes,
            "photo_count": photo_count,
            "video_count": video_count,
            "highlights": highlights,
            "cover_place_name": visited[0].place_name if visited else (trip.places[0].place_name if trip.places else None),
            "title": title,
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _haversine_path_km(places: list[TripPlace]) -> float:
    pts = [(p.latitude, p.longitude) for p in places if p.latitude is not None and p.longitude is not None]
    total = 0.0
    for i in range(1, len(pts)):
        total += _haversine_km(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
    return total
