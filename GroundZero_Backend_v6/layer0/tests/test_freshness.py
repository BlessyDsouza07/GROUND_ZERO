from datetime import datetime, timedelta, timezone

from layer0.application.freshness import FreshnessService
from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand


def _place(last_verified_at=None, temporarily_unavailable=False) -> Place:
    return Place(
        id=None, name="Test Place", category="cafe",
        coordinates=Coordinates(latitude=12.9, longitude=74.85),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.BUDGET,
        estimated_cost=0.0, bias_signals=BiasSignals(),
        last_verified_at=last_verified_at, temporarily_unavailable=temporarily_unavailable,
    )


def test_never_verified_scores_zero():
    service = FreshnessService(stale_after_days=180)
    assert service.score(_place(last_verified_at=None)) == 0.0


def test_temporarily_unavailable_scores_zero_regardless_of_recency():
    service = FreshnessService(stale_after_days=180)
    now = datetime.now(timezone.utc)
    place = _place(last_verified_at=now, temporarily_unavailable=True)
    assert service.score(place, now=now) == 0.0


def test_just_verified_scores_near_one():
    service = FreshnessService(stale_after_days=180)
    now = datetime.now(timezone.utc)
    place = _place(last_verified_at=now)
    assert service.score(place, now=now) == 1.0


def test_decays_linearly_toward_stale_cutoff():
    service = FreshnessService(stale_after_days=100)
    now = datetime.now(timezone.utc)
    verified_50_days_ago = now - timedelta(days=50)
    place = _place(last_verified_at=verified_50_days_ago)
    assert abs(service.score(place, now=now) - 0.5) < 0.01


def test_floors_at_zero_past_stale_cutoff():
    service = FreshnessService(stale_after_days=100)
    now = datetime.now(timezone.utc)
    verified_long_ago = now - timedelta(days=500)
    place = _place(last_verified_at=verified_long_ago)
    assert service.score(place, now=now) == 0.0


def test_is_fresh_enough_threshold():
    service = FreshnessService(stale_after_days=100)
    now = datetime.now(timezone.utc)
    place = _place(last_verified_at=now - timedelta(days=10))
    assert service.is_fresh_enough(place, min_score=0.4, now=now) is True
    assert service.is_fresh_enough(place, min_score=0.95, now=now) is False
