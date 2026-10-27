"""
Survey session storage — pluggable, per Repository Pattern conventions
used everywhere else in this codebase.

The in-memory store is single-process only and loses all in-progress
surveys on restart — fine for tests, not for production with multiple API
workers. RedisSurveySessionStore is the real implementation: sessions
survive restarts and are shared across every worker process, with a TTL
so an abandoned survey doesn't linger in Redis forever.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

# SurveySession is defined in survey_service.py; imported lazily inside
# methods to avoid a circular import (survey_service.py imports this module).


class SurveySessionStore(ABC):
    @abstractmethod
    async def get(self, session_id: str):
        ...

    @abstractmethod
    async def set(self, session) -> None:
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        ...


class InMemorySurveySessionStore(SurveySessionStore):
    """Single-process, non-persistent. Used for tests and for local dev
    without Redis running. NOT suitable for production with more than one
    worker process — each worker would have its own, inconsistent copy."""

    def __init__(self):
        self._sessions: dict[str, "object"] = {}

    async def get(self, session_id: str):
        return self._sessions.get(session_id)

    async def set(self, session) -> None:
        self._sessions[session.id] = session

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


DEFAULT_SESSION_TTL_SECONDS = 3600  # an abandoned survey shouldn't linger forever


class RedisSurveySessionStore(SurveySessionStore):
    """Real Redis-backed session storage. Survives process restarts and is
    shared correctly across multiple API worker processes — the actual
    production requirement an in-memory dict can't meet."""

    def __init__(self, redis_client, key_prefix: str = "survey_session:", ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}{session_id}"

    def _serialize(self, session) -> str:
        return json.dumps({
            "id": session.id,
            "device_id": session.device_id,
            # SECURITY FIX (final-release-hardening pass, Oct 2026): same
            # class of bug as the inferred_steps fix below this one —
            # user_id must round-trip through Redis or ownership checks
            # on a session fetched from a worker that didn't create it
            # would silently see user_id=None and skip enforcement.
            "user_id": session.user_id,
            "join_group_session_id": session.join_group_session_id,
            "current_step_index": session.current_step_index,
            "answers": session.answers,
            # BUG FIX (security/correctness audit, Oct 2026): inferred_steps
            # was never serialized here, so every session round-trip
            # through real Redis silently reset it to an empty set. That
            # broke SurveySession._effective_step_order()'s skip-list,
            # which made the survey state machine walk onto
            # Q7_CURIOSITY_TEXT as a real "current step" — a step that is
            # neither in trips/service.py's _AUTO_FILLED nor its
            # _UI_STEP_NAME, so the survey silently reported
            # next_step=None while done=False, stalling forever. Found by
            # live end-to-end verification against a real Redis instance
            # (the in-memory fallback masks this entirely, which is why it
            # went unnoticed until Redis was actually exercised).
            "inferred_steps": sorted(session.inferred_steps),
            "started_at": session.started_at.isoformat(),
        })

    def _deserialize(self, raw: str):
        from layer1.application.survey_service import SurveySession  # local import, avoids circular import

        data = json.loads(raw)
        return SurveySession(
            id=data["id"],
            device_id=data["device_id"],
            user_id=data.get("user_id"),
            join_group_session_id=data.get("join_group_session_id"),
            current_step_index=data["current_step_index"],
            answers=data["answers"],
            inferred_steps=set(data.get("inferred_steps", [])),
            started_at=datetime.fromisoformat(data["started_at"]),
        )

    async def get(self, session_id: str):
        raw = await self.redis.get(self._key(session_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return self._deserialize(raw)

    async def set(self, session) -> None:
        await self.redis.set(self._key(session.id), self._serialize(session), ex=self.ttl_seconds)

    async def delete(self, session_id: str) -> None:
        await self.redis.delete(self._key(session_id))
