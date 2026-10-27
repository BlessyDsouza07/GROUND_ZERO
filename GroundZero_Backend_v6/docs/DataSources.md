# Ground Zero — Data Sources

This document lists every external data source Layer 0's ETL pipeline
uses, why it's used, its licence, attribution requirements, how often it's
queried, and which module implements the integration. It exists so that
(a) anyone auditing the project can verify every source is legitimate and
properly licensed, and (b) nobody accidentally adds a scraped or
unlicensed source without updating this file.

**Status note (accurate as of this pass):** every collector below queries
its real, live API — none return canned or fixture data. This project's
own sandboxed build/verification environment cannot reach any of these
five external hosts (network egress is restricted to package registries),
so the *code* has been reviewed and unit-tested with mocked HTTP, but a
live end-to-end import against these real endpoints has not yet been run
from within that environment. It must be run and verified from a machine
with open network egress before this project is considered
production-ready for Phase 2/3/8 of the completion checklist.

---

## 1. OpenStreetMap (via Overpass API)

- **Purpose:** Primary source of Points of Interest (POIs) — restaurants,
  cafes, museums, beaches, parks, heritage sites, and every other category
  in the blueprint's tag list. This is the backbone of the Master Data
  Core.
- **Endpoint:** `https://overpass-api.de/api/interpreter` (configurable
  via `overpass_url` in `shared/config.py`)
