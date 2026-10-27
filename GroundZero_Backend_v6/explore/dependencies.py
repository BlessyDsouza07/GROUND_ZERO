"""Dependency wiring for Explore.

`get_current_user_optional` is the one genuinely new piece of auth
plumbing this chunk needs: every other router in this backend
(`trips/`, `layer3`, ...) requires a bearer token on every request
(`auth/dependencies.py::get_current_user` raises 401 if it's missing).
Explore's spec explicitly requires browsing/discovery to work for a
signed-out tourist, with sign-in only required at save/add-to-trip/
personalize moments — so most Explore routes use this optional version,
and only `POST /explore/add-to-journey` uses the real
`auth.dependencies.get_current_user`.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Optional

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from auth.routes import get_db
from auth.security import decode_token
from layer0.application.freshness import FreshnessService
from layer0.application.opening_hours_parser import OpeningHoursParser
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.collectors.tide_collector import TideCollector
from layer0.infrastructure.collectors.weather_collector import WeatherCollector
from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository
from layer0.infrastructure.db.session import get_session
from layer0.infrastructure.http_client import ResilientHttpClient
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer2.application.personal_fit_score import PersonalFitScoreService
from shared.config import Settings, get_settings

from .context_service import ExploreContextService
from .service import ExploreService


async def get_current_user_optional(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    user_id = decode_token(authorization[7:].strip())
    if user_id is None:
        return None
    try:
        user = await db.get(User, uuid.UUID(user_id))
    except ValueError:
        return None
    return user


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


def get_place_repository(session: AsyncSession = Depends(get_db_session)) -> PlaceRepository:
    return PostgresPlaceRepository(session)


def get_explore_service(
    place_repo: PlaceRepository = Depends(get_place_repository),
    settings: Settings = Depends(get_settings),
) -> ExploreService:
    http_client = ResilientHttpClient()
    weather_collector = WeatherCollector(http_client, settings.openweathermap_url, settings.openweathermap_api_key)
    tide_collector = TideCollector(http_client, settings.tide_api_url, settings.tide_api_key)
    context_service = ExploreContextService(weather_collector, tide_collector)

    return ExploreService(
        place_repository=place_repo,
        fit_score=PersonalFitScoreService(CuriosityExtractor()),
        context_service=context_service,
        opening_hours_parser=OpeningHoursParser(),
        freshness_service=FreshnessService(stale_after_days=settings.freshness_stale_after_days),
        mangaluru_center=((settings.bbox_south + settings.bbox_north) / 2, (settings.bbox_west + settings.bbox_east) / 2),
    )
