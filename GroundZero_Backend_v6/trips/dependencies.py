from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from layer0.application.bias_audit import BiasAuditService
from layer0.application.custom_place_service import CustomPlaceService
from layer0.application.dedup import DedupService
from layer0.application.freshness import FreshnessService
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository
from layer0.infrastructure.db.session import get_session
from layer1.api.dependencies import get_curiosity_extractor, get_profile_extractor, get_session_store
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.application.profile_extractor import ProfileExtractor
from layer1.application.survey_service import SurveyService
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.db.repository_impl import PostgresTouristProfileRepository
from layer1.infrastructure.survey_session_store import SurveySessionStore
from layer2.api.dependencies import get_hive_engine
from layer2.application.hive_engine import HiveEngine
from shared.config import Settings, get_settings

from trips.service import TripsService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


def get_place_repository(session: AsyncSession = Depends(get_db_session)) -> PlaceRepository:
    return PostgresPlaceRepository(session)


def get_profile_repository(session: AsyncSession = Depends(get_db_session)) -> TouristProfileRepository:
    return PostgresTouristProfileRepository(session)


def get_survey_service(
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
    curiosity_extractor: CuriosityExtractor = Depends(get_curiosity_extractor),
    session_store: SurveySessionStore = Depends(get_session_store),
    profile_extractor: ProfileExtractor = Depends(get_profile_extractor),
) -> SurveyService:
    return SurveyService(profile_repo, curiosity_extractor, session_store, profile_extractor=profile_extractor)


def get_custom_place_service(
    place_repo: PlaceRepository = Depends(get_place_repository),
    settings: Settings = Depends(get_settings),
) -> CustomPlaceService:
    return CustomPlaceService(
        place_repository=place_repo,
        dedup=DedupService(),
        bias_audit=BiasAuditService(),
        freshness=FreshnessService(stale_after_days=settings.freshness_stale_after_days),
    )


def get_trips_service(
    db: AsyncSession = Depends(get_db_session),
    survey_service: SurveyService = Depends(get_survey_service),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
    hive_engine: HiveEngine = Depends(get_hive_engine),
    place_repo: PlaceRepository = Depends(get_place_repository),
    custom_place_service: CustomPlaceService = Depends(get_custom_place_service),
) -> TripsService:
    return TripsService(db, survey_service, profile_repo, hive_engine, place_repo, custom_place_service)
