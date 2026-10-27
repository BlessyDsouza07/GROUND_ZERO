from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class StartSurveyIn(BaseModel):
    device_id: Optional[str] = None
    join_group_session_id: Optional[str] = None


class SurveyStateOut(BaseModel):
    session_id: str
    current_step: str
    progress_fraction: float
    is_complete: bool


class AnswerIn(BaseModel):
    answer: Any


class TouristProfileOut(BaseModel):
    id: str
    purpose: str
    energy_band: str
    crowd_tolerance: str
    budget: float
    dietary_flags: list[str]
    group_config: str
    group_session_id: Optional[str]
    curiosity_text: str
    curiosity_vector: dict[str, float]
    trip_duration_hours: str
    multi_day_count: Optional[int]
    start_time_preference: str
    accessibility_flags: list[str]
    companion_language: str
    voice_personality: str
    return_visitor_exclusions: list[str]


class MarkVisitedIn(BaseModel):
    place_ids: list[str]


class MarkVisitedOut(BaseModel):
    profile_id: str
    visited_place_ids: list[str]


class VisitedPlaceOut(BaseModel):
    place_id: str
    name: str
    category: str
