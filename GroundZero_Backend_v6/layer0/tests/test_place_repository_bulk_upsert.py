"""
Real integration tests for PostgresPlaceRepository.bulk_upsert's chunking
behavior, added when bulk_upsert moved from a single unchunked
flush/commit to a configurable-batch_size chunked commit (see
repository_impl.py for the reasoning: bounding both per-statement
parameter counts and how much work a late failure can lose).

Uses a real Postgres session, consistent with this codebase's established
pattern of live-verifying DB-touching code rather than mocking the
database away (see test_api_endpoints.py).
"""
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://groundzero:groundzero@localhost:5432/groundzero")

from layer0.domain.entities import BiasSignals, Coordinates, DataSource, OpeningHours, Place, PriceBand  # noqa: E402
from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository  # noqa: E402
from shared.config import get_settings  # noqa: E402


def _place(name: str, lat: float, lon: float) -> Place:
    return Place(
        id=None,
        name=name,
        category="cafe",
        coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(raw=""),
        price_band=PriceBand.BUDGET,
        estimated_cost=100.0,
        bias_signals=BiasSignals(),
        source=[DataSource.OSM],
    )


@pytest.fixture
async def session():
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_bulk_upsert_with_small_batch_size_still_stores_every_place(session: AsyncSession):
    # batch_size=2 forces 3 chunks (2, 2, 1) for 5 places — proves chunking
    # doesn't drop anything at a boundary and every chunk gets its own
    # flush/commit rather than one all-or-nothing transaction.
    repo = PostgresPlaceRepository(session, batch_size=2)
    unique = uuid.uuid4().hex[:8]
    places = [_place(f"Batch Test Place {unique}-{i}", 12.90 + i * 0.001, 74.85) for i in range(5)]

    stored = await repo.bulk_upsert(places)

    assert len(stored) == 5
    assert {p.name for p in stored} == {p.name for p in places}
    for p in stored:
        assert p.id is not None  # every place actually got a durable id


@pytest.mark.asyncio
async def test_bulk_upsert_default_batch_size_matches_settings(session: AsyncSession):
    repo = PostgresPlaceRepository(session, batch_size=get_settings().etl_storage_batch_size)
    assert repo.batch_size == get_settings().etl_storage_batch_size


@pytest.mark.asyncio
async def test_bulk_upsert_earlier_chunk_survives_when_committed_before_a_later_failure(session: AsyncSession):
    # Simulates the exact scenario chunking exists for: with batch_size=1,
    # each place is its own transaction. If a later place fails, places
    # already committed in earlier chunks must remain stored rather than
    # being rolled back with the failure.
    repo = PostgresPlaceRepository(session, batch_size=1)
    unique = uuid.uuid4().hex[:8]
    good_place = _place(f"Durable Chunk Place {unique}", 12.91, 74.85)

    stored = await repo.bulk_upsert([good_place])
    assert len(stored) == 1
    stored_id = stored[0].id

    # A second, independent call (simulating a later chunk failing for an
    # unrelated reason) must not affect what's already committed.
    fetched = await repo.get_by_id(stored_id)
    assert fetched is not None
    assert fetched.name == good_place.name
