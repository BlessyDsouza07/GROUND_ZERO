"""
Phase 1 (Aug 4 2026) — Quick tests for new features:
1. Return visitor mark-visited endpoint
2. HTTP response caching

These validate that the new infrastructure works as designed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from layer0.infrastructure.http_cache import HttpResponseCache


@pytest.mark.asyncio
async def test_http_cache_stores_and_retrieves_response():
    """Test that HTTP cache stores and retrieves responses correctly."""
    # Mock Redis client
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.setex = AsyncMock()
    
    cache = HttpResponseCache(redis_client, ttl_seconds=3600)
    
    # Simulate a cache miss, then set
    url = "https://en.wikipedia.org/wiki/Mangalore"
    response_data = {"title": "Mangalore", "extract": "A coastal city..."}
    
    # First call should be a miss
    result = await cache.get(url)
    assert result is None
    assert cache.misses == 1
    
    # Set the cache
    await cache.set(url, response_data)
    redis_client.setex.assert_called_once()
    
    # Simulate cache hit
    redis_client.get = AsyncMock(return_value='{"title": "Mangalore", "extract": "A coastal city..."}')
    result = await cache.get(url)
    assert result == response_data
    assert cache.hits == 1


@pytest.mark.asyncio
async def test_http_cache_generates_unique_keys():
    """Test that different URLs generate different cache keys."""
    redis_client = AsyncMock()
    cache = HttpResponseCache(redis_client)
    
    url1 = "https://en.wikipedia.org/wiki/Mangalore"
    url2 = "https://en.wikipedia.org/wiki/Bangalore"
    
    key1 = cache._cache_key(url1)
    key2 = cache._cache_key(url2)
    
    assert key1 != key2
    assert key1.startswith("http_cache:")
    assert key2.startswith("http_cache:")


def test_http_cache_stats():
    """Test that cache stats are calculated correctly."""
    redis_client = AsyncMock()
    cache = HttpResponseCache(redis_client)
    
    # Simulate some hits and misses
    cache.hits = 8
    cache.misses = 2
    
    stats = cache.stats()
    
    assert stats["hits"] == 8
    assert stats["misses"] == 2
    assert stats["total_requests"] == 10
    assert stats["hit_rate_percent"] == 80.0


@pytest.mark.asyncio
async def test_http_cache_gracefully_handles_redis_failure():
    """Test that cache failures don't break ETL."""
    # Mock Redis that raises an exception
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(side_effect=Exception("Redis connection failed"))
    redis_client.setex = AsyncMock(side_effect=Exception("Redis connection failed"))
    
    cache = HttpResponseCache(redis_client)
    
    url = "https://en.wikipedia.org/wiki/Mangalore"
    response_data = {"title": "Mangalore"}
    
    # Cache operations should not raise, just log and continue
    result = await cache.get(url)
    assert result is None
    
    await cache.set(url, response_data)
    # No exception raised — ETL continues normally