- **Licence:** [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
  OSM's cartography is CC BY-SA; the underlying data is ODbL.
- **Attribution requirement:** Any public-facing use of OSM data must
  credit **"© OpenStreetMap contributors"**, and any produced/derived
  database must itself be released under ODbL or a compatible licence
  ("share-alike"). Ground Zero's Master Data Core, being a derived
  database, inherits this obligation.
- **Update frequency:** Queried per ETL run (currently manually triggered;
  intended to run on a schedule — see Phase 5/Admin Operations). OSM data
  itself changes continuously; Ground Zero re-queries rather than caching
  indefinitely, so `freshness_stale_after_days` in config governs when a
  place is re-verified.
- **Implementation:** `layer0/infrastructure/collectors/osm_collector.py`
  — tiled/gridded queries with per-tile concurrency limits, boundary
  deduplication by `(osm_type, osm_id)`.

## 2. Wikidata

- **Purpose:** Structured enrichment for OSM-sourced places — description,
  inception date, heritage status, and a Wikipedia sitelink used to fetch
  a summary next.
- **Endpoint:** `https://query.wikidata.org/sparql` (configurable via
  `wikidata_sparql_url`)
- **Licence:** Wikidata's structured data is released under
  [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (public
  domain dedication).
- **Attribution requirement:** None legally required under CC0, but
  crediting Wikidata as a source is good practice and is included in
  Ground Zero's About/Attribution section regardless.
- **Update frequency:** Queried per place during ETL enrichment
  (concurrency-capped, see `enrichment_concurrency` in
  `EtlOrchestrator`), not cached separately from the Master Data Core's
  own freshness cycle.
- **Implementation:**
  `layer0/infrastructure/collectors/wikidata_collector.py`

## 3. Wikipedia

- **Purpose:** Plain-text summary extract for places that have a matched
  Wikidata sitelink, stored as `wiki_summary` on the Place record.
- **Endpoint:** Wikipedia's REST summary endpoint, `en.wikipedia.org`
  (configurable via `wikipedia_api_url`)
- **Licence:** Article text is [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/);
  some content may additionally be GFDL-licensed.
- **Attribution requirement:** Credit **"Wikipedia"** and the specific
  article where its text is displayed, and — because BY-SA is
  share-alike — any substantial reuse of the article text itself (not
  just linking to it) must be released under a compatible licence.
  Ground Zero stores short extracts for context, not full reproductions,
  precisely to stay within fair, low-risk use of this source.
- **Update frequency:** Queried per matched place during ETL enrichment.
- **Implementation:**
  `layer0/infrastructure/collectors/wikipedia_collector.py`

## 4. OpenWeatherMap

- **Purpose:** Two uses — (a) tagging `season_suitability` at ingestion
  time, and (b) live weather-adaptive itinerary scheduling at Layer 2
  HIVE-run time (this collector is called again outside the ETL, at
  recommendation time).
- **Endpoint:** OpenWeatherMap One Call API 3.0,
  `api.openweathermap.org` (configurable via `openweathermap_url`)
- **Licence:** Commercial API, requires an API key
  (`openweathermap_api_key` in config). Free tier has a request-volume
  cap; usage terms are governed by OpenWeatherMap's own ToS, not an open
  data licence — check the current plan's terms before scaling request
  volume.
- **Attribution requirement:** OpenWeatherMap's terms request attribution
  with a link back to openweathermap.org where weather data is displayed
  publicly; confirm current wording against the plan in use.
- **Update frequency:** Ingestion-time tagging is per ETL run; live
  scheduling calls happen per user recommendation request, not batched.
- **Implementation:**
  `layer0/infrastructure/collectors/weather_collector.py`

## 5. WorldTides

- **Purpose:** Tide state for `tide_dependency` places — coastal
  viewpoints, beaches — both at ingestion (tagging) and by Layer 2/3 for
  tide-suitability scoring.
- **Endpoint:** WorldTides API v3, `www.worldtides.info`
  (configurable via `tide_api_url`)
- **Licence:** Commercial API, requires an API key (`tide_api_key`).
  Paid/credit-based usage; governed by WorldTides' own ToS.
- **Attribution requirement:** Check current WorldTides ToS for the
  specific plan in use; commercial tide-data providers commonly require
  attribution or at minimum prohibit redistributing raw tide data as a
  standalone product. Ground Zero only surfaces a derived
  suitability tag, not raw tide tables, to stay clearly within
  reasonable use.
- **Update frequency:** Per coastal place, at ingestion and (for Layer 2/3
  scoring) at recommendation time.
- **Implementation:** `layer0/infrastructure/collectors/tide_collector.py`

## 6. Local event / festival RSS feeds

- **Purpose:** Feeds a "nearby events" signal and freshness for
  festival-linked places.
- **Endpoint:** Configurable, comma-separated list via
  `event_rss_feed_urls`. **No feeds are configured by default** — this is
  intentionally empty until specific, permitted local RSS feeds are
  identified and added; the collector does not scrape or invent feed URLs.
- **Licence:** RSS feed content licensing is source-specific — whoever
  publishes each feed sets its terms. Each feed URL added to
  `event_rss_feed_urls` must be individually checked for permitted use
  before being added to production config.
- **Attribution requirement:** Source-specific; document per feed when
  one is added.
- **Update frequency:** Per ETL run, standard RSS polling.
- **Implementation:**
  `layer0/infrastructure/collectors/event_rss_collector.py`

## 7. Local listings (Karnataka Tourism / local portals)

- **Purpose:** A pluggable slot for local tourism-board or listings data,
  distinct from the community-submission workflow.
- **Status:** **No concrete source is registered.** There is no single
  stable public API for Karnataka Tourism or Mangaluru listings sites
  today. `LocalListingsCollector` defines the contract (`ListingSource`
  interface) so a real source can be plugged in later without touching
  the orchestrator — see
  `layer0/tests/test_etl_local_listings_seam.py` for a proof of that
  seam using a fake source. Nothing here fetches or fabricates data until
  a real, permitted source is registered.
- **Licence / attribution:** To be documented per source when one is
  registered — this section must be updated at that time, not before.
- **Implementation:**
  `layer0/infrastructure/collectors/local_listings_collector.py`

## 8. Community/curator spreadsheet (new, Aug 2026)

- **Purpose:** Free, unlimited-rate ingestion of places that no API
  above will ever index — hyperlocal kitchens, shrines, informal
  viewpoints — filled in directly by Carol's team or trusted local
  contributors. See `docs/GROWING_THE_DATABASE.md` for the full workflow
  and column reference.
- **Endpoint:** None — reads a local CSV file at
  `spreadsheet_places_csv_path` (default `data/community_places.csv`).
  No network call, no rate limit, no API key.
- **Licence:** The data is Carol's team's own entry, not scraped from any
  third party — no licence question applies, provided contributors only
  enter factual information they've personally verified (opening hours,
  description, etc.), not copied text from another site's listing.
- **Update frequency:** Read fresh on every ETL run, same as every other
  source — edits to the CSV take effect on the next
  `/admin/pipeline/run`.
- **Implementation:**
  `layer0/infrastructure/collectors/spreadsheet_source.py`

---

## Data Governance

- **No illegal or ToS-violating scraping.** Every source above is queried
  through its official, documented API. There is no scraper anywhere in
  this codebase for Google Maps, TripAdvisor, Booking.com, Zomato, or any
  other platform whose terms of service prohibit automated collection.
- **Explicitly excluded sources:** Google Maps, TripAdvisor, Booking.com
  (and similarly-restrictive platforms) are not, and must not be, used as
  data sources for the Master Data Core. If a future contributor proposes
  one, it needs a documented legal/licensing review first, not a
  silent addition.
- **Community moderation workflow.** Places submitted by users go through
  `CommunitySubmissionService`
  (`layer0/application/community_workflow.py`) and land in a pending
  queue for admin approval/rejection — they are never auto-merged into
  the Master Data Core. See `layer0/api/admin.py` for the moderation
  endpoints and `layer0/tests/test_community_workflow.py` for the
  enforced state machine.
- **Privacy principles.** The Master Data Core stores information about
  *places*, not people. Community submissions collect a description and
  location, not submitter-identifying data beyond what's needed for
  moderation accountability. No collector in this codebase queries or
  stores personal data from third-party sources.
- **Attribution policy.** See `docs/Attribution.md` for the consolidated,
  user-facing attribution text drawn from the licence terms documented
  above. When any source's attribution wording is uncertain or has
  changed, resolve it against that source's own current terms page
  before shipping, since these licence terms are the provider's to change
  and this document reflects a point-in-time reading of them.

## Freshness & re-verification

Every place carries `last_verified_at` and a computed `freshness_score`
(`layer0/application/freshness.py`), and `freshness_stale_after_days` in
`shared/config.py` governs when a place is considered stale and eligible
for re-verification on the next ETL run. This is how the project avoids
serving increasingly outdated information without a person manually
auditing every record.
