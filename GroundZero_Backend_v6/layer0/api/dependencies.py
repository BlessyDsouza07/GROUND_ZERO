"""Dependency injection wiring for Layer 0. FastAPI's `Depends` calls these
factory functions; nothing here is a global singleton service locator."""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from layer0.application.accessibility import AccessibilityDetector
from layer0.application.bias_audit import BiasAuditService
from layer0.application.community_workflow import CommunitySubmissionService
from layer0.application.custom_place_service import CustomPlaceService
from layer0.application.dedup import DedupService
from layer0.application.etl_orchestrator import EtlOrchestrator
from layer0.application.freshness import FreshnessService
from layer0.domain.repositories import CommunitySubmissionRepository, PlaceRepository
from layer0.infrastructure.collectors.osm_collector import OsmCollector
from layer0.infrastructure.collectors.wikidata_collector import WikidataCollector
from layer0.infrastructure.collectors.wikipedia_collector import WikipediaCollector
from layer0.infrastructure.db.repository_impl import (
    PostgresCommunitySubmissionRepository,
    PostgresPlaceRepository,
)
from layer0.infrastructure.db.session import get_session
from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable
from shared.config import Settings, get_settings

async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


def get_place_repository(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PlaceRepository:
    return PostgresPlaceRepository(session, batch_size=settings.etl_storage_batch_size)


def get_submission_repository(
    session: AsyncSession = Depends(get_db_session),
) -> CommunitySubmissionRepository:
    return PostgresCommunitySubmissionRepository(session)


def get_bias_audit_service() -> BiasAuditService:
    return BiasAuditService()


def get_freshness_service(settings: Settings = Depends(get_settings)) -> FreshnessService:
    return FreshnessService(stale_after_days=settings.freshness_stale_after_days)


def get_accessibility_detector() -> AccessibilityDetector:
    return AccessibilityDetector()


def get_dedup_service() -> DedupService:
    return DedupService()


def get_http_client() -> ResilientHttpClient:
    return ResilientHttpClient()


def get_community_submission_service(
    submission_repo: CommunitySubmissionRepository = Depends(get_submission_repository),
    place_repo: PlaceRepository = Depends(get_place_repository),
    bias_audit: BiasAuditService = Depends(get_bias_audit_service),
    freshness: FreshnessService = Depends(get_freshness_service),
) -> CommunitySubmissionService:
    return CommunitySubmissionService(submission_repo, place_repo, bias_audit, freshness)


def get_custom_place_service(
    place_repo: PlaceRepository = Depends(get_place_repository),
    dedup: DedupService = Depends(get_dedup_service),
    bias_audit: BiasAuditService = Depends(get_bias_audit_service),
    freshness: FreshnessService = Depends(get_freshness_service),
) -> CustomPlaceService:
    return CustomPlaceService(place_repo, dedup, bias_audit, freshness)


def get_etl_orchestrator(
    settings: Settings = Depends(get_settings),
    http_client: ResilientHttpClient = Depends(get_http_client),
    place_repo: PlaceRepository = Depends(get_place_repository),
    bias_audit: BiasAuditService = Depends(get_bias_audit_service),
    freshness: FreshnessService = Depends(get_freshness_service),
    accessibility: AccessibilityDetector = Depends(get_accessibility_detector),
    dedup: DedupService = Depends(get_dedup_service),
) -> EtlOrchestrator:
    from pathlib import Path
    from layer0.infrastructure.collectors.local_listings_collector import LocalListingsCollector
    from layer0.infrastructure.collectors.spreadsheet_source import SpreadsheetListingSource


    from layer0.infrastructure.collectors.event_rss_collector import EventRssCollector
    
    # OSM collection: prefer the fully offline, zero-API, zero-rate-limit
    # extract-file collector when OSM_EXTRACT_FILE_PATH is configured and
    # the file actually exists. Otherwise fall back to the live Overpass
    # collector (also free/legal, already tiled + concurrency-capped for
    # fair use — see osm_collector.py). Either one produces the identical
    # OsmElement shape, so nothing downstream needs to know which is active.
    if settings.osm_extract_file_path and Path(settings.osm_extract_file_path).exists():
        from layer0.infrastructure.collectors.bulk_osm_extract_collector import BulkOsmExtractCollector
        osm_collector = BulkOsmExtractCollector(settings.osm_extract_file_path)
    else:
        osm_collector = OsmCollector(http_client, settings.overpass_url)

    # Karnataka Tourism still has no single stable public API today — when
    # one turns up, registering it is exactly this:
    #
    #   from layer0.infrastructure.collectors.karnataka_tourism_source import KarnatakaTourismSource
    #   listing_sources.append(KarnatakaTourismSource(http_client, settings.karnataka_tourism_feed_url))
    #
    # In the meantime, the CSV-based SpreadsheetListingSource is always
    # registered — it costs nothing to check, has zero rate limits (it's a
    # local file read), and is the practical way to add hyperlocal places
    # no API indexes at all. If the file doesn't exist yet, it silently
    # contributes zero rows (see spreadsheet_source.py) — never an error.
    # Nothing else below, in the orchestrator, or in the ETL pipeline needs
    # to change for either source — see
    # layer0/tests/test_etl_local_listings_seam.py for a test proving this
    # with a fake source.
    listing_sources: list = [SpreadsheetListingSource(settings.spreadsheet_places_csv_path)]
    local_listings_collector = LocalListingsCollector(http_client, listing_sources)

    event_rss_feed_urls = [
        url.strip() for url in settings.event_rss_feed_urls.split(",") if url.strip()
    ]
    event_rss_collector = EventRssCollector(event_rss_feed_urls)
    if settings.enable_wikidata_wikipedia_enrichment:
        wikidata_collector = WikidataCollector(http_client, settings.wikidata_sparql_url)
        wikipedia_collector = WikipediaCollector(http_client)
    else:
        # Zero-API mode: no network call of any kind is made for
        # enrichment. Places still get everything OSM/the spreadsheet
        # provided; they just won't gain a Wikidata description or
        # Wikipedia summary. Reusing SourceUnavailable here means the
        # orchestrator's existing "log and skip, never fabricate" path
        # handles this identically to a real outage — no special-casing
        # needed anywhere else.
        class _DisabledWikidataCollector:
            async def enrich(self, *args, **kwargs):
                raise SourceUnavailable("wikidata", "disabled via ENABLE_WIKIDATA_WIKIPEDIA_ENRICHMENT=false")

        class _DisabledWikipediaCollector:
            async def summary(self, *args, **kwargs):
                raise SourceUnavailable("wikipedia", "disabled via ENABLE_WIKIDATA_WIKIPEDIA_ENRICHMENT=false")

        wikidata_collector = _DisabledWikidataCollector()
        wikipedia_collector = _DisabledWikipediaCollector()

    return EtlOrchestrator(
        osm_collector=osm_collector,
        wikidata_collector=wikidata_collector,
        wikipedia_collector=wikipedia_collector,
        bias_audit=bias_audit,
        freshness=freshness,
        accessibility=accessibility,
        dedup=dedup,
        place_repository=place_repo,
        export_path=Path("data/master_data_core.json"),
        local_listings_collector=local_listings_collector,
        event_rss_collector=event_rss_collector,
        events_export_path=Path("data/events_cache.json"),
    )
