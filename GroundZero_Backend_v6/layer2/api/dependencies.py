from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from layer0.application.accessibility import AccessibilityDetector
from layer0.application.freshness import FreshnessService
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.collectors.tide_collector import TideCollector
from layer0.infrastructure.collectors.weather_collector import WeatherCollector
from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository
from layer0.infrastructure.db.session import get_session
from layer0.infrastructure.http_client import ResilientHttpClient
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.db.repository_impl import PostgresTouristProfileRepository
from layer2.application.feedback_service import ItineraryFeedbackService
from layer2.application.hard_filters import HardFilterService
from layer2.application.hive_engine import HiveEngine
from layer2.application.ranking import RankingConfig
from layer2.application.personal_fit_score import PersonalFitScoreService
from layer2.application.reachability import ReachabilityService
from layer2.application.routing_service import RoutingService
from layer2.application.slot_assembly import SlotAssemblyService
from layer2.application.transport_tagger import TransportTagger
from layer2.application.weather_scheduler import WeatherScheduler
from layer2.domain.feedback_repositories import ItineraryFeedbackRepository
from layer2.infrastructure.db.repository_impl import PostgresItineraryFeedbackRepository
from shared.config import Settings, get_settings


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


def get_place_repository(session: AsyncSession = Depends(get_db_session)) -> PlaceRepository:
    return PostgresPlaceRepository(session)


def get_profile_repository(session: AsyncSession = Depends(get_db_session)) -> TouristProfileRepository:
    return PostgresTouristProfileRepository(session)


def get_itinerary_feedback_repository(session: AsyncSession = Depends(get_db_session)) -> ItineraryFeedbackRepository:
    return PostgresItineraryFeedbackRepository(session)


def get_itinerary_feedback_service(
    repository: ItineraryFeedbackRepository = Depends(get_itinerary_feedback_repository),
) -> ItineraryFeedbackService:
    return ItineraryFeedbackService(repository)


def get_tide_collector(settings: Settings = Depends(get_settings)) -> TideCollector:
    """Not yet consumed by HiveEngine (tide is a Layer 3 Context Engine
    Tier B signal — blueprint Table 6 — not a Layer 2 pre-trip scheduling
    input the way weather is), but wired here the same way
    `weather_collector` is above so Layer 3 can `Depends(get_tide_collector)`
    once it's built, instead of every future caller re-wiring the
    WorldTides/Open-Meteo-Marine fallback logic itself."""
    http_client = ResilientHttpClient()
    return TideCollector(http_client, settings.tide_api_url, settings.tide_api_key)


def get_hive_engine(
    settings: Settings = Depends(get_settings),
    place_repo: PlaceRepository = Depends(get_place_repository),
) -> HiveEngine:
    http_client = ResilientHttpClient()
    curiosity_extractor = CuriosityExtractor()
    weather_collector = WeatherCollector(http_client, settings.openweathermap_url, settings.openweathermap_api_key)

    return HiveEngine(
        place_repository=place_repo,
        hard_filters=HardFilterService(
            AccessibilityDetector(),
            FreshnessService(stale_after_days=settings.freshness_stale_after_days),
            freshness_min_score=settings.freshness_min_score,
            use_typical_hours=True,
        ),
        fit_score=PersonalFitScoreService(curiosity_extractor),
        slot_assembly=SlotAssemblyService(),
        weather_scheduler=WeatherScheduler(),
        transport_tagger=TransportTagger(),
        weather_collector=weather_collector,
        mangaluru_center=((settings.bbox_south + settings.bbox_north) / 2, (settings.bbox_west + settings.bbox_east) / 2),
        reachability=ReachabilityService(),
        routing_service=RoutingService(),
        ranking=RankingConfig(),
    )
