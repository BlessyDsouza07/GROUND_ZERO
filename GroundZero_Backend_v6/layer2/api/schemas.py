from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RecommendationRequestIn(BaseModel):
    profile_id: str
    start_time: datetime | None = None  # defaults to now if omitted
    pinned_place_ids: list[str] = []  # places the tourist added themselves (see /places/custom) — see hive_engine.build_recommendation_queue
    start_latitude: float | None = None  # tourist's real position at trip-start — enables the reachability geofence
    start_longitude: float | None = None


class RecommendationItemOut(BaseModel):
    place_id: str
    place_name: str
    role: str
    scheduled_time: datetime
    travel_mode: str
    travel_time_minutes: int
    travel_is_routed: bool = False
    estimated_cost: float
    reason_selected: str
    personal_score: float
    weather_adjusted: bool
    weather_adjustment_note: str | None


class RecommendationQueueOut(BaseModel):
    profile_id: str
    items: list[RecommendationItemOut]
    total_estimated_cost: float
    generated_at: datetime | None
    geofence_radius_km: float | None = None
    slots_requested: int | None = None
    slots_filled: int | None = None
    slots_dropped_closed: int = 0


class MultiDayRecommendationOut(BaseModel):
    days: list[RecommendationQueueOut]
