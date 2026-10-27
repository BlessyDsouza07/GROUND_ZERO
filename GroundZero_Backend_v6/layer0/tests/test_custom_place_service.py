from datetime import datetime, timezone

import pytest

from layer0.application.bias_audit import BiasAuditService
from layer0.application.custom_place_service import CustomPlaceService
from layer0.application.dedup import DedupService
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import (
    BiasSignals,
    Coordinates,
    DataSource,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.domain.repositories import PlaceRepository

NOW = datetime(2026, 7, 17, 9, 0, tzinfo=timezone.utc)

MILAGRES_CHURCH_LAT = 12.8745
MILAGRES_CHURCH_LON = 74.8420


class FakePlaceRepository(PlaceRepository):
    def __init__(self, places: list[Place]):
        self._places = places
        self.upserted: list[Place] = []

    async def get_by_id(self, place_id):
        return next((p for p in self._places if p.id == place_id), None)

    async def find_duplicates(self, place, radius_meters=75.0):
        return []

    async def upsert(self, place):
        place.id = place.id or f"new-{len(self._places) + len(self.upserted)}"
        self.upserted.append(place)
        self._places.append(place)
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


def _existing_church() -> Place:
    return Place(
        id="church-1",
        name="Milagres Church",
        category="heritage_site",
        coordinates=Coordinates(latitude=MILAGRES_CHURCH_LAT, longitude=MILAGRES_CHURCH_LON),
        opening_hours=OpeningHours(raw="Mo-Su 06:00-19:00", opens_at="06:00", closes_at="19:00"),
        price_band=PriceBand.FREE,
        estimated_cost=0.0,
        bias_signals=BiasSignals(media_mentions=3, local_percentage=0.6),
        bias_index=0.1,
        grade="authentic",
        freshness_score=1.0,
        last_verified_at=NOW,
        source=[DataSource.OSM],
    )


def _service(places: list[Place]) -> tuple[CustomPlaceService, FakePlaceRepository]:
    repo = FakePlaceRepository(places)
    service = CustomPlaceService(
        place_repository=repo,
        dedup=DedupService(),
        bias_audit=BiasAuditService(),
        freshness=FreshnessService(180),
    )
    return service, repo


@pytest.mark.asyncio
async def test_add_or_find_creates_brand_new_place_when_nothing_nearby_matches():
    service, repo = _service([])

    result = await service.add_or_find(
        name="Grandma Fernandes' Fish Curry Stall",
        lat=12.9000,
        lon=74.8300,
        category="local_kitchen",
        note="Tiny stall, best fish curry I've had, cash only.",
    )

    assert result.was_newly_created is True
    assert result.place.id is not None
    assert result.place.name == "Grandma Fernandes' Fish Curry Stall"
    assert result.place.source == [DataSource.TOURIST_ADDED]
    assert result.place.bias_index is not None  # bias audit ran, not left as None
    assert result.place.grade is not None
    assert len(repo.upserted) == 1


@pytest.mark.asyncio
async def test_add_or_find_reuses_existing_place_instead_of_duplicating():
    church = _existing_church()
    service, repo = _service([church])

    # Tourist typed a slightly different name and doesn't know the internal
    # category taxonomy at all ("church" vs "heritage_site") — should still match.
    result = await service.add_or_find(
        name="Milagres church",
        lat=MILAGRES_CHURCH_LAT + 0.0002,  # ~20m off, still within match radius
        lon=MILAGRES_CHURCH_LON,
        category="church",
    )

    assert result.was_newly_created is False
    assert result.place.id == "church-1"
    assert len(repo.upserted) == 0  # nothing new written


@pytest.mark.asyncio
async def test_add_or_find_does_not_match_a_genuinely_different_place_nearby():
    church = _existing_church()
    service, repo = _service([church])

    result = await service.add_or_find(
        name="Some Random Tea Stall",
        lat=MILAGRES_CHURCH_LAT + 0.0002,
        lon=MILAGRES_CHURCH_LON,
        category="cafe",
    )

    assert result.was_newly_created is True  # different name -> not treated as a duplicate
    assert result.place.name == "Some Random Tea Stall"


@pytest.mark.asyncio
async def test_search_nearby_is_sorted_closest_first_and_category_agnostic():
    near = Place(
        id="near", name="Near Place", category="temple",
        coordinates=Coordinates(latitude=MILAGRES_CHURCH_LAT + 0.0003, longitude=MILAGRES_CHURCH_LON),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.FREE, estimated_cost=0.0,
        bias_signals=BiasSignals(), freshness_score=1.0, last_verified_at=NOW,
    )
    far = Place(
        id="far", name="Far Place", category="museum",
        coordinates=Coordinates(latitude=MILAGRES_CHURCH_LAT + 0.0009, longitude=MILAGRES_CHURCH_LON),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.FREE, estimated_cost=0.0,
        bias_signals=BiasSignals(), freshness_score=1.0, last_verified_at=NOW,
    )
    too_far = Place(
        id="too-far", name="Too Far Place", category="beach",
        coordinates=Coordinates(latitude=MILAGRES_CHURCH_LAT + 1.0, longitude=MILAGRES_CHURCH_LON),
        opening_hours=OpeningHours(raw=""), price_band=PriceBand.FREE, estimated_cost=0.0,
        bias_signals=BiasSignals(), freshness_score=1.0, last_verified_at=NOW,
    )
    service, _ = _service([far, too_far, near])  # deliberately unsorted input

    results = await service.search_nearby(MILAGRES_CHURCH_LAT, MILAGRES_CHURCH_LON, radius_meters=150.0)

    assert [p.id for p in results] == ["near", "far"]  # too_far excluded, near before far


@pytest.mark.asyncio
async def test_add_or_find_rejects_blank_name():
    service, _ = _service([])
    with pytest.raises(ValueError):
        await service.add_or_find(name="   ", lat=12.9, lon=74.8)
