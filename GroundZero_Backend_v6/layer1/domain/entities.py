"""
Domain entities for Layer 1 — Soul Survey.

TouristProfile mirrors blueprint Section 4.8 exactly:

  TouristProfile {
    id, purpose, energy_band, crowd_tolerance, budget,
    dietary_flags[], group_config, group_session_id,
    curiosity_text, curiosity_vector[],
    trip_duration_hours,    <- NEW Q8
    start_time_preference,  <- NEW Q9
    accessibility_flags[],  <- NEW
    companion_language,     <- NEW
    voice_personality,
    return_visitor_exclusions[], <- NEW
    created_at
  }
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Purpose(str, Enum):
    CULTURAL = "cultural"
    FOODIE = "foodie"
    ADVENTURE = "adventure"
    LEISURE = "leisure"
    SPIRITUAL = "spiritual"
    UNDECIDED = "undecided"


class CrowdTolerance(str, Enum):
    LOVE_THEM = "love_them"
    FINE = "fine"
    PREFER_QUIET = "prefer_quiet"
    AVOID_ENTIRELY = "avoid_entirely"


class DietaryFlag(str, Enum):
    VEG = "veg"
    VEGAN = "vegan"
    NO_BEEF = "no_beef"
    HALAL = "halal"
    NO_RESTRICTIONS = "no_restrictions"


class GroupConfig(str, Enum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    FRIENDS = "friends"


class TripDuration(str, Enum):
    HALF_DAY = "half_day"      # 4 hrs
    FULL_DAY = "full_day"      # 8 hrs
    MULTI_DAY = "multi_day"


class StartTimePreference(str, Enum):
    MORNING = "morning"                # 7-9 AM
    MID_MORNING = "mid_morning"        # 9-11 AM
    AFTERNOON = "afternoon"            # 11 AM-2 PM
    FLEXIBLE = "flexible"


class AccessibilityFlag(str, Enum):
    WHEELCHAIR = "wheelchair"
    LIMITED_WALKING = "limited_walking"
    VISUAL_IMPAIRMENT = "visual_impairment"
    HEARING_IMPAIRMENT = "hearing_impairment"
    NONE = "none"


class CompanionLanguage(str, Enum):
    ENGLISH = "english"
    KANNADA = "kannada"
    KONKANI = "konkani"
    HINDI = "hindi"


class VoicePersonality(str, Enum):
    WARM_LOCAL_FRIEND = "warm_local_friend"
    CALM_HISTORIAN = "calm_historian"
    WITTY_COMPANION = "witty_companion"


class EnergyBand(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass
class CuriosityVector:
    """Derived from Q7's free text (blueprint: 'the most important input').
    A sparse weighted map of category/tag -> affinity score in [0, 1], used
    directly by Layer 2's curiosity_score component of the Personal Fit
    Score formula."""
    weights: dict[str, float] = field(default_factory=dict)

    def top(self, n: int = 5) -> list[tuple[str, float]]:
        return sorted(self.weights.items(), key=lambda kv: kv[1], reverse=True)[:n]


@dataclass
class TouristProfile:
    id: Optional[str]
    purpose: Purpose
    energy_band: EnergyBand
    crowd_tolerance: CrowdTolerance
    budget: float  # INR, total for the day

    device_id: Optional[str] = None  # needed for Return Visitor Check (4.5) to find a prior session
    dietary_flags: list[DietaryFlag] = field(default_factory=list)
    group_config: GroupConfig = GroupConfig.SOLO
    group_session_id: Optional[str] = None

    curiosity_text: str = ""
    curiosity_vector: CuriosityVector = field(default_factory=CuriosityVector)

    trip_duration_hours: TripDuration = TripDuration.FULL_DAY
    multi_day_count: Optional[int] = None  # only meaningful when trip_duration_hours == MULTI_DAY
    start_time_preference: StartTimePreference = StartTimePreference.FLEXIBLE

    accessibility_flags: list[AccessibilityFlag] = field(default_factory=list)
    companion_language: CompanionLanguage = CompanionLanguage.ENGLISH
    voice_personality: VoicePersonality = VoicePersonality.WARM_LOCAL_FRIEND

    return_visitor_exclusions: list[str] = field(default_factory=list)  # place IDs

    created_at: Optional[datetime] = None

    # SECURITY FIX (final-release-hardening pass, Oct 2026): the signed-in
    # user this profile belongs to, when finalized through THIS app's
    # /trips/survey/*/finalize (trips/survey_service.py already has the
    # real authenticated user's id on hand there — SurveySession.user_id,
    # itself set by this same pass's survey-ownership fix). Optional —
    # not required — because layer1 also runs standalone (layer1/main.py)
    # with no `auth`/`users` table on its own sys.path at all; a profile
    # created there has no user to record and stays unrestricted, same
    # trust boundary shared/ownership.py already documented before this
    # field existed. Where it IS set, it is the authoritative ownership
    # record — see shared/ownership.py, which now checks this directly
    # instead of inferring ownership from a TripEvent log.
    user_id: Optional[str] = None

    def new_group_session(self) -> str:
        self.group_session_id = str(uuid.uuid4())
        return self.group_session_id
