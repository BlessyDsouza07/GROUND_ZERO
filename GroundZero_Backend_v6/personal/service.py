"""Chunk 4 — Contributions + Notifications orchestration. Both are thin:
Contributions wraps layer0's existing CommunitySubmissionService (never
re-implements review/approval); Notifications is pure computation over
rows TripsService already exposes — no new state, nothing fabricated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from layer0.application.community_workflow import CommunitySubmissionService
from layer0.domain.entities import (
    AccessibilityInfo,
    BiasSignals,
    Coordinates,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.domain.repositories import PlaceRepository
from trips.models import Trip, TripPlace
from trips.service import TripsService, _haversine_km

from .models import ContributionRecord, SavedPlace
from .schemas import (
    AddMediaIn,
    AddPlaceIn,
    ContributionOut,
    LocalTipIn,
    MyContributionsOut,
    NotificationOut,
    NotificationsOut,
    ReportIncorrectIn,
    SavedPlaceOut,
    SavedPlacesOut,
    SuggestUpdateIn,
)

MANGALURU_TZ = "Asia/Kolkata"
COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE = 80.0

# Deliberately simple, deliberately disclosed as provisional (see
# README_PERSONAL.md): quiet level labels, never a leaderboard, never
# shown with ranking against other users.
_LEVEL_THRESHOLDS = [
    (0, "Explorer"), (3, "Pathfinder"), (8, "Local Guide"), (16, "Insider"), (31, "Pioneer"),
]


def _explorer_level(total_approved: int) -> str:
    level = "Explorer"
    for threshold, name in _LEVEL_THRESHOLDS:
        if total_approved >= threshold:
            level = name
    return level


class PersonalService:
    def __init__(
        self,
        db: AsyncSession,
        submission_service: CommunitySubmissionService,
        trips_service: TripsService,
        place_repository: Optional[PlaceRepository] = None,
    ):
        self.db = db
        self.submission_service = submission_service
        self.trips_service = trips_service
        # Used only to validate place_id on the four "about an existing
        # place" contribution kinds. Optional/defaulted so this doesn't
        # break anyone constructing PersonalService positionally with
        # just the first three args (tests, older callers).
        self.place_repository = place_repository or submission_service.place_repo

    # -- Contributions ------------------------------------------------------
    async def submit_place(self, user_id: uuid.UUID, payload: AddPlaceIn) -> ContributionOut:
        place = Place(
            id=None,
            name=payload.name,
            category=payload.category,
            coordinates=Coordinates(latitude=payload.latitude, longitude=payload.longitude),
            opening_hours=OpeningHours(raw=""),
            price_band=PriceBand(payload.price_band),
            estimated_cost=payload.estimated_cost,
            description=payload.description,
            bias_signals=BiasSignals(local_percentage=COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE, media_mentions=0),
            accessibility=AccessibilityInfo(),
        )
        note = payload.note
        if payload.media_url:
            note = ((note + "\n") if note else "") + f"Photo: {payload.media_url}"
        submission = await self.submission_service.submit(place, note)
        record = ContributionRecord(user_id=user_id, submission_id=submission.id, kind="add_place")
        self.db.add(record)
        await self.db.commit()
        return ContributionOut(
            contribution_id=str(record.id), kind="add_place", submission_id=submission.id, place_name=payload.name,
            status=submission.status, submitted_at=submission.submitted_at, reviewed_at=None,
            impact_message="Thanks — your submission is in review. We'll let you know as soon as it's checked.",
            explorer_points=None,
        )

    async def _require_place_name(self, place_id: str) -> str:
        place = await self.place_repository.get_by_id(place_id)
        if place is None:
            raise ValueError(f"Place {place_id} not found")
        return place.name

    async def submit_suggest_update(self, user_id: uuid.UUID, payload: SuggestUpdateIn) -> ContributionOut:
        place_name = await self._require_place_name(payload.place_id)
        record = ContributionRecord(
            user_id=user_id, kind="suggest_update", place_id=payload.place_id, status="pending",
            metadata_json=payload.model_dump(exclude={"place_id"}),
        )
        self.db.add(record)
        await self.db.commit()
        return ContributionOut(
            contribution_id=str(record.id), kind="suggest_update", place_id=payload.place_id, place_name=place_name,
            status="pending", submitted_at=record.created_at, reviewed_at=None,
            impact_message="Thanks — we've logged your suggested update for review.",
            explorer_points=None,
        )

    async def submit_local_tip(self, user_id: uuid.UUID, payload: LocalTipIn) -> ContributionOut:
        place_name = await self._require_place_name(payload.place_id)
        record = ContributionRecord(
            user_id=user_id, kind="local_tip", place_id=payload.place_id, status="pending",
            metadata_json=payload.model_dump(exclude={"place_id"}),
        )
        self.db.add(record)
        await self.db.commit()
        return ContributionOut(
            contribution_id=str(record.id), kind="local_tip", place_id=payload.place_id, place_name=place_name,
            status="pending", submitted_at=record.created_at, reviewed_at=None,
            impact_message="Thanks for sharing what you know — your tip is logged and waiting on review "
                            "before it's shown to other explorers as a community tip.",
            explorer_points=None,
        )

    async def submit_report_incorrect(self, user_id: uuid.UUID, payload: ReportIncorrectIn) -> ContributionOut:
        place_name = await self._require_place_name(payload.place_id)
        record = ContributionRecord(
            user_id=user_id, kind="report_incorrect", place_id=payload.place_id, status="pending",
            metadata_json=payload.model_dump(exclude={"place_id"}),
        )
        self.db.add(record)
        await self.db.commit()
        return ContributionOut(
            contribution_id=str(record.id), kind="report_incorrect", place_id=payload.place_id, place_name=place_name,
            status="pending", submitted_at=record.created_at, reviewed_at=None,
            impact_message="Thanks for the heads up — we've logged this report for review.",
            explorer_points=None,
        )

    async def submit_add_media(self, user_id: uuid.UUID, payload: AddMediaIn) -> ContributionOut:
        place_name = await self._require_place_name(payload.place_id)
        record = ContributionRecord(
            user_id=user_id, kind="add_media", place_id=payload.place_id, status="pending",
            metadata_json=payload.model_dump(exclude={"place_id"}),
        )
        self.db.add(record)
        await self.db.commit()
        return ContributionOut(
            contribution_id=str(record.id), kind="add_media", place_id=payload.place_id, place_name=place_name,
            status="pending", submitted_at=record.created_at, reviewed_at=None,
            impact_message="Thanks — your media is logged and waiting on review.",
            explorer_points=None,
        )

    async def list_my_contributions(self, user_id: uuid.UUID) -> MyContributionsOut:
        result = await self.db.execute(
            select(ContributionRecord).where(ContributionRecord.user_id == user_id)
            .order_by(ContributionRecord.created_at.desc())
        )
        records = list(result.scalars().all())
        out: list[ContributionOut] = []
        total_approved = 0
        for r in records:
            if r.kind == "add_place" and r.submission_id:
                submission = await self.submission_service.submission_repo.get_by_id(r.submission_id)
                if submission is None:
                    continue
                if submission.status == "approved":
                    total_approved += 1
                    impact = "VERIFIED — your contribution helped improve GroundZero for future explorers."
                    points: Optional[int] = 30
                elif submission.status == "rejected":
                    impact = "This one didn't make it into GroundZero this time — thanks for trying anyway."
                    points = None
                else:
                    impact = "In review — thanks for helping build GroundZero."
                    points = None
                out.append(ContributionOut(
                    contribution_id=str(r.id), kind="add_place", submission_id=r.submission_id,
                    place_name=submission.submitted_place.name, status=submission.status,
                    submitted_at=submission.submitted_at or r.created_at, reviewed_at=submission.reviewed_at,
                    impact_message=impact, explorer_points=points,
                ))
                continue

            # The other four kinds: this record's own `status` column is
            # authoritative (no admin review action moves it off
            # "pending" yet — honestly reported, never faked as approved).
            place_name = "(place)"
            if r.place_id:
                place = await self.place_repository.get_by_id(r.place_id)
                if place is not None:
                    place_name = place.name
            label = {
                "suggest_update": "Your suggested update is logged and awaiting review.",
                "local_tip": "Your local tip is logged and awaiting review before it's shown to other explorers.",
                "report_incorrect": "Your report is logged and awaiting review.",
                "add_media": "Your media is logged and awaiting review.",
            }.get(r.kind, "Logged and awaiting review.")
            out.append(ContributionOut(
                contribution_id=str(r.id), kind=r.kind, place_id=r.place_id, place_name=place_name,
                status=r.status, submitted_at=r.created_at, reviewed_at=r.reviewed_at,
                impact_message=label, explorer_points=None,
            ))
        return MyContributionsOut(
            contributions=out, total_approved=total_approved, explorer_level=_explorer_level(total_approved),
        )

    # -- Notifications --------------------------------------------------------
    async def notifications(self, user_id: uuid.UUID) -> NotificationsOut:
        """Computed per-request, bundled by category. Never stored, never
        spammed: a quiet afternoon with nothing noteworthy returns an
        empty or near-empty list rather than inventing filler."""
        items: list[NotificationOut] = []
        trips = await self.trips_service.list_my_trips(user_id)
        active = next((t for t in trips if t.status in ("active", "paused")), None)

        if active is not None:
            items.extend(self._now_and_journey_notifications(active))

        # GROUNDZERO category: recent contribution status changes.
        contrib_result = await self.db.execute(
            select(ContributionRecord).where(ContributionRecord.user_id == user_id)
            .order_by(ContributionRecord.created_at.desc()).limit(10)
        )
        for r in contrib_result.scalars().all():
            # BUG FIX (4th audit response, Oct 2026): the four newer
            # contribution kinds (suggest_update, local_tip,
            # report_incorrect, add_media) are logged with
            # submission_id=None (see add_place vs. those four in
            # submit_contribution) -- only add_place ever goes through
            # the layer0 CommunitySubmission pipeline. Calling
            # get_by_id(None) used to raise inside uuid.UUID(None)
            # (TypeError, not a clean None), crashing this endpoint with
            # a 500 as soon as a user had any non-add_place contribution
            # in their last 10. Only look up a submission for the kind
            # that actually has one; the other four kinds have nothing
            # to notify about here yet (no review step exists for them —
            # see README_PERSONAL.md), so they're simply skipped rather
            # than faking a notification for a review that never happens.
            if r.kind != "add_place" or not r.submission_id:
                continue
            submission = await self.submission_service.submission_repo.get_by_id(r.submission_id)
            if submission is None or submission.status == "pending" or submission.reviewed_at is None:
                continue
            recent = (datetime.now(timezone.utc) - submission.reviewed_at).total_seconds() < 60 * 60 * 24 * 7
            if not recent:
                continue
            if submission.status == "approved":
                items.append(NotificationOut(
                    id=f"contrib-{r.id}", category="GROUNDZERO",
                    headline="Your contribution was verified",
                    body=f'"{submission.submitted_place.name}" is now part of GroundZero — thanks for helping build it.',
                ))
            else:
                items.append(NotificationOut(
                    id=f"contrib-{r.id}", category="GROUNDZERO",
                    headline="An update on your submission",
                    body=f'"{submission.submitted_place.name}" wasn\'t added this time.',
                ))
        return NotificationsOut(notifications=items)

    def _now_and_journey_notifications(self, trip: Trip) -> list[NotificationOut]:
        out: list[NotificationOut] = []
        next_place = next((p for p in trip.places if p.status == "pending"), None)
        bits: list[str] = []
        headline = "Your afternoon update"

        if next_place is not None and trip.origin_latitude is not None and trip.origin_longitude is not None \
                and next_place.latitude is not None and next_place.longitude is not None:
            distance_km = _haversine_km(
                trip.origin_latitude, trip.origin_longitude, next_place.latitude, next_place.longitude
            )
            minutes = max(1, int(distance_km / 0.8))  # ~3 km/h walking-and-stopping pace, same assumption layer2 uses elsewhere
            bits.append(f"Your next stop, {next_place.place_name}, is around {minutes} minutes away.")

        sunset_bit, minutes_to_sunset = self._sunset_bit(next_place)
        if sunset_bit:
            bits.append(sunset_bit)

        if trip.budget_remaining < trip.budget_total * 0.15:
            bits.append(f"You have about Rs.{trip.budget_remaining:.0f} left in today's budget.")

        if bits:
            if minutes_to_sunset is not None and 0 < minutes_to_sunset < 90:
                headline = "Sunset's coming up"
            out.append(NotificationOut(
                id=f"journey-{trip.id}", category="YOUR_JOURNEY", headline=headline, body=" ".join(bits),
            ))

        if next_place is not None:
            out.append(NotificationOut(
                id=f"now-{trip.id}", category="NOW", headline="Up next",
                body=f"{next_place.place_name} is your next stop whenever you're ready.",
            ))
        return out

    # -- Saved Places -----------------------------------------------------
    async def save_place(self, user_id: uuid.UUID, place_id: str) -> SavedPlaceOut:
        """Idempotent: saving an already-saved place returns the existing
        row rather than raising or inserting a duplicate (the DB-level
        UniqueConstraint on (user_id, place_id) is the real backstop; this
        check just avoids a round trip to the DB raising an IntegrityError
        on the happy "tapped save twice" path)."""
        place = await self.place_repository.get_by_id(place_id)
        if place is None:
            raise ValueError(f"Place {place_id} not found")

        existing = await self.db.execute(
            select(SavedPlace).where(SavedPlace.user_id == user_id, SavedPlace.place_id == place_id)
        )
        record = existing.scalar_one_or_none()
        if record is None:
            record = SavedPlace(user_id=user_id, place_id=place_id)
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)
        return SavedPlaceOut(
            saved_place_id=str(record.id), place_id=place_id, place_name=place.name,
            category=place.category, saved_at=record.created_at,
        )

    async def unsave_place(self, user_id: uuid.UUID, place_id: str) -> bool:
        """Returns False (not an error) if the place wasn't saved —
        unsaving something that's already unsaved is a no-op, same
        idempotent spirit as save_place."""
        result = await self.db.execute(
            select(SavedPlace).where(SavedPlace.user_id == user_id, SavedPlace.place_id == place_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.commit()
        return True

    async def list_saved_places(self, user_id: uuid.UUID) -> SavedPlacesOut:
        result = await self.db.execute(
            select(SavedPlace).where(SavedPlace.user_id == user_id).order_by(SavedPlace.created_at.desc())
        )
        records = list(result.scalars().all())
        out: list[SavedPlaceOut] = []
        for r in records:
            place = await self.place_repository.get_by_id(r.place_id)
            # A place can vanish (e.g. test/dev data cleanup) without the
            # bookmark being cleaned up too — skip it rather than crash
            # the whole list over one stale row.
            if place is None:
                continue
            out.append(SavedPlaceOut(
                saved_place_id=str(r.id), place_id=r.place_id, place_name=place.name,
                category=place.category, saved_at=r.created_at,
            ))
        return SavedPlacesOut(saved_places=out)

    def _sunset_bit(self, next_place: Optional[TripPlace]) -> tuple[Optional[str], Optional[int]]:
        lat, lon = 12.9141, 74.8560  # Mangaluru centre — used only to phrase the sunset line when a trip has no fix yet
        if next_place is not None and next_place.latitude is not None and next_place.longitude is not None:
            lat, lon = next_place.latitude, next_place.longitude
        tzinfo = ZoneInfo(MANGALURU_TZ)
        now_local = datetime.now(timezone.utc).astimezone(tzinfo)
        loc = LocationInfo("Mangaluru", "India", MANGALURU_TZ, lat, lon)
        sun_times = sun(loc.observer, date=now_local.date(), tzinfo=tzinfo)
        minutes_to_sunset = int((sun_times["sunset"] - now_local).total_seconds() // 60)
        if 0 < minutes_to_sunset < 90:
            return (
                f"Sunset is in about {minutes_to_sunset} minutes — you have enough time to reach your next stop before it.",
                minutes_to_sunset,
            )
        return None, minutes_to_sunset
