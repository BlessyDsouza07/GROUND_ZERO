from datetime import datetime, timezone

from layer0.application.accessibility import AccessibilityDetector
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import (
    AccessibilityInfo,
    BiasSignals,
    Coordinates,
    OpeningHours,
    Place,
    PriceBand,
)
from layer1.domain.entities import (
    AccessibilityFlag,
    CrowdTolerance,
    EnergyBand,
    Purpose,
    StartTimePreference,
    TouristProfile,
    TripDuration,
)
from layer2.application.hard_filters import HardFilterService

NOW = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)


def _place(**overrides) -> Place:
    defaults = dict(
        id="p1", name="Test Place", category="cafe",
        coordinates=Coordinates(latitude=12.9, longitude=74.85),
        opening_hours=OpeningHours(raw="", opens_at="09:00", closes_at="18:00"),
        price_band=PriceBand.BUDGET, estimated_cost=200.0,
        bias_signals=BiasSignals(), accessibility=AccessibilityInfo(),
        freshness_score=1.0, last_verified_at=NOW, temporarily_unavailable=False,
        dwell_time_typical_minutes=45,
    )
    defaults.update(overrides)
    return Place(**defaults)


def _profile(**overrides) -> TouristProfile:
    defaults = dict(
        id="prof1", purpose=Purpose.LEISURE, energy_band=EnergyBand.MODERATE,
        crowd_tolerance=CrowdTolerance.FINE, budget=2000.0,
        trip_duration_hours=TripDuration.FULL_DAY,
        start_time_preference=StartTimePreference.MORNING,
    )
    defaults.update(overrides)
    return TouristProfile(**defaults)


def _service() -> HardFilterService:
    return HardFilterService(AccessibilityDetector(), FreshnessService(stale_after_days=180), freshness_min_score=0.4)


def test_open_place_passes():
    result = _service().evaluate(_place(), _profile(), NOW, remaining_budget=2000.0)
    assert result.passed


def test_closed_place_rejected():
    place = _place(opening_hours=OpeningHours(raw="20:00-23:00", opens_at="20:00", closes_at="23:00"))
    result = _service().evaluate(place, _profile(), NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("closed" in r for r in result.rejection_reasons)


def test_closed_place_rejected_by_day_of_week():
    """Regression test: the previous _is_closed() only ever compared
    time-of-day, never day-of-week, so a place closed all day Sunday
    would incorrectly read as 'open' if the time-of-day happened to fall
    inside its stored window. NOW (a Friday, per the module-level
    constant) falls within this place's Sat-only hours' time range, but
    Friday isn't a day this place is open at all."""
    place = _place(opening_hours=OpeningHours(raw="Sa 09:00-18:00", opens_at="09:00", closes_at="18:00"))
    result = _service().evaluate(place, _profile(), NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("closed" in r for r in result.rejection_reasons)


def test_over_budget_rejected():
    place = _place(estimated_cost=5000.0)
    result = _service().evaluate(place, _profile(), NOW, remaining_budget=1000.0)
    assert not result.passed
    assert any("budget" in r for r in result.rejection_reasons)


def test_dwell_time_exceeds_half_day_window_rejected():
    place = _place(dwell_time_typical_minutes=300)  # 5 hours
    profile = _profile(trip_duration_hours=TripDuration.HALF_DAY)  # 4 hour window
    result = _service().evaluate(place, profile, NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("dwell time" in r for r in result.rejection_reasons)


def test_accessibility_mismatch_rejected():
    place = _place(accessibility=AccessibilityInfo(tags=["stairs-only"]))
    profile = _profile()
    profile.accessibility_flags = [AccessibilityFlag.WHEELCHAIR]
    result = _service().evaluate(place, profile, NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("accessibility" in r for r in result.rejection_reasons)


def test_stale_place_rejected():
    place = _place(last_verified_at=None)  # never verified -> freshness 0.0
    result = _service().evaluate(place, _profile(), NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("freshness" in r for r in result.rejection_reasons)


def test_return_visitor_exclusion_rejected():
    place = _place(id="visited-place")
    profile = _profile()
    profile.return_visitor_exclusions = ["visited-place"]
    result = _service().evaluate(place, profile, NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("already visited" in r for r in result.rejection_reasons)


def test_temporarily_unavailable_rejected():
    place = _place(temporarily_unavailable=True)
    result = _service().evaluate(place, _profile(), NOW, remaining_budget=2000.0)
    assert not result.passed
    assert any("unavailable" in r for r in result.rejection_reasons)


def test_filter_candidates_only_returns_survivors():
    good = _place(id="good")
    bad = _place(id="bad", temporarily_unavailable=True)
    survivors = _service().filter_candidates([good, bad], _profile(), NOW, remaining_budget=2000.0)
    assert [p.id for p in survivors] == ["good"]
