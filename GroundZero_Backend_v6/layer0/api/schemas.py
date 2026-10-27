"""Pydantic schemas for Layer 0's HTTP boundary. Kept separate from the
domain dataclasses in domain/entities.py — the API shape is allowed to
evolve independently of the internal model."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Mirrors layer0.domain.entities.PriceBand's values exactly — kept as a
# plain Literal here (not an import of the enum) so this HTTP-boundary
# schema file stays decoupled from the domain module, per this file's
# own docstring.
_PRICE_BAND = Literal["free", "budget", "moderate", "premium"]


class PlaceOut(BaseModel):
    id: str
    name: str
    category: str
    latitude: float
    longitude: float
    opening_hours: str
    days_open: list[str]
    estimated_cost: float
    price_band: str
    tags: list[str]
    local_percentage: float
    media_mentions: int
    bias_index: Optional[float]
    grade: Optional[str]
    energy_requirement: str
    crowd_level: str
    season_suitability: list[str]
    tide_dependency: bool
    dwell_time_typical: int
    accessibility_tags: list[str]
    wheelchair: Optional[bool]
    stairs: Optional[bool]
    sensory_notes: Optional[str]
    parking: Optional[bool]
    washrooms: Optional[bool]
    food_available: Optional[bool]
    pet_friendly: Optional[bool]
    family_friendly: Optional[bool]
    kid_friendly: Optional[bool]
    photography_allowed: Optional[bool]
    best_time: Optional[str]
    freshness_score: float
    last_verified_at: Optional[datetime]
    temporarily_unavailable: bool
    etiquette_tag: Optional[str]
    source: list[str]
    description: Optional[str]
    wiki_summary: Optional[str]
    transport_access: Optional[str]


class CommunitySubmissionIn(BaseModel):
    name: str
    category: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    estimated_cost: float = Field(default=0.0, ge=0)
    price_band: _PRICE_BAND = "budget"
    description: Optional[str] = None
    submitter_note: Optional[str] = Field(default=None, description="Why this place matters, from the submitter")


class CommunitySubmissionOut(BaseModel):
    id: str
    status: str
    submitted_at: datetime
    place_name: str


class SubmissionReviewIn(BaseModel):
    reviewed_by: str


class CustomPlaceIn(BaseModel):
    """A tourist adding their own place — either one they found via
    search_nearby and want reused as-is, or a brand-new pin+name if it
    genuinely isn't in the system yet."""
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    category: Optional[str] = Field(default=None, description="Best guess is fine — matching ignores this field")
    note: Optional[str] = Field(default=None, description="Anything the tourist wants remembered about this place")
    estimated_cost: float = Field(default=0.0, ge=0)


class CustomPlaceOut(BaseModel):
    place: PlaceOut
    was_newly_created: bool = Field(
        description="True if this place didn't exist in the Master Data Core and was just added from the "
        "tourist's own input; False if it matched an existing place and that one was reused instead."
    )


class EtlRunReportOut(BaseModel):
    started_at: datetime
    finished_at: Optional[datetime]
    osm_elements_collected: int
    wikidata_enriched: int
    wikipedia_enriched: int
    places_after_dedup: int
    places_stored: int
    sources_skipped: list[str]
    errors: list[str]
