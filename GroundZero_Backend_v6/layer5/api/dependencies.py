from __future__ import annotations

import uuid

from fastapi import Depends

from auth.dependencies import get_current_user
from auth.models import User
from layer0.domain.repositories import PlaceRepository
from layer1.domain.repositories import TouristProfileRepository
from layer2.api.dependencies import get_hive_engine, get_place_repository, get_profile_repository
from layer2.application.hive_engine import HiveEngine
from layer5.chatbot import TourismChatbot
from layer5.geofencing import GeofencingEngine
from layer5.multilingual import MultilingualInterface
from layer5.voice_guide import VoiceGuideOrchestrator

# Long-lived singletons: voice engine readiness and the multilingual
# interface hold no per-user state (translation is a pure function of
# the text + target language), so one shared instance per process is
# fine and needs no further change.
_voice_guide = VoiceGuideOrchestrator()
_multilingual = MultilingualInterface()

# BUG FIX (audit response, Oct 2026): geofencing state is NOT
# stateless — `GeofencingEngine` tracks which fences are "active" and
# the last known GPS fix, per instance. This used to be ONE global
# singleton shared by every signed-in user in the process: User A
# loading their itinerary's geofences, then User B sending a GPS ping,
# would evaluate B's position against A's fences and mutate the same
# `active_geofences` set — not a valid multi-user design. Fixed by
# keying a dict of engines by user id instead of one shared instance.
# Still in-memory-only per worker process (same caveat as Redis-backed
# survey sessions already disclosed elsewhere — needs a shared store,
# e.g. Redis, before a true multi-worker deployment), but now at least
# correctly scoped to one user instead of leaking across all of them.
_geofencing_engines: dict[uuid.UUID, GeofencingEngine] = {}


def get_chatbot(
    place_repo: PlaceRepository = Depends(get_place_repository),
    hive_engine: HiveEngine = Depends(get_hive_engine),
) -> TourismChatbot:
    # Bug fixed: TourismChatbot previously always constructed with
    # place_repository=None, hive_engine=None (see chatbot.py), so every
    # chatbot search/recommendation call silently returned nothing no
    # matter what the user asked. Now wired to the same real Postgres-
    # backed repository and HIVE engine Layer 0/2's own routes use.
    return TourismChatbot(place_repository=place_repo, hive_engine=hive_engine)


def get_geofencing_engine(user: User = Depends(get_current_user)) -> GeofencingEngine:
    engine = _geofencing_engines.get(user.id)
    if engine is None:
        engine = GeofencingEngine()
        _geofencing_engines[user.id] = engine
    return engine


def get_voice_guide() -> VoiceGuideOrchestrator:
    return _voice_guide


def get_multilingual_interface() -> MultilingualInterface:
    return _multilingual


__all__ = [
    "get_chatbot",
    "get_geofencing_engine",
    "get_voice_guide",
    "get_multilingual_interface",
    "get_place_repository",
    "get_profile_repository",
]
