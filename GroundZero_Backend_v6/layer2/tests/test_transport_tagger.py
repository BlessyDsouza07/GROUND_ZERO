import pytest

from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand
from layer2.application.transport_tagger import TransportTagger
from layer2.domain.entities import TransportMode


def _place(lat, lon) -> Place:
    return Place(
        id="p", name="P", category="cafe", coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.BUDGET, estimated_cost=0.0,
        bias_signals=BiasSignals(),
    )


def test_short_distance_is_walk_and_free():
    tagger = TransportTagger()
    origin = _place(12.9141, 74.8560)
    destination = _place(12.9145, 74.8563)  # ~50m away
    estimate = tagger.estimate(origin, destination)
    assert estimate.mode == TransportMode.WALK
    assert estimate.cost_inr == 0.0


def test_medium_distance_is_auto_with_cost():
    tagger = TransportTagger()
    origin = _place(12.9141, 74.8560)
    destination = _place(12.94, 74.87)  # a few km away
    estimate = tagger.estimate(origin, destination)
    assert estimate.mode == TransportMode.AUTO
    assert estimate.cost_inr > 0


def test_long_distance_is_cab():
    tagger = TransportTagger()
    origin = _place(12.9141, 74.8560)
    destination = _place(13.05, 75.0)  # >10km away
    estimate = tagger.estimate(origin, destination)
    assert estimate.mode == TransportMode.CAB
    assert estimate.cost_inr > 0


def test_zero_distance_is_free_walk():
    tagger = TransportTagger()
    place = _place(12.9141, 74.8560)
    estimate = tagger.estimate(place, place)
    assert estimate.mode == TransportMode.WALK
    assert estimate.cost_inr == 0.0
    assert estimate.duration_minutes >= 1


def test_auto_within_minimum_fare_distance_charges_flat_minimum():
    """Official RTA tariff: Rs 35 covers the first 1.5km flat, no per-km
    charge added within that distance."""
    tagger = TransportTagger()
    origin = _place(12.9141, 74.8560)
    # ~1.2km away — inside the 1.5km minimum-fare bracket but past the
    # walking threshold.
    destination = _place(12.9141 + 0.0108, 74.8560)
    estimate = tagger.estimate(origin, destination)
    assert estimate.mode == TransportMode.AUTO
    assert estimate.cost_inr == 35.0


def test_auto_beyond_minimum_fare_distance_adds_per_km_rate():
    tagger = TransportTagger()
    origin = _place(12.9141, 74.8560)
    # ~3.5km away -> 35 + (3.5 - 1.5) * 20 = 75
    destination = _place(12.9141 + 0.0315, 74.8560)
    estimate = tagger.estimate(origin, destination)
    assert estimate.mode == TransportMode.AUTO
    assert estimate.cost_inr == pytest.approx(75.0, abs=5.0)
