from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from layer0.infrastructure.db.session import get_session
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.application.profile_extractor import ProfileExtractor
from layer1.application.survey_service import SurveyService
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.db.repository_impl import PostgresTouristProfileRepository
from layer1.infrastructure.survey_session_store import (
    InMemorySurveySessionStore,
    RedisSurveySessionStore,
    SurveySessionStore,
)
from shared.config import Settings, get_settings

logger = logging.getLogger("groundzero.layer1.api.dependencies")


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


def get_profile_repository(session: AsyncSession = Depends(get_db_session)) -> TouristProfileRepository:
    return PostgresTouristProfileRepository(session)


def get_curiosity_extractor() -> CuriosityExtractor:
    return CuriosityExtractor()


def get_profile_extractor() -> ProfileExtractor:
    return ProfileExtractor()


# A single shared in-memory fallback instance (not a fresh one per request)
# so that if Redis is unreachable, at least a single-worker dev setup still
# keeps sessions alive across requests within that one process. This is
# explicitly a degraded fallback, not the production path — see
# get_session_store's docstring.
_fallback_store = InMemorySurveySessionStore()

# Health-check result cache: PING costs a real round trip, so we don't want
# to pay it on every single request. Cached briefly (not indefinitely) so
# an outage is detected within a bounded window rather than never.
_HEALTH_CACHE_TTL_SECONDS = 5.0
_last_health_check: dict[str, tuple[float, bool]] = {}


@lru_cache
def _get_redis_client(redis_url: str):
    import redis.asyncio as redis
    # NOTE: redis.from_url() is lazy — it constructs a client object without
    # opening a connection or validating reachability. An earlier version of
    # this module relied on a try/except around this call to detect a down
    # Redis; that never worked, because this line cannot fail regardless of
    # whether Redis is actually reachable. Confirmed empirically: calling
    # this against a port nothing listens on still returns a client object
    # with no exception. The real health check is _redis_is_reachable below.
    return redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1.0, socket_timeout=1.0)


async def _redis_is_reachable(redis_url: str) -> bool:
    now = time.monotonic()
    cached = _last_health_check.get(redis_url)
    if cached is not None and (now - cached[0]) < _HEALTH_CACHE_TTL_SECONDS:
        return cached[1]

    client = _get_redis_client(redis_url)
    try:
        await client.ping()
        healthy = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Redis PING failed (%s) — falling back to in-memory survey session "
            "store. Sessions will NOT survive a restart or work across multiple "
            "API workers until Redis is reachable.",
            exc,
        )
        healthy = False

    _last_health_check[redis_url] = (now, healthy)
    return healthy


async def get_session_store(settings: Settings = Depends(get_settings)) -> SurveySessionStore:
    """Real Redis-backed session storage in production. Falls back to a
    single-process in-memory store only if Redis genuinely can't be
    reached (verified with an actual PING, cached for
    _HEALTH_CACHE_TTL_SECONDS to bound the cost) — this keeps local dev
    without Redis running from hard-failing every survey request, at the
    cost of losing sessions across workers/restarts in that degraded
    mode. Not silent: logs a warning every time it falls back, so the gap
    is visible in ops rather than discovered by a lost survey."""
    if await _redis_is_reachable(settings.redis_url):
        return RedisSurveySessionStore(_get_redis_client(settings.redis_url))
    return _fallback_store


def get_survey_service(
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
    curiosity_extractor: CuriosityExtractor = Depends(get_curiosity_extractor),
    session_store: SurveySessionStore = Depends(get_session_store),
    profile_extractor: ProfileExtractor = Depends(get_profile_extractor),
) -> SurveyService:
    return SurveyService(profile_repo, curiosity_extractor, session_store, profile_extractor=profile_extractor)
