from datetime import datetime, timezone

import pytest

from layer0.domain.entities import Coordinates, OpeningHours, Place, PriceBand
from layer5.geofencing import GeofencingEngine, GPSCoordinate, geofences_from_places


def _place(pid: str, name: str, lat: float, lon: float, description=None) -> Place:
    return Place(
        id=pid, name=name, category="beach",
        coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(raw="", opens_at="08:00", closes_at="20:00"),
        price_band=PriceBand.BUDGET, estimated_cost=0.0,
        description=description,
    )


def test_geofences_from_places_builds_one_per_place():
    places = [
        _place("p1", "Panambur Beach", 12.95, 74.80, description="A popular beach."),
        _place("p2", "Sasihithlu Beach", 13.05, 74.75),
    ]
    fences = geofences_from_places(places)
    assert len(fences) == 2
    by_id = {f.place_id: f for f in fences}
    assert by_id["p1"].narration_text == "A popular beach."
    # No fabricated facts when there's no description — plain fallback only.
    assert by_id["p2"].narration_text == "Welcome to Sasihithlu Beach."


def test_geofences_from_places_skips_places_without_id():
    places = [_place(None, "No ID Place", 12.9, 74.8)]
    assert geofences_from_places(places) == []


def test_distance_to_haversine_zero_at_same_point():
    gps = GPSCoordinate(latitude=12.9141, longitude=74.8560, accuracy_m=5.0, timestamp=datetime.now(timezone.utc))
    assert gps.distance_to(12.9141, 74.8560) == pytest.approx(0.0, abs=1.0)


def test_engine_fires_entry_then_exit_event():
    engine = GeofencingEngine()
    places = [_place("p1", "Milagres Church", 12.9141, 74.8560, description="Historic church.")]
    engine.add_geofences(geofences_from_places(places))

    inside = GPSCoordinate(latitude=12.9141, longitude=74.8560, accuracy_m=5.0, timestamp=datetime.now(timezone.utc))
    events = engine.update_gps(inside)
    assert len(events) == 1
    assert events[0].event_type == "entry"
    assert events[0].place_id == "p1"

    far_away = GPSCoordinate(latitude=13.5, longitude=75.5, accuracy_m=5.0, timestamp=datetime.now(timezone.utc))
    events = engine.update_gps(far_away)
    assert len(events) == 1
    assert events[0].event_type == "exit"


def test_engine_ignores_gps_with_poor_accuracy():
    engine = GeofencingEngine()
    engine.add_geofences(geofences_from_places([_place("p1", "X", 12.9141, 74.8560)]))
    inaccurate = GPSCoordinate(latitude=12.9141, longitude=74.8560, accuracy_m=999.0, timestamp=datetime.now(timezone.utc))
    assert engine.update_gps(inaccurate) == []
