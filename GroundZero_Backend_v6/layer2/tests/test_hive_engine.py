from datetime import datetime, timezone
import zlib

import pytest

from layer0.application.accessibility import AccessibilityDetector
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import BiasSignals, Coordinates, OpeningHours, Place, PriceBand
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.http_client import SourceUnavailable
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.domain.entities import (
    CrowdTolerance,
    EnergyBand,
    Purpose,
    StartTimePreference,
    TouristProfile,
    TripDuration,
)
from layer2.application.hard_filters import HardFilterService
from layer2.application.hive_engine import HiveEngine
from layer2.application.personal_fit_score import PersonalFitScoreService
from layer2.application.slot_assembly import SlotAssemblyService
from layer2.application.transport_tagger import TransportTagger
from layer2.application.weather_scheduler import WeatherScheduler
from layer2.domain.entities import SlotRole

NOW = datetime(2026, 7, 17, 9, 0, tzinfo=timezone.utc)


class FakePlaceRepository(PlaceRepository):
    def __init__(self, places: list[Place]):
        self._places = places

    async def get_by_id(self, place_id):
        return next((p for p in self._places if p.id == place_id), None)

    async def find_duplicates(self, place, radius_meters=75.0):
        return []

    async def upsert(self, place):
        return place

    async def bulk_upsert(self, places):
        return [await self.upsert(p) for p in places]

    async def list_all(self, category=None):
        return [p for p in self._places if category is None or p.category == category]

    async def list_stale(self, older_than_days):
        return []

    async def delete(self, place_id):
        pass

    async def record_visit(self, place_id):
        pass


class FakeWeatherCollector:
    async def hourly_forecast(self, lat, lon, hours=12):
        raise SourceUnavailable("weather_api", "no key configured in test")


def _place(pid: str, category: str, cost=100.0, dwell=45) -> Place:
    return Place(
        id=pid, name=pid, category=category,
        coordinates=Coordinates(latitude=12.9141 + zlib.crc32(pid.encode()) % 10 * 0.001, longitude=74.8560),
        opening_hours=OpeningHours(raw="", opens_at="08:00", closes_at="20:00"),
        price_band=PriceBand.BUDGET, estimated_cost=cost,
        bias_signals=BiasSignals(media_mentions=1, local_percentage=0.95),
        bias_index=0.1, freshness_score=1.0, last_verified_at=NOW,
        dwell_time_typical_minutes=dwell,
    )


def _build_engine(places: list[Place]) -> HiveEngine:
    return HiveEngine(
        place_repository=FakePlaceRepository(places),
        hard_filters=HardFilterService(AccessibilityDetector(), FreshnessService(180), freshness_min_score=0.4),
        fit_score=PersonalFitScoreService(CuriosityExtractor()),
        slot_assembly=SlotAssemblyService(random_seed=1),
        weather_scheduler=WeatherScheduler(),
        transport_tagger=TransportTagger(),
        weather_collector=FakeWeatherCollector(),
    )


def _rich_pool() -> list[Place]:
    places = []
    categories = (
        ["cafe", "market", "local_kitchen"]
        + ["heritage_site", "museum", "beach"]
        + ["restaurant", "food_court"]
        + ["hidden_gem"] * 2
        + ["viewpoint"] * 10
        + ["art_gallery"] * 3
    )
    for i, cat in enumerate(categories):
        media_mentions = 1 if cat == "hidden_gem" else 20
        local_pct = 0.95 if cat == "hidden_gem" else 0.4
        places.append(
            Place(
                id=f"place-{i}", name=f"place-{i}", category=cat,
                coordinates=Coordinates(latitude=12.9141 + i * 0.001, longitude=74.8560 + i * 0.001),
                opening_hours=OpeningHours(raw="", opens_at="08:00", closes_at="20:00"),
                price_band=PriceBand.BUDGET, estimated_cost=100.0,
                bias_signals=BiasSignals(media_mentions=media_mentions, local_percentage=local_pct),
                bias_index=0.15, freshness_score=1.0, last_verified_at=NOW, dwell_time_typical_minutes=45,
            )
        )
    return places


def _profile() -> TouristProfile:
    return TouristProfile(
        id="prof1", purpose=Purpose.CULTURAL, energy_band=EnergyBand.MODERATE,
        crowd_tolerance=CrowdTolerance.FINE, budget=5000.0,
        trip_duration_hours=TripDuration.FULL_DAY, start_time_preference=StartTimePreference.MORNING,
    )


@pytest.mark.asyncio
async def test_hive_engine_produces_full_recommendation_queue():
    engine = _build_engine(_rich_pool())
    queue = await engine.build_recommendation_queue(_profile(), NOW)

    assert queue.profile_id == "prof1"
    assert len(queue.items) == 13  # full day, per Table 5
    assert queue.total_estimated_cost > 0

    roles_present = {item.role for item in queue.items}
    assert SlotRole.GROUNDING in roles_present
    assert SlotRole.SIGNATURE in roles_present
    assert SlotRole.ANCHOR in roles_present
    assert SlotRole.LOCAL_SECRET in roles_present


@pytest.mark.asyncio
async def test_hive_engine_respects_budget_hard_filter():
    places = _rich_pool()
    # Make everything absurdly expensive
    for p in places:
        p.estimated_cost = 100_000.0
    engine = _build_engine(places)
    profile = _profile()
    profile.budget = 500.0

    queue = await engine.build_recommendation_queue(profile, NOW)
    assert len(queue.items) == 0  # everything filtered out on budget


