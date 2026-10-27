from datetime import datetime, timedelta, timezone

from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand
from layer0.infrastructure.collectors.weather_collector import HourlyForecast
from layer2.application.slot_assembly import AssembledSlot
from layer2.application.weather_scheduler import WeatherScheduler
from layer2.domain.entities import ScoredPlace, SlotRole

START = datetime(2026, 7, 17, 9, 0, tzinfo=timezone.utc)


def _place(pid: str, category: str, dwell=30) -> Place:
    return Place(
        id=pid, name=pid, category=category,
        coordinates=Coordinates(latitude=12.9, longitude=74.85),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.BUDGET, estimated_cost=0.0,
        bias_signals=BiasSignals(), dwell_time_typical_minutes=dwell,
    )


def _slot(pid: str, role=SlotRole.PERSONAL) -> AssembledSlot:
    scored = ScoredPlace(place_id=pid, name=pid, category="x", raw_score=0.5, bias_index=0.1, personal_fit=0.5)
    return AssembledSlot(role=role, scored_place=scored)


def _forecast(hours: list[int], rain_hours: set[int]) -> list[HourlyForecast]:
    return [
        HourlyForecast(
            timestamp=START.replace(hour=h), condition_main="Rain" if h in rain_hours else "Clear",
            is_rain=h in rain_hours, is_severe=False, temperature_celsius=28.0,
        )
        for h in hours
    ]


def test_no_rain_produces_naive_unadjusted_schedule():
    scheduler = WeatherScheduler()
    beach = _place("beach1", "beach")
    museum = _place("museum1", "museum")
    slots = [_slot("beach1"), _slot("museum1")]
    places = {"beach1": beach, "museum1": museum}

    scheduled = scheduler.schedule(slots, places, START, forecast=[])
    assert all(not s.weather_adjusted for s in scheduled)
    assert scheduled[0].scheduled_at == START


def test_outdoor_slot_in_rain_hour_swaps_with_indoor_slot():
    scheduler = WeatherScheduler()
    # beach (outdoor) scheduled first at 9am, museum (indoor) later.
    # Rain forecast at 9am -> beach should swap with museum.
    beach = _place("beach1", "beach", dwell=60)
    museum = _place("museum1", "museum", dwell=60)
    slots = [_slot("beach1"), _slot("museum1")]
    places = {"beach1": beach, "museum1": museum}

    forecast = _forecast(hours=[9, 10, 11], rain_hours={9})
    scheduled = scheduler.schedule(slots, places, START, forecast=forecast, dwell_gap_minutes=15)

    first_place_id = scheduled[0].slot.scored_place.place_id
    assert first_place_id == "museum1"  # indoor place swapped into the rain-hour slot; beach moved to the clear hour
    assert any(s.weather_adjusted for s in scheduled)


def test_no_indoor_alternative_leaves_schedule_unadjusted_for_that_slot():
    scheduler = WeatherScheduler()
    beach1 = _place("beach1", "beach")
    beach2 = _place("beach2", "beach")
    slots = [_slot("beach1"), _slot("beach2")]
    places = {"beach1": beach1, "beach2": beach2}

    forecast = _forecast(hours=[9, 10], rain_hours={9})
    scheduled = scheduler.schedule(slots, places, START, forecast=forecast)
    # No indoor candidate exists, so nothing can be swapped -> no crash, no fabricated fix.
    assert not any(s.weather_adjusted for s in scheduled)
