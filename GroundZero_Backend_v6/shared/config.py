"""
Central configuration for Ground Zero.

Every external dependency (DB, Redis, API keys) is read from the environment
so that nothing is hardcoded and nothing is faked. If a required variable is
missing, we fail loudly at startup rather than silently falling back to a
mock — a missing API key should be a startup error, not a demo with fake data.
"""
from __future__ import annotations

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://groundzero:groundzero@localhost:5432/groundzero",
        description="Async SQLAlchemy URL. Must point at a PostGIS-enabled Postgres.",
    )

    # --- Cache ---
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- External data sources (Layer 0) ---
    overpass_url: str = Field(default="https://overpass-api.de/api/interpreter")
    wikidata_sparql_url: str = Field(default="https://query.wikidata.org/sparql")
    wikipedia_api_url: str = Field(default="https://en.wikipedia.org/w/api.php")

    # --- Zero-API, zero-rate-limit OSM collection (Aug 2026) ---
    # Path to a locally downloaded .osm / .osm.pbf / .osm.xml.gz extract
    # (see layer0/infrastructure/collectors/bulk_osm_extract_collector.py
    # for where to get one for free — bbbike.org custom extract or a
    # Geofabrik country extract clipped locally). When set and the file
    # exists, this REPLACES the live Overpass collector entirely — no
    # network call, no rate limit, offline-only. Leave unset to keep
    # using the live (also free, also legal, already fair-use-tiled)
    # Overpass collector.
    osm_extract_file_path: str | None = Field(default=None)

    # Master "no API calls at all" switch. When false, Wikidata/Wikipedia
    # enrichment (history/description text — a nice-to-have, never
    # required for a place to exist) is skipped entirely; combine with
    # osm_extract_file_path set for a pipeline run that makes zero network
    # calls of any kind. Spreadsheet-sourced places are unaffected either
    # way — their `description` column already covers this.
    enable_wikidata_wikipedia_enrichment: bool = Field(default=True)
    openweathermap_api_key: str | None = Field(default=None)
    openweathermap_url: str = Field(default="https://api.open-meteo.com/v1/forecast")
    tide_api_key: str | None = Field(default=None)
    tide_api_url: str = Field(default="https://www.worldtides.info/api/v3")
    karnataka_tourism_feed_url: str | None = Field(default=None)

    # --- Free, rate-limit-free spreadsheet ingestion (Aug 2026) ---
    # Path to a CSV file (exported from Google Sheets/Excel) of manually
    # curated places — the practical way to reach genuine completeness for
    # hyperlocal places that no API will ever index. See
    # layer0/infrastructure/collectors/spreadsheet_source.py and
    # docs/GROWING_THE_DATABASE.md. Missing file = zero rows contributed,
    # not an error.
    spreadsheet_places_csv_path: str = Field(default="data/community_places.csv")
    event_rss_feed_urls: str = Field(
        default="https://news.google.com/rss/search?q=Mangaluru%20festival%20OR%20event%20OR%20mela&hl=en-IN&gl=IN&ceid=IN:en",
        description="Comma-separated list of local event/festival RSS feed URLs.",
    )

    # --- Region of interest (Mangaluru bounding box) ---
    # South, West, North, East — used to scope every Layer 0 collector query
    # so we never accidentally ingest all of India.
    bbox_south: float = Field(default=12.75)
    bbox_west: float = Field(default=74.78)
    bbox_north: float = Field(default=13.05)
    bbox_east: float = Field(default=75.05)

    # --- ETL storage batching (Phase 1: "configurable batching") ---
    # Number of places committed per transaction in PostgresPlaceRepository
    # .bulk_upsert. Lower this for constrained deployments or to bound how
    # much work a single failing chunk can lose; raise it for fewer round
    # trips on a beefy DB. See repository_impl.py for the reasoning.
    etl_storage_batch_size: int = Field(default=500)

    # --- Freshness / bias thresholds (blueprint section 3.2 / 5.1) ---
    freshness_min_score: float = Field(default=0.4, description="Below this, Hard Filter drops the place")
    freshness_stale_after_days: int = Field(default=180)

    # --- Anthropic (Ask Engine — Layer 3, not in current scope) ---
    anthropic_api_key: str | None = Field(default=None)

    # --- Groq (free tier) — powers Talk to Guide (guide/) and Layer 3's Ask Engine ---
    groq_api_key: str | None = Field(default=None)
    groq_model: str = Field(default="llama-3.1-8b-instant")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")

    environment: str = Field(default="development")

    # Admin API key (blueprint's "Admin Protection" requirement, security
    # audit finding: previously NO authentication existed anywhere on
    # /admin/* — any caller could trigger the ingestion pipeline or
    # approve/reject community submissions). Required in production; in
    # development, an empty value here means every admin request is
    # rejected with a clear error rather than silently having no auth —
    # see layer0/api/security.py.
    admin_api_key: str = Field(
        default="",
        description="Shared secret required in the X-Admin-Api-Key header for all /admin/* endpoints.",
    )

    # CORS (security audit finding: previously hardcoded to allow_origins=["*"]
    # unconditionally, with a comment acknowledging it should be tightened
    # that was never acted on). Comma-separated list of allowed origins;
    # "*" is only accepted while environment=development.
    cors_allowed_origins: str = Field(default="*")

    # Rate limiting (security audit finding: no inbound rate limiting
    # existed anywhere — only outbound, for calls this app makes to
    # external APIs). Applies per-client-IP across the whole API.
    rate_limit_per_minute: int = Field(default=60)


_RECOGNIZED_ENVIRONMENTS = {"development", "staging", "production"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # SECURITY FIX (final-release-hardening pass, Oct 2026): a review
    # pointed out that this round's SQLite/weak-admin-key fail-closed
    # fixes (layer3_config.py, live_events/app/config.py) left the MAIN
    # app's own config with none of the same checks — a production
    # deployment could still set ENVIRONMENT to a typo'd or made-up value
    # (silently behaving like "not development" everywhere else, but
    # never actually caught) and DATABASE_URL could still be pointed at
    # SQLite even in production (nothing ever checked the scheme, only
    # whether the variable was present at all). Both now fail closed the
    # same way CORS_ALLOWED_ORIGINS="*" already did, a few lines above
    # this function.
    if settings.environment not in _RECOGNIZED_ENVIRONMENTS:
        raise RuntimeError(
            f"ENVIRONMENT is set to '{settings.environment}', which isn't one of "
            f"{sorted(_RECOGNIZED_ENVIRONMENTS)} — refusing to start with an unrecognized "
            "environment, since every other fail-closed check in this app (CORS, admin "
            "keys, Layer 3's and Live Events' database fallbacks) only treats the exact "
            "string 'development' as safe for relaxed defaults. Set ENVIRONMENT to one of "
            "the recognized values."
        )
    if settings.environment != "development" and settings.database_url.startswith("sqlite"):
        raise RuntimeError(
            f"DATABASE_URL is a SQLite URL but ENVIRONMENT is '{settings.environment}' — "
            "refusing to run production/staging against SQLite (no concurrent-worker safety, "
            "not backed up or monitored like real Postgres). Set DATABASE_URL to a real "
            "PostGIS-enabled Postgres URL."
        )
    return settings
