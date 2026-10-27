"""
ETL Orchestrator — implements the exact 10-step pipeline from the project
brief:

  1. Collect POIs from OpenStreetMap
  2. Enrich using Wikidata
  3. Enrich from Wikipedia
  4. Calculate Bias Index
  5. Generate tags
  6. Calculate freshness
  7. Accessibility detection
  8. Deduplicate
  9. Store in PostgreSQL
  10. Export MasterData JSON

Runs unattended (cron/APScheduler calls `run()`); no step is manual. A
source failing (SourceUnavailable) is logged and that step's contribution
is skipped for this run — the pipeline does not stop, and nothing is
back-filled with fake data to "complete" a failed step.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from layer0.application.accessibility import AccessibilityDetector
from shared.place_taxonomy import canonical_category
from layer0.application.bias_audit import BiasAuditService
from layer0.application.bias_signal_estimator import BiasSignalEstimator
from layer0.application.dedup import DedupService
from layer0.application.freshness import FreshnessService
from layer0.application.opening_hours_parser import OpeningHoursParser
from layer0.application.place_enricher import PlaceEnricher
from layer0.domain.entities import (
    AccessibilityInfo,
    Coordinates,
    DataSource,
    OpeningHours,
    Place,
)
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.collectors.local_listings_collector import ListingRecord, LocalListingsCollector
from layer0.infrastructure.collectors.osm_collector import OsmCollector, OsmElement
from layer0.infrastructure.collectors.wikidata_collector import WikidataCollector
from layer0.infrastructure.collectors.wikipedia_collector import WikipediaCollector
from layer0.infrastructure.http_client import SourceUnavailable
from layer0.infrastructure.collectors.event_rss_collector import EventRssCollector

logger = logging.getLogger("groundzero.layer0.etl")

# OSM tag -> Ground Zero category mapping. Deliberately a plain dict (not
# a giant if/elif) so it's the single place to extend when a new OSM tag
# value needs mapping during the "deepen Layer 0" pass.
_CATEGORY_MAP = {
    "restaurant": "restaurant", "cafe": "cafe", "fast_food": "street_food",
    "food_court": "food_court", "bakery": "bakery", "confectionery": "dessert_shop",
    "bar": "local_kitchen", "pub": "local_kitchen", "ice_cream": "dessert_shop",
    "marketplace": "market", "place_of_worship": "heritage_site",
    "museum": "museum", "gallery": "art_gallery", "library": "library",
    "theatre": "theatre", "arts_centre": "art_gallery",
    "beach": "beach", "water": "lake", "wood": "nature_spot", "peak": "viewpoint",
    "park": "park", "garden": "garden", "nature_reserve": "nature_spot",
    "beach_resort": "beach", "attraction": "tourist_attraction",
    "viewpoint": "viewpoint", "mall": "shopping_mall", "craft": "craft_centre",
    "monument": "heritage_site", "memorial": "heritage_site", "church": "heritage_site",
    "heritage": "heritage_site",
    # Expanded coverage (Aug 2026 pass — see Section on database completeness):
    "fountain": "attraction", "boat_rental": "attraction", "ferry_terminal": "transit_point",
    "planetarium": "museum", "hotel": "lodging", "guest_house": "lodging",
    "hostel": "lodging", "camp_site": "lodging", "chalet": "lodging",
    "aquarium": "attraction", "wilderness_hut": "lodging",
    "cave_entrance": "nature_spot", "bay": "beach", "cliff": "viewpoint",
    "spring": "nature_spot", "waterfall": "nature_spot", "hot_spring": "nature_spot",
    "water_park": "attraction", "sports_centre": "attraction", "stadium": "attraction",
    "marina": "attraction", "archaeological_site": "heritage_site",
    "wayside_shrine": "heritage_site", "wayside_cross": "heritage_site",
    "tomb": "heritage_site", "fort": "heritage_site", "manor": "heritage_site",
}


@dataclass
class EtlRunReport:
    started_at: datetime
    finished_at: datetime | None = None
    osm_elements_collected: int = 0
    wikidata_enriched: int = 0
    wikipedia_enriched: int = 0
    places_after_dedup: int = 0
    duplicates_removed: int = 0
    places_stored: int = 0
    sources_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    places_stored: int = 0
    events_collected: int = 0
    sources_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "osm_elements_collected": self.osm_elements_collected,
            "wikidata_enriched": self.wikidata_enriched,
            "wikipedia_enriched": self.wikipedia_enriched,
            "places_after_dedup": self.places_after_dedup,
            "duplicates_removed": self.duplicates_removed,
            "places_stored": self.places_stored,
            "events_collected": self.events_collected,
            "sources_skipped": self.sources_skipped,
            "errors": self.errors,
        }


def _osm_element_to_place(
    element: OsmElement,
    opening_hours_parser: OpeningHoursParser,
    place_enricher: PlaceEnricher,
    bias_signal_estimator: BiasSignalEstimator,
) -> Place | None:
    tags = element.tags
    name = tags.get("name")
    if not name:
        return None  # unnamed nodes are not useful tourism POIs

    category = None
    for key in ("amenity", "tourism", "shop", "natural", "leisure", "historic"):
        if key in tags and tags[key] in _CATEGORY_MAP:
            category = _CATEGORY_MAP[tags[key]]
            break
    category = category or "uncategorized"

    raw_hours = tags.get("opening_hours", "")
    parsed_hours = opening_hours_parser.parse(raw_hours)
    enriched = place_enricher.enrich(category, tags)
    bias_signals = bias_signal_estimator.estimate_from_osm_tags(category, tags)

    return Place(
        id=None,
        name=name,
        category=category,
        coordinates=Coordinates(latitude=element.lat, longitude=element.lon),
        opening_hours=OpeningHours(
            raw=raw_hours,
            days_open=parsed_hours.days_open,
            opens_at=parsed_hours.opens_at,
            closes_at=parsed_hours.closes_at,
        ),
        price_band=enriched.price_band,
        estimated_cost=enriched.estimated_cost,
        tags=[t for t in [tags.get("cuisine"), tags.get("religion")] if t],
        energy_requirement=enriched.energy_requirement,
        crowd_level=enriched.crowd_level,
        season_suitability=enriched.season_suitability,
        tide_dependency=enriched.tide_dependency,
        dwell_time_typical_minutes=enriched.dwell_time_typical_minutes,
        parking=enriched.parking,
        washrooms=enriched.washrooms,
        food_available=enriched.food_available,
        pet_friendly=enriched.pet_friendly,
        family_friendly=enriched.family_friendly,
        kid_friendly=enriched.kid_friendly,
        photography_allowed=enriched.photography_allowed,
        best_time=enriched.best_time,
        etiquette_tag=enriched.etiquette_tag,
        bias_signals=bias_signals,
        source=[DataSource.OSM],
    )


def _listing_record_to_place(
    record: ListingRecord, place_enricher: PlaceEnricher, bias_signal_estimator: BiasSignalEstimator,
    opening_hours_parser: OpeningHoursParser,
) -> Place | None:
    """Converts a ListingRecord (from any registered ListingSource — e.g. a
    curated spreadsheet via SpreadsheetListingSource, or a future
    KarnatakaTourismSource) into the same Place shape OSM produces, so it
    flows through accessibility detection, enrichment, bias audit, dedup,
    and storage identically. No source-specific branching needed anywhere
    downstream — this is the one seam a new source's output has to fit
    through.

    Every field a curator actually provided on the record is used as-is
    (a human who filled in a spreadsheet cell knows more about that one
    field than any category-level default). Anything left blank on the
    record falls back to PlaceEnricher's category-level prior — exactly
    the same honest "real value, else defensible default, never a guess"
    rule the OSM path follows.
    """
    if record.lat is None or record.lon is None:
        return None  # can't place it on the map without coordinates

    # Curators type whatever word feels natural ("temple", "mosque", "hotel").
    # Normalise to the same vocabulary the OSM path produces, so enrichment
    # priors, the etiquette note, Purpose.SPIRITUAL matching and itinerary
    # eligibility all treat spreadsheet places exactly like OSM ones. The
    # curator's own word is kept as a tag — nothing is lost.
    raw_category = (record.category or "").strip()
    category = canonical_category(raw_category)
    enriched = place_enricher.enrich(category, {})  # listing sources don't carry raw OSM tags
    bias_signals = bias_signal_estimator.estimate_from_osm_tags(category, {})

    # A curator's own local_percentage/media_mentions estimate is a real
    # signal (arguably a better one than the category-level prior — see
    # bias_signal_estimator.py's honesty note on why that prior is
    # heuristic-only), so it overrides the estimator's guess when given.
    if record.local_percentage_hint is not None:
        bias_signals.local_percentage = record.local_percentage_hint
    if record.media_mentions_hint is not None:
        bias_signals.media_mentions = record.media_mentions_hint

    raw_hours = record.opening_hours_raw or ""
    parsed_hours = opening_hours_parser.parse(raw_hours) if raw_hours else None

    return Place(
        id=None,
        name=record.name,
        category=category,
        coordinates=Coordinates(latitude=record.lat, longitude=record.lon),
        opening_hours=OpeningHours(
            raw=raw_hours,
            days_open=parsed_hours.days_open if parsed_hours else [],
            opens_at=parsed_hours.opens_at if parsed_hours else None,
            closes_at=parsed_hours.closes_at if parsed_hours else None,
        ),
        price_band=_price_band_from_str(record.price_band) or enriched.price_band,
        estimated_cost=record.estimated_cost if record.estimated_cost is not None else enriched.estimated_cost,
        tags=list(dict.fromkeys(
            list(record.tags)
            + ([raw_category.lower().replace(" ", "_")] if raw_category and raw_category.lower().replace(" ", "_") != category else [])
        )),
        energy_requirement=_energy_from_str(record.energy_requirement) or enriched.energy_requirement,
        crowd_level=_crowd_from_str(record.crowd_level) or enriched.crowd_level,
        season_suitability=list(record.season_suitability) or enriched.season_suitability,
        tide_dependency=record.tide_dependency if record.tide_dependency is not None else enriched.tide_dependency,
        dwell_time_typical_minutes=(
            record.dwell_time_typical_minutes
            if record.dwell_time_typical_minutes is not None
            else enriched.dwell_time_typical_minutes
        ),
        parking=record.parking if record.parking is not None else enriched.parking,
        washrooms=record.washrooms if record.washrooms is not None else enriched.washrooms,
        food_available=record.food_available if record.food_available is not None else enriched.food_available,
        pet_friendly=enriched.pet_friendly,
        family_friendly=record.family_friendly if record.family_friendly is not None else enriched.family_friendly,
        kid_friendly=record.kid_friendly if record.kid_friendly is not None else enriched.kid_friendly,
        photography_allowed=(
            record.photography_allowed if record.photography_allowed is not None else enriched.photography_allowed
        ),
        best_time=record.best_time or enriched.best_time,
        etiquette_tag=record.etiquette_tag or enriched.etiquette_tag,
        description=record.description,
        bias_signals=bias_signals,
        source=[DataSource.LOCAL_LISTING],
    )


def _price_band_from_str(value: str | None):
    if not value:
        return None
    from layer0.domain.entities import PriceBand
    try:
        return PriceBand(value.strip().lower())
    except ValueError:
        return None


def _energy_from_str(value: str | None):
    if not value:
        return None
    from layer0.domain.entities import EnergyRequirement
    try:
        return EnergyRequirement(value.strip().lower())
    except ValueError:
        return None


def _crowd_from_str(value: str | None):
    if not value:
        return None
    from layer0.domain.entities import CrowdLevel
    try:
        return CrowdLevel(value.strip().lower())
    except ValueError:
        return None


class EtlOrchestrator:
    def __init__(
        self,
        osm_collector: OsmCollector,
        wikidata_collector: WikidataCollector,
        wikipedia_collector: WikipediaCollector,
        bias_audit: BiasAuditService,
        freshness: FreshnessService,
        accessibility: AccessibilityDetector,
        dedup: DedupService,
        place_repository: PlaceRepository,
        export_path: Path,
        local_listings_collector: LocalListingsCollector | None = None,
        opening_hours_parser: OpeningHoursParser | None = None,
        place_enricher: PlaceEnricher | None = None,
        bias_signal_estimator: BiasSignalEstimator | None = None,
        enrichment_concurrency: int = 8,
        event_rss_collector: EventRssCollector | None = None,
        events_export_path: Path | None = None,
    ):
        self.osm_collector = osm_collector
        self.wikidata_collector = wikidata_collector
        self.wikipedia_collector = wikipedia_collector
        self.bias_audit = bias_audit
        self.freshness = freshness
        self.accessibility = accessibility
        self.dedup = dedup
        self.place_repository = place_repository
        self.export_path = export_path
        # None (no sources registered yet) is the correct default — there is
        # no single stable public API for Karnataka Tourism / local listings
        # today. Registering one later (see local_listings_collector.py) is
        # a matter of instantiating a ListingSource and passing a collector
        # here; nothing else in this class changes.
        self.local_listings_collector = local_listings_collector
        self.opening_hours_parser = opening_hours_parser or OpeningHoursParser()
        self.place_enricher = place_enricher or PlaceEnricher()
        self.bias_signal_estimator = bias_signal_estimator or BiasSignalEstimator()
        # Caps concurrent Wikidata/Wikipedia requests during enrichment —
        # an architectural audit found this loop was fully sequential,
        # meaning N places meant ~2N sequential HTTP round trips. A public
        # Overpass/Wikidata-scale service still needs a concurrency cap
        # (not unlimited asyncio.gather) to stay a reasonable API citizen.
        self.enrichment_concurrency = enrichment_concurrency
        self.event_rss_collector = event_rss_collector
        self.events_export_path = events_export_path or Path("data/events_cache.json")


    async def run(self, bbox: tuple[float, float, float, float]) -> EtlRunReport:
        report = EtlRunReport(started_at=datetime.now(timezone.utc))
        south, west, north, east = bbox

        # Step 1: Collect POIs from OpenStreetMap
        try:
            osm_elements = await self.osm_collector.collect(south, west, north, east)
            report.osm_elements_collected = len(osm_elements)
        except SourceUnavailable as exc:
            report.sources_skipped.append("openstreetmap")
            report.errors.append(str(exc))
            osm_elements = []

        candidate_places: list[Place] = []
        for element in osm_elements:
            place = _osm_element_to_place(
                element, self.opening_hours_parser, self.place_enricher, self.bias_signal_estimator
            )
            if place is None:
                continue

            # Step 7: Accessibility detection (done per-place, right after
            # we have the raw OSM tags available)
            place.accessibility = self.accessibility.detect(element.tags)
            candidate_places.append(place)

        # Local listings (Karnataka Tourism / local portals — Step 1b, same
        # tier as OSM collection). Empty/no-op today (no sources registered
        # — see EtlOrchestrator.__init__ docstring); the moment a real
        # ListingSource is registered, its output flows through this exact
        # same path (accessibility default, enrichment, bias audit, dedup,
        # storage) with no changes anywhere else in this file.
        if self.local_listings_collector is not None:
            try:
                listing_records = await self.local_listings_collector.collect()
            except Exception as exc:  # noqa: BLE001 — a misbehaving source must not kill the run
                report.errors.append(f"local listings collection failed: {exc}")
                listing_records = []

            for record in listing_records:
                place = _listing_record_to_place(
                    record, self.place_enricher, self.bias_signal_estimator, self.opening_hours_parser
                )
                if place is not None:
                    if record.accessibility_tags:
                        place.accessibility = AccessibilityInfo(
                            tags=list(record.accessibility_tags),
                            wheelchair="wheelchair" in record.accessibility_tags,
                            stairs="stairs-only" in record.accessibility_tags,
                        )
                    candidate_places.append(place)

        # Steps 2 & 3: Enrich using Wikidata, then Wikipedia. Concurrency-
        # capped (not unlimited asyncio.gather) — previously fully
        # sequential, confirmed by an audit to mean ~2N sequential HTTP
        # round trips for N places. A semaphore keeps this a reasonable
        # citizen of the public Wikidata/Wikipedia endpoints rather than
        # firing hundreds of simultaneous requests.
        semaphore = asyncio.Semaphore(self.enrichment_concurrency)
        wikidata_skipped = False
        wikipedia_skipped = False

        async def _enrich_one(place: Place) -> None:
            nonlocal wikidata_skipped, wikipedia_skipped
            has_wikidata_match = False
            has_wikipedia_match = False
            summary_length = 0

            async with semaphore:
                try:
                    enrichment = await self.wikidata_collector.enrich(
                        place.coordinates.latitude, place.coordinates.longitude, place.name
                    )
                except SourceUnavailable as exc:
                    wikidata_skipped = True
                    report.errors.append(str(exc))
                    enrichment = None

                if enrichment is not None:
                    has_wikidata_match = True
                    report.wikidata_enriched += 1
                    place.description = enrichment.description
                    place.source.append(DataSource.WIKIDATA)

                    if enrichment.wikipedia_title:
                        try:
                            summary = await self.wikipedia_collector.summary(enrichment.wikipedia_title)
                        except SourceUnavailable as exc:
                            wikipedia_skipped = True
                            report.errors.append(str(exc))
                            summary = None

                        if summary:
                            has_wikipedia_match = True
                            report.wikipedia_enriched += 1
                            place.wiki_summary = summary.extract
                            place.source.append(DataSource.WIKIPEDIA)
                            summary_length = len(summary.extract)

            # Step 4 (partial): refine bias signals with what enrichment
            # just told us (real notability signal), ahead of the full
            # Bias Index computation later in the pipeline.
            self.bias_signal_estimator.refine_with_enrichment(
                place.bias_signals, has_wikidata_match, has_wikipedia_match, summary_length
            )

        await asyncio.gather(*(_enrich_one(place) for place in candidate_places))
        if wikidata_skipped:
            report.sources_skipped.append("wikidata")
        if wikipedia_skipped:
            report.sources_skipped.append("wikipedia")

        # Step 5: Generate tags (derived from category + enrichment, kept
        # simple and deterministic here; the "deepen Layer 0" pass can add
        # an NLP-based tag extractor from wiki_summary/description text)
        for place in candidate_places:
            if place.category not in place.tags:
                place.tags.append(place.category)
            if place.wiki_summary:
                place.tags.append("has-wiki-context")

        # Step 8: Deduplicate against already-stored places AND within this
        # batch (OSM alone can return the same POI as both a node and a way)
        deduped: list[Place] = []
        for place in candidate_places:
            existing_matches = await self.place_repository.find_duplicates(place)
            match = self.dedup.find_best_match(place, existing_matches + deduped)
            if match:
                merged = self.dedup.merge(match.existing, place)
                if merged not in deduped and match.existing in deduped:
                    pass  # already tracked by reference
                elif match.existing not in deduped:
                    deduped.append(merged)
            else:
                deduped.append(place)
        report.places_after_dedup = len(deduped)
        report.duplicates_removed = len(candidate_places) - len(deduped)

        # Step 4: Calculate Bias Index (after dedup, so merged bias_signals
        # from multiple sources are the ones scored — not a pre-merge signal)
        # Step 6: Calculate freshness
        now = datetime.now(timezone.utc)
        for place in deduped:
            place.last_verified_at = now
            breakdown = self.bias_audit.compute(place.bias_signals)
            place.bias_index = breakdown.bias_index
            place.grade = self.bias_audit.grade_for(breakdown.bias_index)
            place.freshness_score = self.freshness.score(place, now=now)

        # Step 9: Store in PostgreSQL — one batch transaction rather than
        # one commit per place (see PostgresPlaceRepository.bulk_upsert
        # for why this was a confirmed performance bottleneck).
        try:
            stored_places = await self.place_repository.bulk_upsert(deduped)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"bulk store failed: {exc}")
            stored_places = []
        report.places_stored = len(stored_places)

        # Step 10: Export MasterData JSON
        self._export_master_data(stored_places)

        if self.event_rss_collector is not None:
            try:
                events = await self.event_rss_collector.collect()
                report.events_collected = len(events)
                self._export_events(events)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"event RSS collection failed: {exc}")
        else:
            report.sources_skipped.append("event_rss (no collector registered)")

        report.finished_at = datetime.now(timezone.utc)
        return report

    def _export_events(self, events: list) -> None:
        self.events_export_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = [
            {
                "title": e.title,
                "published": e.published.isoformat() if e.published else None,
                "link": e.link,
                "summary": e.summary,
                "feed_url": e.feed_url,
            }
            for e in events
        ]
        with open(self.events_export_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        logger.info("Exported %d events to %s", len(serializable), self.events_export_path)

    def _export_master_data(self, places: list[Place]) -> None:
        from dataclasses import asdict

        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = []
        for place in places:
            data = asdict(place)
            data["price_band"] = place.price_band.value
            data["energy_requirement"] = place.energy_requirement.value
            data["crowd_level"] = place.crowd_level.value
            data["grade"] = place.grade.value if place.grade else None
            data["source"] = [s.value for s in place.source]
            for dt_field in ("last_verified_at", "created_at", "updated_at"):
                if data.get(dt_field):
                    data[dt_field] = data[dt_field].isoformat()
            serializable.append(data)

        with open(self.export_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        logger.info("Exported %d places to %s", len(serializable), self.export_path)
