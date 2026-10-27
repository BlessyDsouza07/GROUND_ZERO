"""
Karnataka Tourism / local listings collector (blueprint 3.1 sources #3-4).

Unlike OSM/Wikidata/Wikipedia, there is no single stable public API for
Karnataka Tourism or Mangaluru local listing sites — this genuinely varies
by source and changes over time. This collector defines the *contract*
(what a listing looks like once collected) and a pluggable `ListingSource`
interface so real scrapers/APIs can be registered per site without
touching the ETL orchestrator. Each concrete source is responsible for its
own real HTTP calls; none of them return canned data.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from layer0.infrastructure.http_client import ResilientHttpClient

logger = logging.getLogger("groundzero.layer0.collectors.local_listings")


@dataclass(frozen=True)
class ListingRecord:
    name: str
    category: str
    lat: float | None
    lon: float | None
    address: str | None
    description: str | None
    source_url: str
    source_name: str

    # --- Optional rich fields (Aug 2026) ---------------------------------
    # A ListingSource (e.g. a curated spreadsheet — see
    # spreadsheet_source.py) can supply as much or as little of this as a
    # human curator actually knows about the place. Anything left as None
    # falls back to PlaceEnricher's category-level default in
    # etl_orchestrator._listing_record_to_place, exactly like an
    # unenriched OSM tag would. Nothing here is invented if the source
    # doesn't provide it.
    opening_hours_raw: str | None = None
    tags: tuple[str, ...] = ()
    price_band: str | None = None            # "free" | "budget" | "moderate" | "premium"
    estimated_cost: float | None = None      # INR
    energy_requirement: str | None = None    # "low" | "moderate" | "high"
    crowd_level: str | None = None           # "low" | "moderate" | "high" | "variable"
    dwell_time_typical_minutes: int | None = None
    tide_dependency: bool | None = None
    season_suitability: tuple[str, ...] = ()
    accessibility_tags: tuple[str, ...] = ()
    etiquette_tag: str | None = None
    best_time: str | None = None
    parking: bool | None = None
    washrooms: bool | None = None
    food_available: bool | None = None
    family_friendly: bool | None = None
    kid_friendly: bool | None = None
    photography_allowed: bool | None = None
    contact_phone: str | None = None

    # A human curator is exactly the source the blueprint's Bias Audit
    # (3.2) needs for genuine Local Secrets and hyped spots alike — no
    # media-mention counting API exists in this system's data sources
    # (see bias_signal_estimator.py's own honesty note), but a local
    # person filling in a spreadsheet often knows both of these directly.
    # Left as None when the curator doesn't know, same as everywhere else.
    local_percentage_hint: float | None = None  # 0.0-1.0
    media_mentions_hint: int | None = None


class ListingSource(ABC):
    """One implementation per real site/API registered in config. e.g. a
    `KarnatakaTourismSource` that hits the department's actual listings
    endpoint once its URL/auth is known, or an RSS/JSON feed for a specific
    Mangaluru tourism portal."""

    name: str

    @abstractmethod
    async def fetch(self) -> list[ListingRecord]:
        ...


class LocalListingsCollector:
    """Aggregates results from every registered ListingSource. A source
    that fails (network, schema change) is logged and skipped — it does
    not take down the rest of the ETL run."""

    def __init__(self, http_client: ResilientHttpClient, sources: list[ListingSource]):
        self.http_client = http_client
        self.sources = sources

    async def collect(self) -> list[ListingRecord]:
        all_records: list[ListingRecord] = []
        for source in self.sources:
            try:
                records = await source.fetch()
                logger.info("%s: collected %d listings", source.name, len(records))
                all_records.extend(records)
            except Exception as exc:  # noqa: BLE001 - intentionally broad; log and continue
                logger.warning("%s: failed this run (%s), skipping", source.name, exc)
        return all_records
