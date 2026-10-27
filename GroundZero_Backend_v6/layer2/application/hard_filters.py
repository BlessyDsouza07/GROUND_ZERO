"""
Hard Filters (blueprint 5.1 + Table 11 step 6). A place surviving Hard
Filters is merely *eligible* — Personal Fit Score decides if it's *good*.
Every filter here is a hard boolean exclusion, never a soft penalty.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from layer0.application.accessibility import AccessibilityDetector
from layer0.application.freshness import FreshnessService
from layer0.application.opening_hours_parser import OpeningHoursParser
from layer0.domain.entities import Place
from layer1.domain.entities import TouristProfile, TripDuration

_TRIP_DURATION_HOURS = {
    TripDuration.HALF_DAY: 4,
    TripDuration.FULL_DAY: 8,
    TripDuration.MULTI_DAY: 8,  # per-day budget; multi-day count handled by caller
}


@dataclass(frozen=True)
class FilterResult:
    place_id: str
    passed: bool
    rejection_reasons: list[str]


class HardFilterService:
    def __init__(
        self,
        accessibility_detector: AccessibilityDetector,
        freshness_service: FreshnessService,
        freshness_min_score: float = 0.4,
        opening_hours_parser: OpeningHoursParser | None = None,
        use_typical_hours: bool = False,
    ):
        self.accessibility_detector = accessibility_detector
        self.freshness_service = freshness_service
        self.freshness_min_score = freshness_min_score
        self.opening_hours_parser = opening_hours_parser or OpeningHoursParser()
        self.use_typical_hours = use_typical_hours

    def is_open_at(self, place: Place, at: datetime) -> bool:
        """Public entry point for opening-hours checks outside Hard
        Filters' own pipeline — used by the post-scheduling re-validation
        in hive_engine.py, which needs to check a place against its own
        scheduled visit time (not the trip's single start_time)."""
        return not self._is_closed(place, at)

    def _is_closed(self, place: Place, at: datetime) -> bool:
        # Uses the raw OSM string directly via the real opening_hours
        # parser, not the summary opens_at/closes_at fields. Confirmed by
        # an architectural audit: the previous time-only comparison never
        # checked day-of-week at all — a place closed every Sunday would
        # have incorrectly read as "open" any Sunday whose time-of-day
        # fell inside the stored window. is_open_at() handles day-of-week,
        # multi-window schedules, and overnight hours correctly by asking
        # the real parser rather than approximating.
        is_open = self.opening_hours_parser.is_open_at(place.opening_hours.raw, at)
        if is_open is None:
            # No listed hours: fall back to the usual timings for this kind of
            # place, so a trip never schedules a beach at 11 pm or a temple at 2 pm.
            if not self.use_typical_hours:
                return False
            try:
                from explore.hours import open_info

                info = open_info(place, self.opening_hours_parser, at)
                return info.state == "closed"
            except Exception:  # noqa: BLE001
                return False
        return not is_open

    def evaluate(
        self,
        place: Place,
        profile: TouristProfile,
        at: datetime,
        remaining_budget: float,
    ) -> FilterResult:
        reasons: list[str] = []

        if self._is_closed(place, at):
            reasons.append("closed at scheduled time")

        if place.estimated_cost > remaining_budget:
            reasons.append("outside remaining budget")

        max_hours = _TRIP_DURATION_HOURS[profile.trip_duration_hours]
        if place.dwell_time_typical_minutes > max_hours * 60:
            reasons.append("dwell time exceeds trip duration window")

        blocking_tags = self.accessibility_detector.blocks_for([f.value for f in profile.accessibility_flags])
        if blocking_tags & set(place.accessibility.tags):
            reasons.append(f"accessibility mismatch: {sorted(blocking_tags & set(place.accessibility.tags))}")

        if not self.freshness_service.is_fresh_enough(place, self.freshness_min_score, now=at):
            reasons.append(f"freshness_score below {self.freshness_min_score}")

        if place.id and place.id in profile.return_visitor_exclusions:
            reasons.append("already visited on a prior trip (return visitor exclusion)")

        if place.temporarily_unavailable:
            reasons.append("temporarily unavailable")

        return FilterResult(place_id=place.id or "", passed=(len(reasons) == 0), rejection_reasons=reasons)

    def filter_candidates(
        self,
        places: list[Place],
        profile: TouristProfile,
        at: datetime,
        remaining_budget: float,
    ) -> list[Place]:
        survivors = []
        for place in places:
            result = self.evaluate(place, profile, at, remaining_budget)
            if result.passed:
                survivors.append(place)
        return survivors
