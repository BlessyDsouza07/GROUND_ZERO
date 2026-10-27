"""
Layer 5 API routes.

Bug fixed (the headline "layer 5" problem): this router did not exist at
all. `layer5/chatbot.py`, `geofencing.py`, `multilingual.py`, and
`voice_guide.py` were fully-written classes that nothing in the app ever
imported, instantiated with real data, or exposed over HTTP — `main.py`
only wired up layers 0, 1, and 2. That made every Layer 5 feature dead
code: reachable by nothing, tested by nothing, running with `None`
repositories even if someone had wired it up by hand. This module fixes
that by exposing real endpoints backed by the same Layer 0 place
repository and Layer 2 HIVE engine the rest of the app already uses, and
`main.py` now includes this router.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from auth.models import User
from layer0.domain.repositories import PlaceRepository
from layer5.api.dependencies import (
    get_chatbot,
    get_geofencing_engine,
    get_multilingual_interface,
    get_place_repository,
    get_voice_guide,
)
from layer5.api.schemas import (
    ChatRequestIn,
    ChatResponseOut,
    GeofenceEventOut,
    GPSUpdateIn,
    LoadGeofencesResponseOut,
    NarratePlaceRequestIn,
    NarratePlaceResponseOut,
    PlaceOut,
    TranslateRequestIn,
    TranslateResponseOut,
)
from layer5.chatbot import TourismChatbot
from layer5.geofencing import GeofencingEngine, GPSCoordinate, geofences_from_places
from layer5.multilingual import Language, MultilingualInterface
from layer5.voice_guide import VoiceGuideOrchestrator

logger = logging.getLogger("groundzero.layer5.api")

router = APIRouter(prefix="/companion", tags=["layer5-companion"])


@router.post("/chat", response_model=ChatResponseOut)
async def chat(payload: ChatRequestIn, bot: TourismChatbot = Depends(get_chatbot)) -> ChatResponseOut:
    response_text, bot_msg = await bot.process_message(payload.message)
    return ChatResponseOut(
        response=response_text,
        intent=(bot_msg.intent.value if bot_msg.intent else "unknown"),
        confidence=bot_msg.confidence,
    )


@router.get("/places/search", response_model=list[PlaceOut])
async def search_places(
    query: str = "", category: str | None = None, bot: TourismChatbot = Depends(get_chatbot)
) -> list[PlaceOut]:
    results = await bot.search_places(query, category)
    return [PlaceOut(**r) for r in results]


@router.get("/places/nearby", response_model=list[PlaceOut])
async def nearby_places(
    latitude: float, longitude: float, radius_m: int = 500, bot: TourismChatbot = Depends(get_chatbot)
) -> list[PlaceOut]:
    results = await bot.get_nearby_places(latitude, longitude, radius_m)
    return [PlaceOut(**r) for r in results]


@router.post("/geofences/load", response_model=LoadGeofencesResponseOut)
async def load_geofences(
    user: User = Depends(get_current_user),
    place_repo: PlaceRepository = Depends(get_place_repository),
    engine: GeofencingEngine = Depends(get_geofencing_engine),
) -> LoadGeofencesResponseOut:
    """Seed the geofencing engine from the real place catalog. Call this
    once at trip start (or after adding pinned/custom places) — before
    this fix there was no way to get real geofences into the engine at
    all. Requires a signed-in user: `engine` is now a per-user instance
    (see layer5/api/dependencies.py) rather than one shared singleton."""
    places = await place_repo.list_all()
    fences = geofences_from_places(places)
    engine.add_geofences(fences)
    return LoadGeofencesResponseOut(loaded_count=len(fences))


@router.post("/geofences/gps", response_model=list[GeofenceEventOut])
async def update_gps(
    payload: GPSUpdateIn,
    user: User = Depends(get_current_user),
    engine: GeofencingEngine = Depends(get_geofencing_engine),
) -> list[GeofenceEventOut]:
    from datetime import datetime, timezone

    gps = GPSCoordinate(
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
        timestamp=datetime.now(timezone.utc),
    )
    events = engine.update_gps(gps)
    return [
        GeofenceEventOut(
            event_type=e.event_type, place_id=e.place_id, place_name=e.place_name,
            latitude=e.latitude, longitude=e.longitude,
        )
        for e in events
    ]


@router.post("/translate", response_model=TranslateResponseOut)
async def translate(payload: TranslateRequestIn, ml: MultilingualInterface = Depends(get_multilingual_interface)) -> TranslateResponseOut:
    try:
        target = Language(payload.target_language)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported target_language: {payload.target_language!r}")

    text, was_translated = await ml.translator.translate(payload.text, target)
    return TranslateResponseOut(text=text, target_language=target.value, translation_available=was_translated)


@router.post("/narrate", response_model=NarratePlaceResponseOut)
async def narrate_place(
    payload: NarratePlaceRequestIn,
    place_repo: PlaceRepository = Depends(get_place_repository),
    voice: VoiceGuideOrchestrator = Depends(get_voice_guide),
) -> NarratePlaceResponseOut:
    place = await place_repo.get_by_id(payload.place_id)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place {payload.place_id} not found")

    place_dict = {"name": place.name, "category": place.category, "description": place.description}
    narration = await voice.tts.narrate_place(place_dict, payload.language)
    return NarratePlaceResponseOut(
        text=narration.text,
        language=narration.language,
        audio_url=narration.audio_url,
        duration_seconds=narration.duration_seconds,
    )
