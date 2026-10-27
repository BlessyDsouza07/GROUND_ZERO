"""
Proves the claim in EtlOrchestrator's docstring: registering a new
ListingSource (e.g. a real Karnataka Tourism API once one exists) requires
no changes to the orchestrator itself — only instantiating the source and
passing it into LocalListingsCollector's `sources` list. This test uses a
fake source instead of a real API, since none is available/stable today;
the seam being tested is the architecture, not any particular API.
"""
from datetime import datetime, timezone

import pytest

from layer0.application.accessibility import AccessibilityDetector
from layer0.application.bias_audit import BiasAuditService
from layer0.application.dedup import DedupService
from layer0.application.etl_orchestrator import EtlOrchestrator
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import DataSource, Place
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.collectors.local_listings_collector import (
    ListingRecord,
    ListingSource,
    LocalListingsCollector,
)
from layer0.infrastructure.http_client import SourceUnavailable


class FakeKarnatakaTourismSource(ListingSource):
    """Stands in for a real future implementation — same interface, no
    real network call. Proves a new source only needs to implement
    ListingSource.fetch(); nothing about the orchestrator changes."""

    name = "fake_karnataka_tourism"

    async def fetch(self) -> list[ListingRecord]:
        return [
            ListingRecord(
                name="Kadri Manjunath Temple", category="heritage_site",
                lat=12.8817, lon=74.8477, address="Kadri, Mangaluru",
                description="A historic temple complex.",
                source_url="https://example.gov.in/kadri-temple",
                source_name=self.name,
            ),
            ListingRecord(
                name="Unmappable Listing", category="museum",
                lat=None, lon=None,  # no coordinates -> should be dropped, not crash
                address=None, description=None,
                source_url="https://example.gov.in/no-coords",
                source_name=self.name,
            ),
        ]


class FailingListingSource(ListingSource):
    """A source that errors out — must not take down the ETL run."""

    name = "failing_source"

    async def fetch(self) -> list[ListingRecord]:
        raise RuntimeError("upstream site changed its HTML structure")


class NullOsmCollector:
    async def collect(self, *args, **kwargs):
        raise SourceUnavailable("openstreetmap", "not exercised in this test")


class NullWikidataCollector:
    async def enrich(self, *args, **kwargs):
        raise SourceUnavailable("wikidata", "not exercised in this test")


class NullWikipediaCollector:
    async def summary(self, *args, **kwargs):
        raise SourceUnavailable("wikipedia", "not exercised in this test")


class FakePlaceRepository(PlaceRepository):
    def __init__(self):
        self.stored: list[Place] = []

    async def get_by_id(self, place_id):
        return next((p for p in self.stored if p.id == place_id), None)

    async def find_duplicates(self, place, radius_meters=75.0):
        return []

    async def upsert(self, place):
        place.id = place.id or f"generated-{len(self.stored)}"
        self.stored.append(place)
        return place

    async def bulk_upsert(self, places):
        return [await self.upsert(p) for p in places]

    async def list_all(self, category=None):
        return list(self.stored)

    async def list_stale(self, older_than_days):
        return []

    async def delete(self, place_id):
        pass

    async def record_visit(self, place_id):
        pass


def _build_orchestrator(sources: list[ListingSource], tmp_path) -> tuple[EtlOrchestrator, FakePlaceRepository]:
    repo = FakePlaceRepository()
    orchestrator = EtlOrchestrator(
        osm_collector=NullOsmCollector(),
        wikidata_collector=NullWikidataCollector(),
        wikipedia_collector=NullWikipediaCollector(),
        bias_audit=BiasAuditService(),
        freshness=FreshnessService(180),
        accessibility=AccessibilityDetector(),
        dedup=DedupService(),
        place_repository=repo,
        export_path=tmp_path / "master_data_core.json",
        local_listings_collector=LocalListingsCollector(http_client=None, sources=sources),
    )
    return orchestrator, repo


@pytest.mark.asyncio
async def test_no_sources_registered_is_a_clean_no_op(tmp_path):
    orchestrator, repo = _build_orchestrator([], tmp_path)
    report = await orchestrator.run(bbox=(12.75, 74.78, 13.05, 75.05))
    assert report.places_stored == 0
    assert repo.stored == []


@pytest.mark.asyncio
async def test_registering_a_fake_source_flows_through_the_full_pipeline(tmp_path):
    orchestrator, repo = _build_orchestrator([FakeKarnatakaTourismSource()], tmp_path)
    report = await orchestrator.run(bbox=(12.75, 74.78, 13.05, 75.05))

    # Only the record with real coordinates should survive; bias audit,
    # freshness, and storage should all have run on it, same as an OSM place.
    assert report.places_stored == 1
    stored = repo.stored[0]
    assert stored.name == "Kadri Manjunath Temple"
    assert stored.bias_index is not None
    assert stored.freshness_score == 1.0
    assert DataSource.LOCAL_LISTING in stored.source


@pytest.mark.asyncio
async def test_failing_source_does_not_crash_the_run(tmp_path):
    # LocalListingsCollector catches per-source failures itself (logs and
    # skips) — that's why this doesn't crash. Confirms the run completes
    # cleanly with zero places stored, not that the error is surfaced here.
    orchestrator, repo = _build_orchestrator([FailingListingSource()], tmp_path)
    report = await orchestrator.run(bbox=(12.75, 74.78, 13.05, 75.05))
    assert report.places_stored == 0


@pytest.mark.asyncio
async def test_multiple_sources_including_one_that_fails(tmp_path):
    orchestrator, repo = _build_orchestrator(
        [FakeKarnatakaTourismSource(), FailingListingSource()], tmp_path
    )
    report = await orchestrator.run(bbox=(12.75, 74.78, 13.05, 75.05))
    # The failing source is caught inside LocalListingsCollector itself
    # (per-source try/except), so the good source's results still arrive.
    assert report.places_stored == 1