@pytest.mark.asyncio
async def test_hive_engine_each_item_has_a_reason():
    engine = _build_engine(_rich_pool())
    queue = await engine.build_recommendation_queue(_profile(), NOW)
    assert all(item.reason_selected for item in queue.items)
    assert all(item.personal_score > 0 for item in queue.items)


@pytest.mark.asyncio
async def test_hive_engine_weather_unavailable_does_not_crash():
    # FakeWeatherCollector always raises SourceUnavailable; engine must
    # degrade gracefully to the naive (unadjusted) schedule, not error out.
    engine = _build_engine(_rich_pool())
    queue = await engine.build_recommendation_queue(_profile(), NOW)
    assert all(not item.weather_adjusted for item in queue.items)


# --- Tourist-added places (pinned_place_ids) -------------------------------
#
# A place the tourist adds themselves (see CustomPlaceService /
# POST /places/custom) must always land in the queue, even when it would
# have failed a Hard Filter or blown the budget on its own — that's the
# entire point of "you add it, you're guaranteed to be taken there."


@pytest.mark.asyncio
async def test_pinned_place_is_included_even_though_hard_filters_would_reject_it():
    places = _rich_pool()
    pinned = _place("pinned-1", "tourist_pick", cost=100.0)
    pinned.temporarily_unavailable = True  # would normally be dropped by Hard Filters
    places.append(pinned)

    engine = _build_engine(places)
    queue = await engine.build_recommendation_queue(_profile(), NOW, pinned_place_ids=["pinned-1"])

    pinned_items = [item for item in queue.items if item.place_id == "pinned-1"]
    assert len(pinned_items) == 1
    assert pinned_items[0].role == SlotRole.TOURIST_PICK
    assert "added this place yourself" in pinned_items[0].reason_selected


@pytest.mark.asyncio
async def test_pinned_place_is_never_dropped_by_budget_enforcement():
    places = _rich_pool()
    pinned = _place("pinned-2", "tourist_pick", cost=100_000.0)  # absurdly over budget on its own
    places.append(pinned)

    engine = _build_engine(places)
    profile = _profile()
    profile.budget = 500.0  # low enough that ordinary places get trimmed hard

    queue = await engine.build_recommendation_queue(profile, NOW, pinned_place_ids=["pinned-2"])
    pinned_items = [item for item in queue.items if item.place_id == "pinned-2"]
    assert len(pinned_items) == 1  # kept despite blowing the budget alone


@pytest.mark.asyncio
async def test_pinned_place_is_not_also_selected_as_an_ordinary_slot():
    places = _rich_pool()
    pinned = _place("pinned-3", "cafe", cost=50.0)  # a category HIVE would happily pick on its own
    places.append(pinned)

    engine = _build_engine(places)
    queue = await engine.build_recommendation_queue(_profile(), NOW, pinned_place_ids=["pinned-3"])

    matches = [item for item in queue.items if item.place_id == "pinned-3"]
    assert len(matches) == 1
    assert matches[0].role == SlotRole.TOURIST_PICK


@pytest.mark.asyncio
async def test_no_pinned_place_ids_behaves_exactly_as_before():
    engine = _build_engine(_rich_pool())
    queue = await engine.build_recommendation_queue(_profile(), NOW, pinned_place_ids=[])
    assert len(queue.items) == 13
    assert all(item.role != SlotRole.TOURIST_PICK for item in queue.items)


# --- Reachability geofence --------------------------------------------------
#
# Regression coverage for a real bug: start_latitude/start_longitude is
# meant to narrow the candidate pool to what's reachable, never to be able
# to silently empty it. The most common way a caller ends up passing a
# wildly-wrong location isn't malice, it's routine: a simulator/emulator's
# default GPS fix (e.g. iOS Simulator's Cupertino default, an Android
# emulator's Mountain View/(0,0) default), or a stale/cell-tower fix grabbed
# before a real GPS lock — any of which is thousands of km from every place
# in this dataset. Before the fix, that produced an empty queue for every
# survey answer; see layer2/application/reachability.py.

# Real-world example of exactly this failure mode: Apple's iOS Simulator
# default location (Apple Park, Cupertino) — nowhere near Mangaluru.
_SIMULATOR_DEFAULT_LATITUDE = 37.3346
_SIMULATOR_DEFAULT_LONGITUDE = -122.0090


@pytest.mark.asyncio
async def test_geofence_falls_back_to_full_pool_when_location_matches_nothing():
    engine = _build_engine(_rich_pool())
    queue = await engine.build_recommendation_queue(
        _profile(), NOW,
        start_latitude=_SIMULATOR_DEFAULT_LATITUDE, start_longitude=_SIMULATOR_DEFAULT_LONGITUDE,
    )
    # The whole point of the fix: an untrustworthy location must never be
    # able to produce "nothing fit today" on its own.
    assert len(queue.items) == 13
    assert queue.geofence_radius_km is None  # signals "no effective geofence was applied"


@pytest.mark.asyncio
async def test_geofence_narrows_pool_for_a_real_nearby_location():
    places = _rich_pool()  # all within ~a few hundred meters of 12.9141, 74.8560
    far_away = _place("far-1", "cafe", cost=100.0)
    far_away.coordinates = Coordinates(latitude=_SIMULATOR_DEFAULT_LATITUDE, longitude=_SIMULATOR_DEFAULT_LONGITUDE)
    places.append(far_away)

    engine = _build_engine(places)
    queue = await engine.build_recommendation_queue(
        _profile(), NOW, start_latitude=12.9141, start_longitude=74.8560,
    )
    # A real, in-coverage location still geofences normally...
    assert queue.geofence_radius_km is not None
    # ...and the place on the other side of the world is correctly excluded.
    assert all(item.place_id != "far-1" for item in queue.items)
