"""
Regression tests for the Redis fallback fix (layer1/api/dependencies.py).

An architectural audit found that the original fallback logic wrapped
`redis.from_url()` in a try/except, which can never catch a down Redis
because `from_url()` constructs a lazy client without validating
reachability. These tests use a fake client with a controllable `.ping()`
so the health-check logic itself is verified without needing a real
Redis process (that live verification was also done separately, against
an actual Redis instance and an actual closed port).
"""
import time
from unittest.mock import AsyncMock, patch

import pytest

from layer1.api import dependencies as deps


class FakeHealthyClient:
    async def ping(self):
        return True


class FakeUnhealthyClient:
    async def ping(self):
        raise ConnectionError("simulated Redis outage")


@pytest.fixture(autouse=True)
def clear_health_cache():
    deps._last_health_check.clear()
    deps._get_redis_client.cache_clear()
    yield
    deps._last_health_check.clear()
    deps._get_redis_client.cache_clear()


@pytest.mark.asyncio
async def test_reachable_redis_returns_true():
    with patch.object(deps, "_get_redis_client", return_value=FakeHealthyClient()):
        result = await deps._redis_is_reachable("redis://fake-healthy/0")
    assert result is True


@pytest.mark.asyncio
async def test_unreachable_redis_returns_false_not_raises():
    """This is the exact behavior the old code was supposed to have and
    didn't: a failing PING must resolve to False, not propagate an
    exception up into get_session_store."""
    with patch.object(deps, "_get_redis_client", return_value=FakeUnhealthyClient()):
        result = await deps._redis_is_reachable("redis://fake-unhealthy/0")
    assert result is False


@pytest.mark.asyncio
async def test_health_check_result_is_cached_within_ttl():
    call_count = 0

    class CountingClient:
        async def ping(self):
            nonlocal call_count
            call_count += 1
            return True

    with patch.object(deps, "_get_redis_client", return_value=CountingClient()):
        await deps._redis_is_reachable("redis://fake-counting/0")
        await deps._redis_is_reachable("redis://fake-counting/0")
        await deps._redis_is_reachable("redis://fake-counting/0")

    assert call_count == 1  # only the first call actually pinged


@pytest.mark.asyncio
async def test_health_check_re_pings_after_ttl_expires():
    call_count = 0

    class CountingClient:
        async def ping(self):
            nonlocal call_count
            call_count += 1
            return True

    with patch.object(deps, "_get_redis_client", return_value=CountingClient()):
        await deps._redis_is_reachable("redis://fake-ttl/0")
        # Simulate time passing beyond the cache TTL by rewriting the
        # cached timestamp directly rather than actually sleeping.
        cached_time, cached_value = deps._last_health_check["redis://fake-ttl/0"]
        deps._last_health_check["redis://fake-ttl/0"] = (
            cached_time - deps._HEALTH_CACHE_TTL_SECONDS - 1,
            cached_value,
        )
        await deps._redis_is_reachable("redis://fake-ttl/0")

    assert call_count == 2


@pytest.mark.asyncio
async def test_get_session_store_returns_redis_store_when_healthy():
    from layer1.infrastructure.survey_session_store import RedisSurveySessionStore
    from shared.config import Settings

    settings = Settings(redis_url="redis://fake-healthy/0")
    with patch.object(deps, "_get_redis_client", return_value=FakeHealthyClient()):
        store = await deps.get_session_store(settings)
    assert isinstance(store, RedisSurveySessionStore)


@pytest.mark.asyncio
async def test_get_session_store_falls_back_to_in_memory_when_unhealthy():
    from layer1.infrastructure.survey_session_store import InMemorySurveySessionStore
    from shared.config import Settings

    settings = Settings(redis_url="redis://fake-unhealthy-2/0")
    with patch.object(deps, "_get_redis_client", return_value=FakeUnhealthyClient()):
        store = await deps.get_session_store(settings)
    assert isinstance(store, InMemorySurveySessionStore)
