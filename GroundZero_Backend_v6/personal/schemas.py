from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Mirrors layer0.api.schemas._PRICE_BAND exactly (kept as its own
# Literal, not a shared import, for the same HTTP-boundary-decoupling
# reason given there) — audit fix: this used to be a bare `str`, so
# "budjet" or "Budget" would silently pass validation and then not
# match anything downstream that switches on the real price bands.
_PRICE_BAND = Literal["free", "budget", "moderate", "premium"]


# ---------------------------------------------------------------------------
# Contributions
# ---------------------------------------------------------------------------
class AddPlaceIn(BaseModel):
    """"+ ADD A PLACE" — goes through the real layer0 Community
    Submission -> Review -> Master Data pipeline, the same as the other
    four kinds funnel through PersonalService, just logged (see
    README_PERSONAL.md for which kinds have a wired-up review step and
    which are honestly still "received, not yet reviewable")."""
    name: str
    category: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    estimated_cost: float = Field(default=0.0, ge=0)
    price_band: _PRICE_BAND = "budget"
    description: Optional[str] = None
    note: Optional[str] = Field(default=None, description="Why this place/update matters, from the contributor")
    media_url: Optional[str] = Field(default=None, description="Photo the contributor took or chose (uploaded via /media/upload)")


class SuggestUpdateIn(BaseModel):
    """"Suggest an update" — a correction to one field on an existing,
    already-published place."""
    place_id: str
    field: str = Field(description="Which place attribute this is about, e.g. 'opening_hours', 'price_band'")
    current_value: Optional[str] = None
    suggested_value: str
    reason: Optional[str] = None


class LocalTipIn(BaseModel):
    """"Share a local tip" — stored and shown as a community tip,
    never merged into the place's own authoritative attributes (see
    PersonalService.submit_local_tip)."""
    place_id: str
    tip: str
    best_time: Optional[str] = None
    context: Optional[str] = None


class ReportIncorrectIn(BaseModel):
    """"Report incorrect information" on an existing place."""
    place_id: str
    issue_type: str = Field(description="e.g. 'wrong_hours', 'closed_down', 'wrong_location', 'wrong_price'")
    description: str
    evidence: Optional[str] = None


class AddMediaIn(BaseModel):
    """"Add useful media" to an existing place. `media_url` is a
    placeholder the same way Journal's is — no object-storage upload
    pipeline exists in this backend yet (see README_PERSONAL.md)."""
    place_id: str
    media_url: str
    caption: Optional[str] = None
    source: Optional[str] = None


class ContributionOut(BaseModel):
    contribution_id: str
    kind: str  # add_place | suggest_update | local_tip | report_incorrect | add_media
    submission_id: Optional[str] = None
    place_id: Optional[str] = None
    place_name: str
    status: str  # pending | approved | rejected
    submitted_at: datetime
    reviewed_at: Optional[datetime]
    # Impact framing is the primary message; points are secondary and
    # only shown once a submission is approved — never fabricated for a
    # pending one.
    impact_message: str
    explorer_points: Optional[int]


class MyContributionsOut(BaseModel):
    contributions: list[ContributionOut]
    total_approved: int
    explorer_level: str  # Explorer / Pathfinder / Local Guide / Insider / Pioneer — quiet, no leaderboard


# ---------------------------------------------------------------------------
# Notifications — four categories, bundled, computed per-request from
# real data. No table, nothing stored, nothing fabricated.
# ---------------------------------------------------------------------------
class NotificationOut(BaseModel):
    id: str  # stable within one response, derived from its content — not persisted
    category: str  # NOW | YOUR_JOURNEY | AROUND_YOU | GROUNDZERO
    headline: str
    body: str


class NotificationsOut(BaseModel):
    notifications: list[NotificationOut]


# ---------------------------------------------------------------------------
# Saved Places — a persistent bookmark, independent of any trip.
# ---------------------------------------------------------------------------
class SavedPlaceOut(BaseModel):
    saved_place_id: str
    place_id: str
    place_name: str
    category: str
    saved_at: datetime


class SavedPlacesOut(BaseModel):
    saved_places: list[SavedPlaceOut]
