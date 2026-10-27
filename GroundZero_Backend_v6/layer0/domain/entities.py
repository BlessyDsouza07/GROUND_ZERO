"""
Domain entities for Layer 0 — Background Engine.

These are plain dataclasses with zero framework dependencies (no SQLAlchemy,
no Pydantic). The infrastructure layer maps them to/from ORM models and API
schemas. Keeping them framework-free is what makes "Clean Architecture" more
than a buzzword here: the domain doesn't know Postgres or FastAPI exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PriceBand(str, Enum):
    FREE = "free"
    BUDGET = "budget"
    MODERATE = "moderate"
    PREMIUM = "premium"


class CrowdLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VARIABLE = "variable"


class EnergyRequirement(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class Grade(str, Enum):
    """Derived from bias_index; see BiasAuditService.grade_for()."""
    AUTHENTIC = "authentic"        # bias_index < 0.3
    BALANCED = "balanced"          # 0.3 <= bias_index < 0.6
    COMMERCIALISED = "commercialised"  # bias_index >= 0.6


class DataSource(str, Enum):
    OSM = "openstreetmap"
    WIKIDATA = "wikidata"
    WIKIPEDIA = "wikipedia"
    KARNATAKA_TOURISM = "karnataka_tourism"
    LOCAL_LISTING = "local_listing"
    COMMUNITY_SUBMISSION = "community_submission"
    TOURIST_ADDED = "tourist_added"  # a tourist's own pick, added via their itinerary (not a public community submission)
    WEATHER_API = "weather_api"
    TIDE_API = "tide_api"
    EVENT_RSS = "event_rss"


@dataclass
class Coordinates:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(f"Invalid longitude: {self.longitude}")


@dataclass
class AccessibilityInfo:
    tags: list[str] = field(default_factory=list)  # e.g. ["stairs-only", "uneven-terrain"]
    wheelchair: Optional[bool] = None
    stairs: Optional[bool] = None
    sensory_notes: Optional[str] = None


@dataclass
class OpeningHours:
    """Structured opening hours, not a raw OSM string, so Hard Filters can
    reason about them without re-parsing text at query time."""
    raw: str  # original OSM opening_hours tag, kept for auditability
    days_open: list[str] = field(default_factory=list)  # ["mon","tue",...]
    opens_at: Optional[str] = None   # "09:00"
    closes_at: Optional[str] = None  # "18:00"


@dataclass
class BiasSignals:
    """Raw inputs to the Bias Index formula (blueprint 3.2). Kept separate
    from the derived bias_index so the audit is always re-computable and
    explainable, not just a stored magic number."""
    media_mentions: int = 0
    local_percentage: float = 0.0       # 0..1, fraction of visitors who are local
    commercial_flags: int = 0           # souvenir density / inflated fees / sponsored signals, count
    tourist_popularity: float = 0.0     # 0..1, normalized popularity signal
    sponsored_indicator: bool = False


@dataclass
class Place:
    id: Optional[str]
    name: str
    category: str
    coordinates: Coordinates

    opening_hours: OpeningHours
    price_band: PriceBand
    estimated_cost: float  # INR

    tags: list[str] = field(default_factory=list)

    bias_signals: BiasSignals = field(default_factory=BiasSignals)
    bias_index: Optional[float] = None       # 0 (authentic) .. 1 (commercialised)
    grade: Optional[Grade] = None

    energy_requirement: EnergyRequirement = EnergyRequirement.MODERATE
    crowd_level: CrowdLevel = CrowdLevel.MODERATE
    season_suitability: list[str] = field(default_factory=list)  # ["monsoon","winter",...]
    tide_dependency: bool = False
    dwell_time_typical_minutes: int = 45

    accessibility: AccessibilityInfo = field(default_factory=AccessibilityInfo)
    parking: Optional[bool] = None
    washrooms: Optional[bool] = None
    food_available: Optional[bool] = None
    pet_friendly: Optional[bool] = None
    family_friendly: Optional[bool] = None
    kid_friendly: Optional[bool] = None
    photography_allowed: Optional[bool] = None
    best_time: Optional[str] = None  # "sunrise", "sunset", "morning", ...

    freshness_score: float = 0.0
    last_verified_at: Optional[datetime] = None
    temporarily_unavailable: bool = False

    etiquette_tag: Optional[str] = None
    source: list[DataSource] = field(default_factory=list)
    description: Optional[str] = None
    wiki_summary: Optional[str] = None
    transport_access: Optional[str] = None

    # SECURITY FIX (final-release-hardening pass, Oct 2026): "verified"
    # (the default, and what every ETL/community-approved/legacy place
    # is) vs "pending" — a brand-new tourist-added place
    # (CustomPlaceService.add_or_find), not yet reviewed by an admin.
    # HiveEngine's general recommendation pool and GET /places both
    # exclude "pending" places; pinning one into the trip that added it
    # still works regardless of status (resolved by id, not by list_all's
    # filtered pool) — see custom_place_service.py's module docstring.
    verification_status: str = "verified"

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_outdoor(self) -> bool:
        return "outdoor" in self.tags or self.category in {
            "beach", "viewpoint", "park", "garden", "waterfall", "trail",
        }


@dataclass
class CommunitySubmission:
    """A locally submitted hidden gem, per blueprint 3.1 source #7. Enters
    the Master Data Core only after admin approval — never auto-merged."""
    id: Optional[str]
    submitted_place: Place
    submitter_note: Optional[str]
    status: str = "pending"  # pending | approved | rejected
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    # SECURITY FIX (final-release-hardening pass, Oct 2026): who submitted
    # this, so a submitter can eventually be shown/manage only their own
    # submissions instead of every signed-in user being able to see or act
    # on everyone else's pending queue the same way. Optional — layer0 also
    # runs standalone (layer0/main.py) with no `auth`/`users` table on its
    # own sys.path at all, same as layer1/TouristProfile.user_id; no FK to
    # `users` for the same reason. GET /admin/submissions (admin-only) is
    # unaffected either way — admins already see every submission.
    submitter_user_id: Optional[str] = None
