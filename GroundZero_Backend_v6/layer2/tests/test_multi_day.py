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

NOW = datetime(2026, 7, 17, 9, 0, tzinfo=timezone.utc)


class FakePlaceRepository(PlaceRepository):
    def __init__(self, places):
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
        return self._places

    async def list_stale(self, older_than_days):
        return []

    async def delete(self, place_id):
        pass

    async def record_visit(self, place_id):
        pass


class FakeWeatherCollector:
    async def hourly_forecast(self, lat, lon, hours=12):
        raise SourceUnavailable("weather_api", "no key configured in test")


def _place(pid: str, category: str, cost: float = 50.0) -> Place:
    return Place(
        id=pid, name=pid, category=category,
        coordinates=Coordinates(latitude=12.9141 + (zlib.crc32(pid.encode()) % 20) * 0.001, longitude=74.8560),
        opening_hours=OpeningHours(raw="", opens_at="08:00", closes_at="20:00"),
        price_band=PriceBand.BUDGET, estimated_cost=cost,
        bias_signals=BiasSignals(media_mentions=1, local_percentage=0.9),
        bias_index=0.15, freshness_score=1.0, last_verified_at=NOW, dwell_time_typical_minutes=30,
    )


def _large_pool(n_per_category: int = 4) -> list[Place]:
    """Large enough that 3 days of 13-slot itineraries (39 places) can be
    filled without running out of candidates for any role."""
    categories = ["cafe", "market", "local_kitchen", "heritage_site", "museum", "beach",
                  "restaurant", "food_court", "hidden_gem", "viewpoint", "art_gallery"]
    places = []
    for cat in categories:
        for i in range(n_per_category * 4):  # generous supply per category
            places.append(_place(f"{cat}-{i}", cat))
    return places


def _engine(places: list[Place]) -> HiveEngine:
    return HiveEngine(
        place_repository=FakePlaceRepository(places),
        hard_filters=HardFilterService(AccessibilityDetector(), FreshnessService(180), freshness_min_score=0.4),
        fit_score=PersonalFitScoreService(CuriosityExtractor()),
        slot_assembly=SlotAssemblyService(random_seed=1),
        weather_scheduler=WeatherScheduler(),
        transport_tagger=TransportTagger(),
        weather_collector=FakeWeatherCollector(),
    )


def _multi_day_profile(days: int) -> TouristProfile:
    return TouristProfile(
        id="prof-multi", purpose=Purpose.CULTURAL, energy_band=EnergyBand.MODERATE,
        crowd_tolerance=CrowdTolerance.FINE, budget=5000.0,
        trip_duration_hours=TripDuration.MULTI_DAY, multi_day_count=days,
        start_time_preference=StartTimePreference.MORNING,
    )


@pytest.mark.asyncio
async def test_non_multi_day_profile_returns_single_day():
    engine = _engine(_large_pool())
    profile = TouristProfile(
        id="p1", purpose=Purpose.CULTURAL, energy_band=EnergyBand.MODERATE,
        crowd_tolerance=CrowdTolerance.FINE, budget=5000.0,
        trip_duration_hours=TripDuration.FULL_DAY, start_time_preference=StartTimePreference.MORNING,
    )
    result = await engine.build_multi_day_recommendation_queue(profile, NOW)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_multi_day_generates_requested_number_of_days():
    engine = _engine(_large_pool())
    profile = _multi_day_profile(days=3)
    result = await engine.build_multi_day_recommendation_queue(profile, NOW)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_multi_day_does_not_repeat_places_across_days():
    engine = _engine(_large_pool())
    profile = _multi_day_profile(days=3)
    result = await engine.build_multi_day_recommendation_queue(profile, NOW)

    all_place_ids = []
    for day_queue in result:
        all_place_ids.extend(item.place_id for item in day_queue.items)

    assert len(all_place_ids) == len(set(all_place_ids)), "a place was recommended on more than one day"


@pytest.mark.asyncio
async def test_multi_day_each_day_starts_24h_apart():
    engine = _engine(_large_pool())
    profile = _multi_day_profile(days=2)
    result = await engine.build_multi_day_recommendation_queue(profile, NOW)

    day1_first = result[0].items[0].scheduled_time
    day2_first = result[1].items[0].scheduled_time
    assert (day2_first - day1_first).days == 1


@pytest.mark.asyncio
async def test_multi_day_defaults_to_one_day_if_count_not_set():
    engine = _engine(_large_pool())
    profile = _multi_day_profile(days=None)
    profile.multi_day_count = None
    result = await engine.build_multi_day_recommendation_queue(profile, NOW)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_multi_day_respects_prior_return_visitor_exclusions():
    """Places excluded from a genuinely prior trip (blueprint 4.5) should
    also never resurface within THIS multi-day trip."""
    engine = _engine(_large_pool())
    profile = _multi_day_profile(days=2)
    profile.return_visitor_exclusions = ["heritage_site-0", "heritage_site-1"]

    result = await engine.build_multi_day_recommendation_queue(profile, NOW)
    all_place_ids = {item.place_id for day in result for item in day.items}
    assert "heritage_site-0" not in all_place_ids
    assert "heritage_site-1" not in all_place_ids
