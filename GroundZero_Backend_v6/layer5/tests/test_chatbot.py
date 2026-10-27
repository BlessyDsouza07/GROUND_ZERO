import pytest

from layer0.domain.entities import Coordinates, OpeningHours, Place, PriceBand
from layer0.domain.repositories import PlaceRepository
from layer5.chatbot import ChatIntent, IntentClassifier, TourismChatbot


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
        return list(places)

    async def list_all(self, category=None):
        return [p for p in self._places if category is None or p.category == category]

    async def list_stale(self, older_than_days):
        return []

    async def delete(self, place_id):
        pass

    async def record_visit(self, place_id):
        pass


def _place(pid: str, name: str, category: str, lat: float, lon: float) -> Place:
    return Place(
        id=pid,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(raw="", opens_at="08:00", closes_at="20:00"),
        price_band=PriceBand.BUDGET,
        estimated_cost=100.0,
        description="A lovely heritage church" if category == "heritage_site" else None,
    )


MANGALURU_CENTER = (12.9141, 74.8560)


@pytest.fixture
def repo() -> FakePlaceRepository:
    return FakePlaceRepository(
        [
            _place("p1", "Milagres Church", "heritage_site", 12.9141, 74.8560),
            _place("p2", "Panambur Beach", "beach", 12.9500, 74.8050),
        ]
    )


@pytest.mark.asyncio
async def test_search_places_returns_empty_without_repository_configured():
    # Regression test: before the fix, this always returned [] even with
    # a real repository because place_repository was hardcoded to None.
    bot = TourismChatbot(place_repository=None, hive_engine=None)
    results = await bot.search_places("church")
    assert results == []


@pytest.mark.asyncio
async def test_search_places_matches_real_repository_data(repo):
    bot = TourismChatbot(place_repository=repo, hive_engine=None)
    results = await bot.search_places("church")
    assert len(results) == 1
    assert results[0]["name"] == "Milagres Church"


@pytest.mark.asyncio
async def test_search_places_empty_query_returns_all(repo):
    bot = TourismChatbot(place_repository=repo, hive_engine=None)
    results = await bot.search_places("")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_get_nearby_places_sorts_closest_first_and_respects_radius(repo):
    bot = TourismChatbot(place_repository=repo, hive_engine=None)
    lat, lon = MANGALURU_CENTER
    results = await bot.get_nearby_places(lat, lon, radius_m=2000)
    # Only the church (co-located with the center) should be within 2km;
    # the beach is ~5km away.
    assert len(results) == 1
    assert results[0]["name"] == "Milagres Church"
    assert results[0]["distance_meters"] < 100


@pytest.mark.asyncio
async def test_get_place_info_returns_none_for_unknown_id(repo):
    bot = TourismChatbot(place_repository=repo, hive_engine=None)
    assert await bot.get_place_info("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_place_info_returns_real_place(repo):
    bot = TourismChatbot(place_repository=repo, hive_engine=None)
    info = await bot.get_place_info("p2")
    assert info is not None
    assert info["name"] == "Panambur Beach"


@pytest.mark.asyncio
async def test_process_message_greeting_intent():
    bot = TourismChatbot()
    response_text, bot_msg = await bot.process_message("Namaste!")
    assert bot_msg.intent == ChatIntent.GREETING
    assert response_text


@pytest.mark.asyncio
async def test_intent_classifier_emergency():
    classifier = IntentClassifier()
    intent, confidence = await classifier.classify("I need an ambulance, help!")
    assert intent == ChatIntent.EMERGENCY
    assert confidence > 0
