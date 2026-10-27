from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from layer1.domain.entities import (
    AccessibilityFlag,
    CompanionLanguage,
    CrowdTolerance,
    CuriosityVector,
    DietaryFlag,
    EnergyBand,
    GroupConfig,
    Purpose,
    StartTimePreference,
    TouristProfile,
    TripDuration,
    VoicePersonality,
)
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.db.models import TouristProfileModel


def _to_model(profile: TouristProfile, existing: TouristProfileModel | None = None) -> TouristProfileModel:
    model = existing or TouristProfileModel(id=uuid.UUID(profile.id) if profile.id else uuid.uuid4())
    model.device_id = profile.device_id
    model.purpose = profile.purpose.value
    model.energy_band = profile.energy_band.value
    model.crowd_tolerance = profile.crowd_tolerance.value
    model.budget = profile.budget
    model.dietary_flags = [f.value for f in profile.dietary_flags]
    model.group_config = profile.group_config.value
    model.group_session_id = profile.group_session_id
    model.curiosity_text = profile.curiosity_text
    model.curiosity_vector = profile.curiosity_vector.weights
    model.trip_duration_hours = profile.trip_duration_hours.value
    model.multi_day_count = profile.multi_day_count
    model.start_time_preference = profile.start_time_preference.value
    model.accessibility_flags = [f.value for f in profile.accessibility_flags]
    model.companion_language = profile.companion_language.value
    model.voice_personality = profile.voice_personality.value
    model.return_visitor_exclusions = profile.return_visitor_exclusions
    # SECURITY FIX (final-release-hardening pass, Oct 2026): see
    # layer1/domain/entities.py::TouristProfile.user_id.
    model.user_id = uuid.UUID(profile.user_id) if profile.user_id else None
    return model


def _to_domain(model: TouristProfileModel) -> TouristProfile:
    return TouristProfile(
        id=str(model.id),
        purpose=Purpose(model.purpose),
        energy_band=EnergyBand(model.energy_band),
        crowd_tolerance=CrowdTolerance(model.crowd_tolerance),
        budget=model.budget,
        device_id=model.device_id,
        dietary_flags=[DietaryFlag(f) for f in model.dietary_flags],
        group_config=GroupConfig(model.group_config),
        group_session_id=model.group_session_id,
        curiosity_text=model.curiosity_text,
        curiosity_vector=CuriosityVector(weights=model.curiosity_vector or {}),
        trip_duration_hours=TripDuration(model.trip_duration_hours),
        multi_day_count=model.multi_day_count,
        start_time_preference=StartTimePreference(model.start_time_preference),
        accessibility_flags=[AccessibilityFlag(f) for f in model.accessibility_flags],
        companion_language=CompanionLanguage(model.companion_language),
        voice_personality=VoicePersonality(model.voice_personality),
        return_visitor_exclusions=model.return_visitor_exclusions or [],
        created_at=model.created_at,
        user_id=str(model.user_id) if model.user_id else None,
    )


class PostgresTouristProfileRepository(TouristProfileRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, profile: TouristProfile) -> TouristProfile:
        existing = await self.session.get(TouristProfileModel, uuid.UUID(profile.id)) if profile.id else None
        model = _to_model(profile, existing=existing)
        if not existing:
            self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return _to_domain(model)

    async def get_by_id(self, profile_id: str) -> Optional[TouristProfile]:
        model = await self.session.get(TouristProfileModel, uuid.UUID(profile_id))
        return _to_domain(model) if model else None

    async def get_prior_session_for_device(self, device_id: str) -> Optional[TouristProfile]:
        stmt = (
            select(TouristProfileModel)
            .where(TouristProfileModel.device_id == device_id)
            .order_by(TouristProfileModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def get_visited_place_ids(self, profile_id: str) -> list[str]:
        model = await self.session.get(TouristProfileModel, uuid.UUID(profile_id))
        return model.visited_log if model and model.visited_log else []

    async def mark_visited(self, profile_id: str, place_ids: list[str]) -> list[str]:
        model = await self.session.get(TouristProfileModel, uuid.UUID(profile_id))
        if model is None:
            raise ValueError(f"TouristProfile {profile_id} not found")
        existing = set(model.visited_log or [])
        existing.update(place_ids)
        model.visited_log = sorted(existing)
        await self.session.commit()
        await self.session.refresh(model)
        return model.visited_log

    async def list_by_group_session(self, group_session_id: str) -> list[TouristProfile]:
        stmt = select(TouristProfileModel).where(TouristProfileModel.group_session_id == group_session_id)
        result = await self.session.execute(stmt)
        return [_to_domain(m) for m in result.scalars().all()]
