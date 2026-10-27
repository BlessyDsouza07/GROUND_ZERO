"""
Personal Fit Score (blueprint Table 4, verified against the worked
examples in Table 10):

  raw_score = (0.30 × companion_score)
            + (0.20 × energy_score)
            + (0.20 × curiosity_score)
            + (0.15 × crowd_score)
            + (0.15 × time_score)

  personal_fit = raw_score × (1 − bias_index)

No approximation of the weights — they are hardcoded exactly as specified,
not "tuned" or rounded differently. See tests for verification against
Table 10's three worked examples (Milagres Church, Summer Sands Resort,
Mrs. Lobo's Home Kitchen).
"""
from __future__ import annotations

from dataclasses import dataclass

from layer0.domain.entities import CrowdLevel, EnergyRequirement, Place
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.domain.entities import CrowdTolerance, EnergyBand, Purpose, StartTimePreference, TouristProfile

WEIGHT_COMPANION = 0.30
WEIGHT_ENERGY = 0.20
WEIGHT_CURIOSITY = 0.20
WEIGHT_CROWD = 0.15
WEIGHT_TIME = 0.15

# Purpose -> place category affinity. A place's category scores highly
# against the purpose it most directly serves; everything else gets a
# baseline so no category is ever zeroed out by purpose alone.
_PURPOSE_CATEGORY_AFFINITY: dict[Purpose, set[str]] = {
    Purpose.CULTURAL: {"heritage_site", "museum", "art_gallery", "library", "theatre"},
    Purpose.FOODIE: {"restaurant", "cafe", "street_food", "local_kitchen", "food_court", "bakery", "dessert_shop", "market"},
    Purpose.ADVENTURE: {"nature_spot", "waterfall", "trail", "adventure"},
    Purpose.LEISURE: {"park", "garden", "beach", "viewpoint", "shopping_mall"},
    Purpose.SPIRITUAL: {"heritage_site"},  # temples/churches/mosques mapped to heritage_site in Layer 0
}

_ENERGY_ORDER = [EnergyBand.LOW, EnergyBand.MODERATE, EnergyBand.HIGH]
_PLACE_ENERGY_ORDER = [EnergyRequirement.LOW, EnergyRequirement.MODERATE, EnergyRequirement.HIGH]

_CROWD_TOLERANCE_ORDER = [
    CrowdTolerance.AVOID_ENTIRELY, CrowdTolerance.PREFER_QUIET, CrowdTolerance.FINE, CrowdTolerance.LOVE_THEM,
]
_CROWD_LEVEL_ORDER = [CrowdLevel.LOW, CrowdLevel.MODERATE, CrowdLevel.HIGH, CrowdLevel.HIGH]  # VARIABLE treated as HIGH-risk


@dataclass(frozen=True)
class FitBreakdown:
    companion_score: float
    energy_score: float
    curiosity_score: float
    crowd_score: float
    time_score: float
    raw_score: float
    bias_index: float
    personal_fit: float


class PersonalFitScoreService:
    def __init__(self, curiosity_extractor: CuriosityExtractor):
        self.curiosity_extractor = curiosity_extractor

    def _companion_score(self, place: Place, profile: TouristProfile) -> float:
        affinity_categories = _PURPOSE_CATEGORY_AFFINITY.get(profile.purpose, set())
        if profile.purpose == Purpose.UNDECIDED:
            return 0.6  # neutral-positive baseline; nothing to optimize against
        return 1.0 if place.category in affinity_categories else 0.4

    def _energy_score(self, place: Place, profile: TouristProfile) -> float:
        tourist_idx = _ENERGY_ORDER.index(profile.energy_band)
        place_idx = _PLACE_ENERGY_ORDER.index(place.energy_requirement)
        distance = abs(tourist_idx - place_idx)
        return max(0.0, 1.0 - 0.5 * distance)  # exact match=1.0, one band off=0.5, two off=0.0

    def _curiosity_score(self, place: Place, profile: TouristProfile) -> float:
        return self.curiosity_extractor.affinity_for_category(
            profile.curiosity_vector, place.category, place.tags
        )

    def _crowd_score(self, place: Place, profile: TouristProfile) -> float:
        if profile.crowd_tolerance == CrowdTolerance.AVOID_ENTIRELY and place.crowd_level in (
            CrowdLevel.HIGH, CrowdLevel.VARIABLE,
        ):
            return 0.0
        tolerance_idx = _CROWD_TOLERANCE_ORDER.index(profile.crowd_tolerance)
        level_idx = _CROWD_LEVEL_ORDER.index(place.crowd_level)
        # tolerance_idx and level_idx are both on a 0..3 "low tolerance/low
        # crowd" -> "high tolerance/high crowd" scale; mismatch in the
        # direction of "more crowd than tolerance allows" is penalized harder
        # than "less crowd than tolerance allows" (which is never a problem).
        if level_idx <= tolerance_idx:
            return 1.0
        distance = level_idx - tolerance_idx
        return max(0.0, 1.0 - 0.4 * distance)

    def _time_score(self, place: Place, profile: TouristProfile, scheduled_hour: int) -> float:
        best_time_map = {
            "sunrise": range(5, 8), "morning": range(6, 11), "sunset": range(17, 19),
            "afternoon": range(12, 17), "evening": range(17, 21), "night": range(19, 24),
        }
        if not place.best_time or place.best_time not in best_time_map:
            return 0.75  # no strong preference known -> mildly-good default, not full marks
        return 1.0 if scheduled_hour in best_time_map[place.best_time] else 0.5

    def _start_hour_for(self, profile: TouristProfile) -> int:
        return {
            StartTimePreference.MORNING: 8,
            StartTimePreference.MID_MORNING: 10,
            StartTimePreference.AFTERNOON: 13,
            StartTimePreference.FLEXIBLE: 10,
        }[profile.start_time_preference]

    def score(self, place: Place, profile: TouristProfile, scheduled_hour: int | None = None) -> FitBreakdown:
        hour = scheduled_hour if scheduled_hour is not None else self._start_hour_for(profile)

        companion = self._companion_score(place, profile)
        energy = self._energy_score(place, profile)
        curiosity = self._curiosity_score(place, profile)
        crowd = self._crowd_score(place, profile)
        time_ = self._time_score(place, profile, hour)

        raw_score = (
            WEIGHT_COMPANION * companion
            + WEIGHT_ENERGY * energy
            + WEIGHT_CURIOSITY * curiosity
            + WEIGHT_CROWD * crowd
            + WEIGHT_TIME * time_
        )
        bias_index = place.bias_index if place.bias_index is not None else 0.5
        personal_fit = raw_score * (1 - bias_index)

        return FitBreakdown(
            companion_score=round(companion, 4),
            energy_score=round(energy, 4),
            curiosity_score=round(curiosity, 4),
            crowd_score=round(crowd, 4),
            time_score=round(time_, 4),
            raw_score=round(raw_score, 4),
            bias_index=round(bias_index, 4),
            personal_fit=round(personal_fit, 4),
        )
