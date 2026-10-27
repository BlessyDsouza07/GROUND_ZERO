"""
Shared HTTP client for all Layer 0 collectors.

Design goals:
  - Real network calls only — no mock mode, no fixture fallback.
  - When a source is unreachable (network egress restricted, API down, rate
    limited past retries), raise `SourceUnavailable` with a specific reason.
    Callers (the orchestrator) catch this and skip that source for that run
    — the pipeline finishes, that source's contribution is just absent for
    this pass, and it tries again on the next scheduled run.
  - This is the only place retry/backoff/rate-limit logic lives, so every
    collector behaves consistently.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("groundzero.layer0.http_client")

# Wikidata (and some other public APIs) reject requests with no descriptive
# User-Agent per https://meta.wikimedia.org/wiki/User-Agent_policy — a
# missing/generic one gets a flat 403, independent of network reachability.
DEFAULT_USER_AGENT = "GroundZero-Tourism-Pipeline/1.0 (https://github.com/your-org/groundzero; contact@example.com)"


class SourceUnavailable(Exception):
    """Raised when an external data source cannot be reached after retries.
    Carries a specific, non-generic reason so failures are diagnosable."""

    def __init__(self, source: str, reason: str, status_code: int | None = None):
        self.source = source
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"[{source}] unavailable: {reason} (status={status_code})")


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 20.0


class ResilientHttpClient:
    def __init__(self, retry_config: RetryConfig | None = None, timeout_seconds: float = 15.0):
        self.retry_config = retry_config or RetryConfig()
        self.timeout_seconds = timeout_seconds

    async def request(
        self,
        source: str,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        request_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(1, self.retry_config.max_attempts + 1):
                try:
                    response = await client.request(
                        method, url, params=params, json=json_body, headers=request_headers
                    )
                except httpx.TimeoutException as exc:
                    last_exc = exc
                    logger.warning("%s timeout on attempt %d/%d", source, attempt, self.retry_config.max_attempts)
                except (
                    httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError,
                    httpx.ProxyError,
                ) as exc:
                    # ProxyError added alongside the others: an environment that
                    # routes egress through a forward proxy (e.g. an allowlist
                    # proxy blocking a host outright) raises this instead of
                    # ConnectError, and it was falling through uncaught into a
                    # raw 500 instead of the intended graceful
                    # SourceUnavailable-and-skip-this-source degradation.
                    last_exc = exc
                    logger.warning(
                        "%s transport/protocol error on attempt %d/%d: %s",
                        source, attempt, self.retry_config.max_attempts, exc,
                    )
                else:
                    if response.status_code == 429:
                        retry_after = float(response.headers.get("Retry-After", self.retry_config.base_delay_seconds))
                        logger.warning("%s rate-limited, honoring Retry-After=%.1fs", source, retry_after)
                        await asyncio.sleep(min(retry_after, self.retry_config.max_delay_seconds))
                        continue
                    if response.status_code >= 500:
                        last_exc = None
                        logger.warning(
                            "%s server error %d on attempt %d/%d",
                            source, response.status_code, attempt, self.retry_config.max_attempts,
                        )
                    elif response.status_code in {401, 403, 406}:
                        # Distinct from a transient failure — usually means the
                        # network path to this host is blocked, credentials are
                        # invalid/missing (401 — e.g. a placeholder API key), or
                        # the request is rejected by the upstream service (e.g.
                        # Overpass 406), not a temporary server error.
                        raise SourceUnavailable(
                            source,
                            f"request rejected ({response.status_code}) — check network egress / request format",
                            status_code=response.status_code,
                        )
                    else:
                        response.raise_for_status()
                        return response

                delay = min(
                    self.retry_config.base_delay_seconds * (2 ** (attempt - 1)),
                    self.retry_config.max_delay_seconds,
                )
                if attempt < self.retry_config.max_attempts:
                    await asyncio.sleep(delay)

        reason = str(last_exc) if last_exc else "exhausted retries with server errors"
        raise SourceUnavailable(source, reason)