from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MoodOut(BaseModel):
    slug: str
    label: str
    tagline: str


class RightNowOut(BaseModel):
    headline: str  # "A GOOD MORNING IN MANGALURU" / "SUNSET IS GETTING CLOSE" / ...
    now_local: str
    weather_available: bool
    temperature_celsius: Optional[float]
    condition: Optional[str]
    is_rain: Optional[bool]
    tide_available: bool
    tide_state: Optional[str]
    tide_source: Optional[str]
    sunset_local: str
    minutes_to_sunset: int
    events_today_count: Optional[int]
    weather_note: Optional[str]   # "RAIN MOVING IN - maybe skip the exposed coast" style, or None
    tide_note: Optional[str]      # "TIDE RISING - good for a waterfront walk" style, or None


class WhyNowOut(BaseModel):
    headline: str                  # "SUNSET IN 38 MINUTES"
    reasons: list[str]


class WhyThisPickOut(BaseModel):
    matches_selected_mood: bool
    fits_available_time: bool
    suitable_current_conditions: bool
    lower_expected_crowd: bool


class PlaceCardOut(BaseModel):
    place_id: str
    name: str
    category: str
    tags: list[str]
    latitude: float
    longitude: float
    price_band: str
    estimated_cost: float
    dwell_minutes: int
    crowd_level: str
    best_time: Optional[str]
    grade: Optional[str]
    media_mentions: int
    provenance: str                # "verified" | "community"
    image_url: Optional[str]       # None today — see README_EXPLORE.md
    distance_km: Optional[float]
    why_now: WhyNowOut
    open_state: Optional[str] = None   # open | closed | unknown
    open_label: Optional[str] = None
    open_source: Optional[str] = None  # listed | typical | none


class PickOut(PlaceCardOut):
    fit_percent: int
    why_this_pick: WhyThisPickOut


class BeyondTheObviousOut(PlaceCardOut):
    why_found_this: str


class ExperienceCategoryOut(BaseModel):
    slug: str
    label: str
    preview: list[PlaceCardOut]
    total_count: int


class SearchResultOut(BaseModel):
    results: list[PlaceCardOut]
    suggested_searches: list[str]


class EventOut(BaseModel):
    id: int
    title: str
    start_at: Optional[str]
    venue: Optional[str]
    address: Optional[str]
    source_url: str


class PlaceDetailOut(BaseModel):
    place_id: str
    name: str
    category: str
    tags: list[str]
    tagline: str                    # "QUIET COAST, MANGALURU" style
    latitude: float
    longitude: float
    why_go: str
    good_for: list[str]
    why_now: WhyNowOut
    price_band: str
    estimated_cost: float
    opening_hours_raw: str
    etiquette_tag: Optional[str]
    grade: Optional[str]
    provenance: str
    image_url: Optional[str]


class AddToJourneyIn(BaseModel):
    place_id: str
    trip_id: Optional[str] = None


class AddToJourneyOut(BaseModel):
    status: str  # "added" | "no_active_trip"
    trip_id: Optional[str] = None
    trip_place_id: Optional[str] = None
    message: str


class SituationOut(BaseModel):
    situation: str            # stay | transit | place | outdoors
    near_name: Optional[str]
    headline: str
    detail: str
    kind: str                 # food | stay | rest | explore
    accuracy_m: Optional[float] = None
    now_local: str
    suggestions: list[PlaceCardOut]
