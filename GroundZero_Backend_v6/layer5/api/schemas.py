from __future__ import annotations

from pydantic import BaseModel


class ChatRequestIn(BaseModel):
    message: str


class ChatResponseOut(BaseModel):
    response: str
    intent: str
    confidence: float


class PlaceOut(BaseModel):
    id: str | None
    name: str
    category: str
    latitude: float
    longitude: float
    description: str | None = None
    estimated_cost: float | None = None
    bias_index: float | None = None
    grade: str | None = None
    distance_meters: float | None = None


class GPSUpdateIn(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float = 10.0


class GeofenceEventOut(BaseModel):
    event_type: str
    place_id: str
    place_name: str
    latitude: float
    longitude: float


class LoadGeofencesResponseOut(BaseModel):
    loaded_count: int


class TranslateRequestIn(BaseModel):
    text: str
    target_language: str  # one of layer5.multilingual.Language values, e.g. "kn"


class TranslateResponseOut(BaseModel):
    text: str
    target_language: str
    translation_available: bool


class NarratePlaceRequestIn(BaseModel):
    place_id: str
    language: str = "en"


class NarratePlaceResponseOut(BaseModel):
    text: str
    language: str
    audio_url: str | None
    duration_seconds: float
