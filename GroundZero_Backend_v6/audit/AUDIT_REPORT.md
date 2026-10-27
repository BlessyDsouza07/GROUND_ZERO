# Ground Zero — Production Readiness Audit

Every claim below is backed by a file path, function/class name, or a command actually run against the code in this session. Where I could not verify something (e.g. live external API behavior), I say so explicitly rather than assuming.

---

## LAYER 0 AUDIT

### 1. OpenStreetMap ingestion

**Status: Partial.** Real, correct Overpass QL query code exists and has never been proven to work against live Overpass from any environment I've had access to.

- `layer0/infrastructure/collectors/osm_collector.py` — `OsmCollector.collect()`, `build_overpass_query()`. Builds one query covering 6 OSM tag categories (amenity, tourism, shop, natural, leisure, historic) across ~35 tag values.
- **Pagination: NOT implemented.** One query for the entire bounding box, `[out:json][timeout:60]`. No tiling/chunking of the bbox, no `[maxsize:]`, no continuation logic. A city-scale query risks Overpass timeout/truncation on the public instance — untested, because this sandbox gets HTTP 403 from `overpass-api.de` (confirmed via direct `curl`, see prior turns).
- **Retry: implemented**, but generically — `layer0/infrastructure/http_client.py`, `ResilientHttpClient.request()`, 3 attempts, exponential backoff, honors `Retry-After` on 429. Not specific to OSM.
- **Rate limiting: reactive only** (honors server's `Retry-After`). No proactive throttling/concurrency cap to respect Overpass's fair-use policy.
- **Does it populate the database: yes**, but only every place gets `estimated_cost=0.0` (`etl_orchestrator.py:118`), and `opening_hours` only stores the raw string — `days_open`/`opens_at`/`closes_at` are **never parsed** anywhere in the codebase. Confirmed by grep: no OSM `opening_hours` syntax parser exists.
- **How many POIs can it ingest: unknown.** No cap in code; bounded by whatever Overpass returns for one query in 60s. Never run against live data.

### 2. Wikidata enrichment

**Status: Partial.**
- `layer0/infrastructure/collectors/wikidata_collector.py` — `WikidataCollector.enrich()`, real SPARQL geosearch query (`build_nearby_query`).
- Fields fetched: `description`, `heritage_status`, `wikipedia_title`, `image_url`.
- **Fields actually used: only `description` and `wikipedia_title`** (`etl_orchestrator.py:238,241`). `heritage_status` and `image_url` are fetched and silently discarded — never written to `Place`, no `image_url` field exists on the domain model at all.
- Missing entities handled: `if not bindings: return None` (line 74-75), orchestrator checks for `None` and continues.
- Retry: inherited from `ResilientHttpClient`.

### 3. Wikipedia enrichment

**Status: Partial.**
- `layer0/infrastructure/collectors/wikipedia_collector.py` — `WikipediaCollector.summary()`.
- **Language: hardcoded to English**, not configurable. `base_rest_url` defaults to `en.wikipedia.org` and is never overridden in `layer0/api/dependencies.py:get_etl_orchestrator()` — it's called as `WikipediaCollector(http_client)` with no URL argument. Note: `shared/config.py` has a `wikipedia_api_url` setting, but it is **never read by this collector** — dead config.
- Duplicate-summary prevention: not applicable/not tested — one summary per place, 1:1.
- 404 handled (`if response.status_code == 404: return None`).

### 4. Deduplication

**Status: Implemented, with real gaps.**
- `layer0/application/dedup.py` — `DedupService.find_best_match()`, `haversine_meters()`, `name_similarity()` (via `difflib.SequenceMatcher`).
- Distance threshold: **75.0 meters** (`DEFAULT_DISTANCE_THRESHOLD_METERS`).
- Name similarity threshold: **0.82** (`DEFAULT_NAME_SIMILARITY_THRESHOLD`), computed on normalized names (lowercased, punctuation stripped, articles removed).
- Category matching: happens **before** `DedupService` is even called — `PostgresPlaceRepository.find_duplicates()` filters candidates by exact `category` match in the SQL query (`repository_impl.py`). **Confirmed edge case gap**: if the same physical place is miscategorized differently across sources (e.g. OSM tags it `cafe`, a community submission calls it `local_kitchen`), it will **never** be flagged as a duplicate, because the DB query excludes it before name/distance comparison ever runs.
- Merge strategy: union of tags/sources, null-coalescing on description/wiki_summary/etc., max on `media_mentions`, average on `local_percentage`, latest `last_verified_at` wins (`dedup.py:76-102`).
- **No durable external-ID tracking**: `OsmElement.osm_id`/`osm_type` are discarded once converted to `Place` — no column stores the source system's ID, so there's no way to reconcile an edited OSM node against an already-ingested Place except by the same distance+name heuristic every time.

### 5. Bias Index

**Status: Implemented, but the exact formula is an original design choice, not a verified blueprint match — and it never receives real input data for OSM-ingested places.**
- `layer0/application/bias_audit.py` — `BiasAuditService.compute()`. Weighted formula: `0.25×media + 0.35×local + 0.20×commercial + 0.15×popularity + 0.05×sponsored`, log-saturating normalization for unbounded inputs.
- **Important honesty point**: the blueprint (Table 10) gives `bias_index` as an already-known *input* to the Personal Fit Score formula — it never specifies the formula that derives `bias_index` from `media_mentions`/`local_percentage`/etc. These weights and the saturation curve are my own reasonable interpretation, verified only against the qualitative description and grade boundary behavior, not against an exact blueprint formula (none exists to check against). Layer 2's Personal Fit Score *combination* formula, by contrast, **is** verified exactly against Table 10.
- **Critical gap**: for every OSM-ingested place, `bias_signals=BiasSignals()` — i.e. **all defaults** (`etl_orchestrator.py:120`, `_osm_element_to_place()`). `media_mentions`, `local_percentage`, `commercial_flags`, `tourist_popularity`, `sponsored_indicator` are never actually computed from any real signal anywhere in the codebase. Every OSM place gets the identical derived score: with all-default inputs, `bias_index = 0.35×(1-0) = 0.35` → **every single automatically-ingested place is graded "balanced," regardless of its actual character.** Only community submissions get a non-default `local_percentage` (hardcoded `0.85`, `layer0/api/routes.py`).

### 6. Accessibility detection

**Status: Partial — real, but shallow.**
- `layer0/application/accessibility.py` — `AccessibilityDetector.detect()`.
- Populated from real OSM tags: `wheelchair` (yes/no/limited), `stairs-only` (highway=steps), `uneven-terrain` (7 surface values), minimal `sensory_notes` (only `tactile_paving`).
- **Never populated, for any place, by any code path**: `parking`, `washrooms`, `food_available`, `pet_friendly`, `family_friendly`, `kid_friendly`, `photography_allowed`, `etiquette_tag`, `transport_access`, `best_time`. These are real columns in the DB schema and real fields on the domain entity, but `etl_orchestrator.py` never assigns them — confirmed by reading the entire `_osm_element_to_place()` function, which sets exactly: `id, name, category, coordinates, opening_hours(raw only), price_band(heuristic), estimated_cost(always 0), tags(minimal), bias_signals(default), source`. Nothing else.

### 7. Freshness scoring

**Status: Implemented, but "automatic" only in a narrow sense.**
- `layer0/application/freshness.py` — `FreshnessService.score()`, linear decay from 1.0 to 0.0 over `stale_after_days` (default 180).
- Computed as part of every ETL run (`etl_orchestrator.py:289`), always right after setting `last_verified_at = now` — meaning freshness is always ~1.0 immediately post-run, and only decays if the pipeline is re-run later.
- **No scheduler exists.** Grepped the entire codebase for APScheduler/cron/celery — nothing. `requirements.txt` has no scheduling package. The only trigger is a human (or external cron you'd have to set up yourself) calling `POST /admin/pipeline/run`. The docstring's "Runs unattended (cron/APScheduler calls run())" describes an intended deployment pattern, not code that exists.

### 8. Master Data Core — scale

**Status: Not demonstrated at any scale. Currently near-empty.**
- Live-verified in this session with **8 hand-entered real-coordinate places** (for pipeline-testing purposes, not as production seed data) plus 2 community submissions. That is the actual current row count in the one Postgres instance this was tested against.
- No batch insert exists — `etl_orchestrator.py`'s Step 9 calls `place_repository.upsert(place)` **once per place, in a sequential Python loop**, each call its own commit (confirmed in `PostgresPlaceRepository.upsert`, `repository_impl.py`). For thousands of places this is thousands of individual round trips and commits — a real, unaddressed performance bottleneck.
- Enrichment (Wikidata → Wikipedia) also runs **sequentially per place**, no `asyncio.gather` concurrency — for N places this is roughly 2N sequential HTTP round trips.
- **Verdict: cannot currently claim "hundreds or thousands."** Nothing in the codebase prevents it at small-to-moderate scale, but nothing has verified it either, and the sequential I/O pattern would make a full Mangaluru-scale run slow even if Overpass cooperated.

### 9. Community Submission workflow

**Status: Implemented and live-verified end-to-end** — the most solidly proven Layer 0 feature.
- `layer0/application/community_workflow.py` — `CommunitySubmissionService.submit()/approve()/reject()`. Full path: submit → pending → admin approve/reject → bias audit → freshness → `place_repo.upsert()`.
- **Live-verified in this session** via real HTTP calls to a running backend: submitted "Uncle Prakash Toddy Shop," approved it, got back `bias_index=0.0525, grade=authentic` — a real end-to-end round trip, not a unit test with fakes.
- **Real bug found**: `CommunitySubmissionModel.resulting_place_id` (the FK meant to link an approved submission to its resulting `Place` row) is **read** in `repository_impl.py:363` but **never written** anywhere — `update_status()` (line 351-360) only sets `status`, `reviewed_by`, `reviewed_at`. It stays `NULL` forever, even for approved submissions. Confirmed by grep across the entire codebase — zero writes to this field.

### 10. Database — full field audit

Schema is complete (all fields below exist as real columns, live-verified against PostGIS in this session). Population status is the real story:

| Field | In schema? | Ever populated by ETL for OSM places? |
|---|---|---|
| id, name, category, lat/lon | Yes | Yes |
| opening_hours (raw) | Yes | Yes (raw string only) |
| days_open, opens_at, closes_at | Yes | No — never parsed |
| price_band | Yes | Partial — heuristic FREE/BUDGET only; MODERATE/PREMIUM never assigned |
| estimated_cost | Yes | No — always 0.0 |
| tags | Yes | Partial — category name + "has-wiki-context" only |
| local_percentage, media_mentions, commercial_flags, tourist_popularity, sponsored_indicator | Yes | No — always default (0/0.0/False) |
| bias_index, grade | Yes | Yes (computed, but from the all-default signals above) |
| energy_requirement | Yes | No — always default MODERATE |
| crowd_level | Yes | No — always default MODERATE |
| season_suitability | Yes | No — never computed |
| tide_dependency | Yes | No — never set, even for beaches |
| dwell_time_typical_minutes | Yes | No — always default 45 |
| accessibility_tags, wheelchair, stairs | Yes | Yes — real, from OSM tags |
| sensory_notes | Yes | Partial — only tactile_paving checked |
| parking, washrooms, food_available, pet_friendly, family_friendly, kid_friendly, photography_allowed | Yes | No — never set, any of them |
| best_time | Yes | No — never set |
| freshness_score, last_verified_at | Yes | Yes — real |
| temporarily_unavailable | Yes | No — never set (always False) |
| etiquette_tag, transport_access | Yes | No — never set |
| description, wiki_summary | Yes | Partial — only when Wikidata/Wikipedia find a match |
| source | Yes | Yes — real |

**13 of ~30 fields are structurally dead for OSM-ingested data** — present in the schema, never written by any code path.

---

## LAYER 1 AUDIT

**Status: Implemented and the most rigorously tested layer** — 30 automated tests, plus live Redis verification.

- Question flow: `layer1/application/survey_service.py`, `SurveyStep` enum + `_STEP_ORDER`. Matches blueprint Table 3 (Q1–Q9) plus the 4.3–4.7 additions in the documented order (Purpose, Energy, Crowd, Budget, Dietary, Group, Accessibility, Curiosity, Duration, Start time, Language, Return-visitor, Voice, Group-session-setup).
- Validation: `SurveyService._validate()`, enum-based per step, real `InvalidSurveyAnswer` exceptions — unit-tested (`layer1/tests/test_survey_service.py`, 12 tests).
- Redis sessions: `layer1/infrastructure/survey_session_store.py`, `RedisSurveySessionStore` — **live-verified against a real Redis instance** in this session (store/fetch/TTL/delete, plus a full 13-step survey run through Redis, not fakes).
- **Real bug found in the Redis fallback**: `layer1/api/dependencies.py`, `get_session_store()`. The `try/except` around `redis.from_url()` is supposed to fall back to in-memory storage if Redis is down. **It cannot work as documented** — `redis.from_url()` constructs a lazy client and never raises at construction regardless of reachability. Proved empirically in this session: constructing a client against a port nothing listens on succeeds without error. If Redis is genuinely down in production, the first real command inside `SurveyService` will raise an **uncaught** exception, not gracefully degrade.
- Curiosity extraction: `layer1/application/curiosity_extractor.py`, `CuriosityExtractor.extract()` — **a 13-category keyword lexicon (`re.findall` word-boundary matching), not an ML/NLP system.** Honestly labeled as such in its own docstring. Only 13 of the system's ~30 place categories have lexicon entries — curiosity text mentioning e.g. "bakery," "theatre," or "waterfall" (as distinct from "nature") would never match anything.
- **Return Visitor Check is structurally inert in production**: the mechanism (`get_prior_session_for_device`, `get_visited_place_ids`) is correctly wired and passed my earlier unit test — but that test used a `FakeProfileRepository` that hardcoded `get_visited_place_ids` to return `["place-1", "place-2"]`. The **real** implementation reads `TouristProfileModel.visited_log` (`layer1/infrastructure/db/repository_impl.py:103`), and grepping the entire codebase confirms **nothing, anywhere, ever writes to `visited_log`**. No API endpoint marks a place as visited. In the real system, this will always return `[]`.
- TouristProfile generation: `SurveyService.finalize()` — real, complete, all fields populated including the v3 additions (`device_id`, `accessibility_flags`, `companion_language`, `multi_day_count`).

---

## FRONTEND AUDIT

**Status: Functionally wired and visually designed, but unverified on any actual device or simulator (this sandbox cannot render React Native), and has zero automated tests.**

Visual design (this session's pass): `frontend/src/theme/tokens.js`, `SignalRing.js`, `GlassCard.js`, `Skeleton.js`, and 4 rebuilt screens. Real glassmorphism (`expo-blur` `BlurView`), real gradients (`expo-linear-gradient`), real Reanimated transitions (`FadeInRight`/`FadeOutLeft`/`Layout`), a genuine custom typography pairing (Fraunces/Manrope, not system fonts), skeleton loading states, real empty/error states with on-brand copy.

Verified (since rendering isn't possible here): `npm install` resolves all packages (1153 total); every font family string checked against the installed package's actual exported names; every `LinearGradient`/`BlurView`/Reanimated import checked against the installed package's type declarations; all frontend files parse with a real Babel parser; every single design-token reference (`colors.x`, `typography.x`, `spacing.x`, `radii.x`) cross-checked against the actual token definitions — zero typos found.

**Not verified — cannot be, from here**: whether it actually renders correctly, whether the animations feel right, whether it works on iOS vs Android, whether the API calls succeed against a real deployed backend from an actual device.

**Explicitly missing against "Apple/Airbnb/Headspace" bar**:
- **Zero automated tests** — no Jest, no React Native Testing Library, no test script in `package.json`.
- **Zero accessibility props** — grep for `accessibilityLabel`/`accessibilityRole` across `frontend/src` returns nothing. Notable irony: the app collects tourists' accessibility needs via survey but the app's own UI has no screen-reader support.
- **No custom illustrations** — the design system is typography/color/motion/the Signal Ring; there is no illustrated artwork anywhere.
- **No offline handling, no push notifications, no real device testing.**
- Admin dashboard (`admin-dashboard/index.html`) is a separate, distinct design (harbor-instrument-panel) and has its own gap: **zero authentication** on a page that can trigger the ingestion pipeline and approve/reject community data.

---

## LAYER 2 AUDIT

**Status: The most mathematically rigorous layer, and the only one with an exact, provable blueprint match — but it operates on largely-default data because of the Layer 0 gaps above.**

- **Hard Filters** (`layer2/application/hard_filters.py`, `HardFilterService.evaluate()`): all 7 blueprint filters present — closed, budget, trip-duration, accessibility, freshness, return-visitor, unavailable. **But 5 of 7 are structurally inert for OSM-ingested data**, as a direct consequence of the Layer 0 gaps above:
  - "Closed places" — `_is_closed()` always returns `False`, since `opens_at`/`closes_at` are never parsed (see Layer 0 §10).
  - "Outside budget" — `estimated_cost` is always `0.0` for OSM places, so this can never exclude anything.
  - "Dwell time exceeds trip duration" — `dwell_time_typical_minutes` is always the default 45, rarely triggers.
  - "Return visitor exclusion" — `return_visitor_exclusions` is always empty (see Layer 1 above), so this can never trigger.
  - "Temporarily unavailable" — never set, always `False`.
  - Only **accessibility mismatch** and **freshness** are actually functional against real ingested data today.
- **Personal Fit Score** (`layer2/application/personal_fit_score.py`): the **top-level weighted-combination formula is exact and verified** against blueprint Table 10's three worked examples (`layer2/tests/test_personal_fit_score.py::test_formula_matches_table_10_*`, all passing). **Honesty point**: the blueprint specifies this combination formula exactly, but does **not** specify formulas for the five sub-scores (`companion_score`, `energy_score`, `curiosity_score`, `crowd_score`, `time_score`) beyond their qualitative meaning — those are my own reasonable implementation choices, not a verified blueprint match, because no exact blueprint formula exists for them to be checked against.
  - **Cascading gap**: because `energy_requirement`, `crowd_level`, and `best_time` are never populated per-place by Layer 0 (all constant defaults), **3 of the 5 sub-scores — accounting for 0.50 of the 1.0 weight — are effectively non-differentiating across all real ingested places.** Only `companion_score` (0.30, depends on category, which IS populated) and `curiosity_score` (0.20, depends on category/tags, shallow but populated) actually vary meaningfully today.
- **Slot Assembly** (`layer2/application/slot_assembly.py`): counts match Table 5 exactly (full-day 13, half-day 8 — the half-day figure is a documented, flagged deviation from Table 11's "7," since the two blueprint tables disagree with each other). **Real bug found**: `LOCAL_SECRET_MIN_LOCAL_PERCENTAGE = 0.9` (`slot_assembly.py:41`) is **stricter** than the community-submission default `local_percentage=0.85` (`layer0/api/routes.py`) — meaning even a genuine community-submitted hidden gem cannot currently qualify for the Local Secret slot it was specifically designed for. Also: `self._rng` (a `random.Random` instance) is constructed but **never used** anywhere in `assemble()` — dead code, the `random_seed` parameter has zero effect since selection is fully deterministic (sorted by `personal_fit`).
- **Weather adaptation** (`layer2/application/weather_scheduler.py`): real rain-hour swap logic, live-tested with synthetic forecasts. **Never tested against a real OpenWeatherMap response** — `OPENWEATHERMAP_API_KEY` is empty by default (`.env.example`), so `WeatherCollector.hourly_forecast()` always raises `SourceUnavailable` and weather scheduling is a permanent no-op unless a real key is configured.
- **Transport tagging** (`layer2/application/transport_tagger.py`): real haversine-based mode/cost thresholds. Auto fare calibrated against the real, cited Dakshina Kannada RTA tariff (₹35/1.5km + ₹20/km after) — verified with an exact-match test. Cab fare is a representative estimate, not sourced from an official tariff card — flagged as such in the code.
- **Recommendation Queue**: `HiveEngine.build_recommendation_queue()` — real, tested, includes a genuine two-pass budget enforcement (approximate pre-transport trim, then a strict post-transport pass) after a confirmed, fixed bug where budget was never actually enforced across a day (reproduced concretely: ₹500 budget → ₹1,556.75 day, before the fix).
- **Multi-day**: `HiveEngine.build_multi_day_recommendation_queue()` — real, tested, generates N independent day-queues excluding places used on earlier days. **Design choice, not a verified blueprint requirement**: each day gets the full stated budget independently (budget documented as "per day"), not a split total — the blueprint doesn't specify this explicitly.
- **Stale comment found**: `hive_engine.py`'s `BUDGET_TRANSPORT_HEADROOM` docstring says "10% is a reasonable buffer" but the constant is actually `0.20` — updated during the fix, comment never updated.

---

## INTEGRATION AUDIT

**The single most important finding of this audit**: Layer 2's mathematics are sound and well-tested, but **13 of Layer 0's Place fields are never populated for automatically-ingested data**, which cascades into **5 of 7 Hard Filters and 3 of 5 Personal Fit Score components being non-functional/non-differentiating** against real ingested data. The system is not "broken" — it's internally consistent and produces a correct answer given its inputs — but today's inputs are mostly defaults, not real signals. This is the actual gap between "the math is right" and "the product works," and it lives entirely in Layer 0's ETL, not in Layer 2's logic.

Can the frontend perform a complete flow? **Plumbing: yes.** `POST /survey/start` then `POST /survey/{id}/answer` x13 then `POST /survey/{id}/finalize` then `TouristProfile` saved then `POST /hive/recommendations` then `RecommendationQueue`. All 16 endpoints registered (confirmed via `main.app.openapi()` output showing all routes). **Live-verified for Layer 0/1 endpoints via curl in this session; the full survey→HIVE chain has been tested via direct Python calls with fakes and via live Postgres for individual pieces, but never as one single live HTTP request chain through the actual React Native app.**

---

## TESTING AUDIT

Real, measured (not estimated) via `pytest --cov`, run in this session:

```
TOTAL: 3248 statements, 1124 missed, 65% coverage
98 tests, 98 passed
```

- **0% coverage, every file**: `layer0/api/*`, `layer1/api/*`, `layer2/api/*` (routes, dependencies, schemas — all layers), `layer0/infrastructure/db/*`, `layer1/infrastructure/db/*`, all three `main.py` entrypoints.
- **93–100% coverage**: nearly all `application/` and `domain/` logic — bias audit, dedup, freshness, accessibility, curiosity extraction, survey state machine, hard filters, personal fit score, slot assembly, transport tagger, weather scheduler, HIVE engine.
- **What this precisely means**: the math and business logic are well-covered by automated, repeatable tests. The API layer and the database layer were verified **manually, live, once, by hand** (documented extensively in this conversation) — real evidence that the code works, but **zero regression protection** going forward. A future change could silently break `POST /admin/pipeline/run` or the Postgres mapping code and no test would catch it.
- **Frontend: zero tests of any kind.**
- No integration tests exercising the full HTTP stack (no `TestClient`/`httpx.AsyncClient` against the FastAPI app anywhere in the test suite).

---

## PERFORMANCE AUDIT

- **Database indexes**: real, live-verified — GiST spatial index on `location`, B-tree on `category` and `temporarily_unavailable`, unique constraint on `(name, category, location)`. Confirmed via `SELECT indexname, indexdef FROM pg_indexes` against live PostGIS in this session.
- **Batch inserts: none.** `EtlOrchestrator` Step 9 upserts one place at a time in a Python loop, each its own DB round trip and commit.
- **Concurrency: none in the ETL.** OSM collection is one request; Wikidata/Wikipedia enrichment and dedup lookups run **sequentially per place** — no `asyncio.gather`. For 1,000 places this is roughly 2,000+ sequential HTTP calls plus 1,000+ sequential DB round trips.
- **Caching: none.** No Redis caching of Place reads, no HTTP response caching for repeated Wikidata/Wikipedia lookups of the same entity.
- **Async: correct where it matters** — all DB and HTTP I/O uses async/await properly (SQLAlchemy async engine, `httpx.AsyncClient`, `asyncpg`), verified live.
- **Verdict on scale**: 100 places — probably fine, untested. 1,000+ — the sequential loops would make a full pipeline run slow (likely minutes, not verified), though nothing would technically crash. 10,000 — architecture would need batching/concurrency work first; not verified at all.

---

## SECURITY AUDIT

- **Authentication: none, anywhere.** Grepped the entire codebase for `OAuth2`, `HTTPBearer`, `JWT`, `verify_token`, `authenticate` — zero results. No auth-related package in `requirements.txt` (no `python-jose`, `passlib`, etc.).
- **Authorization: none.** `POST /admin/pipeline/run`, `POST /admin/submissions/{id}/approve`, `POST /admin/submissions/{id}/reject` — confirmed via `layer0/api/admin.py` — have **zero access control**. `reviewed_by` on the approve/reject endpoints is a free-text string the caller supplies themselves, not a verified identity.
- **CORS: wide open.** `main.py`, `allow_origins=["*"]`, with a comment acknowledging "tighten before production" that was never acted on.
- **Rate limiting (inbound): none.** No `slowapi`/`fastapi-limiter` in `requirements.txt` or the codebase. The rate-limit handling that exists (`ResilientHttpClient`) is for *outbound* calls to external APIs, not protecting Ground Zero's own API from abuse.
- **SQL injection: low risk.** All queries go through SQLAlchemy's ORM/Core with parameterized values; no raw string-interpolated SQL found anywhere.
- **Input validation**: Pydantic schemas provide type validation on every endpoint. No length limits on free-text fields (`curiosity_text`, `submitter_note`).
- **Secrets**: `.env`-based via `pydantic-settings` (reasonable pattern), but no secrets manager, and `.env.example` ships with empty API keys (correct — no real secrets are in the repo).
- **Admin dashboard**: `admin-dashboard/index.html` calls the same unauthenticated admin endpoints directly from a browser — no login screen, no token.

---

## MASTER TABLE

| Feature | Blueprint Requirement | Status | Impl. % | Evidence (file:function) | Missing Work | Priority |
|---|---|---|---|---|---|---|
| OSM ingestion | Fetch all discoverable POIs | Partial | 60% | `osm_collector.py:OsmCollector.collect` | Bbox tiling, batch insert, estimated_cost, opening_hours parsing | P0 |
| Wikidata enrichment | Auto-enrich POIs | Partial | 50% | `wikidata_collector.py:enrich` | Use heritage_status/image_url, or drop them | P2 |
| Wikipedia enrichment | Summaries, configurable language | Partial | 60% | `wikipedia_collector.py:summary` | Wire up settings.wikipedia_api_url or remove it; language config | P2 |
| Deduplication | Coordinate+name, category, merge | Implemented w/ gaps | 80% | `dedup.py:DedupService` | Cross-category dedup, external ID tracking | P2 |
| Bias Index | Formula per blueprint inputs | Partial | 40% | `bias_audit.py:BiasAuditService.compute` | Real media_mentions/local_percentage/commercial_flags/tourist_popularity sourcing | P0 |
| Accessibility detection | All accessibility fields | Partial | 40% | `accessibility.py:AccessibilityDetector.detect` | parking, washrooms, food_available, +5 more fields | P1 |
| Freshness scoring | Automatic | Implemented, not scheduled | 70% | `freshness.py:FreshnessService.score` | Actual scheduler (APScheduler/cron) | P1 |
| Master Data Core scale | Hundreds/thousands | Not demonstrated | 15% | live test: 8 rows | Real ETL run against live network, batching | P0 |
| Community submissions | Full workflow | Implemented, live-verified | 95% | `community_workflow.py` — live curl test | Fix resulting_place_id write | P2 |
| DB schema completeness | All blueprint fields | Implemented | 100% (schema) / 55% (populated) | `models.py:PlaceModel` | Populate 13 dead fields | P0 |
| Soul Survey flow | 9Q + additions | Implemented, tested | 95% | `survey_service.py:SurveyService` | — | — |
| Redis sessions | Persistent, multi-worker | Implemented, live-verified | 90% | `survey_session_store.py:RedisSurveySessionStore` | Fix broken fallback health-check | P1 |
| Return Visitor Check | Skip previously-visited | Mechanism only | 30% | `repository_impl.py:get_visited_place_ids` | visited_log write path + API endpoint | P1 |
| Curiosity extraction | "Most important input" | Simplified | 50% | `curiosity_extractor.py:CuriosityExtractor` | Expand lexicon or upgrade to embeddings/LLM | P2 |
| Hard Filters | 7 exclusion rules | Implemented, 5/7 inert on real data | 100% (logic) / 30% (effective) | `hard_filters.py:HardFilterService.evaluate` | Depends entirely on Layer 0 field population | P0 |
| Personal Fit Score | Exact weighted formula | Top-level formula exact & verified | 100% (top formula) / ~50% (effective) | `personal_fit_score.py` — Table 10 tests passing | Sub-score inputs need real per-place data | P0 |
| Slot Assembly | Table 5 counts | Implemented, tested | 95% | `slot_assembly.py` — full/half day tests passing | Fix Local Secret threshold vs. submission default | P1 |
| Weather adaptation | Rain rescheduling | Implemented, untested live | 80% | `weather_scheduler.py` | Real OpenWeatherMap key + live test | P2 |
| Transport tagging | Real fares | Implemented, calibrated to real RTA tariff | 90% | `transport_tagger.py` — exact-match tests | Cab fare is estimated, not sourced | P3 |
| Budget enforcement | (not explicit in blueprint, but required for a working system) | Implemented, bug found & fixed | 90% | `hive_engine.py:_enforce_budget_strict` | — | — |
| Multi-day trips | Q8 multi-day | Implemented (this session) | 85% | `hive_engine.py:build_multi_day_recommendation_queue` | Budget-split-vs-per-day is an inferred choice | P3 |
| Frontend visual design | Apple/Airbnb/Headspace tier | Designed, unverified on device | 60% | `frontend/src/screens/*`, `SignalRing.js` | Real device testing, illustrations, a11y props | P1 |
| Frontend tests | — | Missing entirely | 0% | — | Jest + RN Testing Library | P1 |
| API tests | — | Missing entirely | 0% | --cov shows 0% on all api/ files | TestClient-based route tests | P0 |
| Auth/Authorization | — | Missing entirely | 0% | grep: zero results | Real auth on /admin/* at minimum | P0 |
| Rate limiting (inbound) | — | Missing entirely | 0% | grep: zero results | slowapi or equivalent | P1 |

---

## COMPLETION PERCENTAGES

These are my own honest estimates, weighted toward "does this actually work end-to-end with real data" rather than "does the code exist" — stated as such, not measured by any tool, since no such tool can measure "blueprint compliance."

- **Layer 0: ~45%.** Architecture and community-submission path are solid and verified. Automated OSM/Wikidata/Wikipedia ingestion is real code, unverified against live data, and — even when it runs — populates fewer than half the required fields.
- **Layer 1: ~80%.** The most complete and best-tested layer. Two real bugs found and documented (Redis fallback, Return Visitor Check's missing write path) but the core survey flow is genuinely solid.
- **Layer 2: ~65%.** Mathematically the most rigorous and best-tested layer, with an exact, provable match to the one formula the blueprint fully specifies. Held back entirely by Layer 0's data gaps, not by its own logic.
- **Frontend: ~40%.** Real design work done this session, structurally sound, zero tests, unverified on any device.
- **Overall project: ~55%.**

---

## TOP 100 REMAINING TASKS (highest to lowest priority)

**P0 — blocks any real usage**
1. Compute real media_mentions for ingested places (some actual source: news/blog scan, review counts)
2. Compute real local_percentage for ingested places
3. Compute real commercial_flags for ingested places
4. Compute real tourist_popularity for ingested places
5. Populate real estimated_cost per place (not always 0.0)
6. Parse OSM opening_hours syntax into days_open/opens_at/closes_at
7. Populate energy_requirement per place (category-based classifier at minimum)
8. Populate crowd_level per place
9. Populate dwell_time_typical_minutes per category
10. Populate best_time per place
11. Add authentication to all /admin/* endpoints
12. Add authentication to the admin dashboard
13. Write visited_log somewhere (new endpoint: mark place as visited) so Return Visitor Check has real data
14. Fix resulting_place_id never being written on submission approval
15. Fix LOCAL_SECRET_MIN_LOCAL_PERCENTAGE (0.9) vs. community-submission default (0.85) mismatch
16. Fix the broken Redis fallback health-check in get_session_store()
17. Add API-level (TestClient) tests for every route, all 3 layers
18. Batch-insert places in the ETL instead of one-at-a-time upserts
19. Add asyncio.gather concurrency to Wikidata/Wikipedia enrichment loops
20. Run the actual ETL pipeline against live Overpass/Wikidata/Wikipedia from a real network and see what breaks
21. Tile/chunk the Overpass bbox query for a city-scale area
22. Populate temporarily_unavailable via some real signal (not always False)

**P1 — needed before calling this a real product**
23. Populate parking
24. Populate washrooms
25. Populate food_available
26. Populate pet_friendly
27. Populate family_friendly
28. Populate kid_friendly
29. Populate photography_allowed
30. Populate etiquette_tag
31. Populate transport_access
32. Populate season_suitability
33. Populate tide_dependency for coastal places
34. Set up a real scheduler (APScheduler/cron) for periodic ETL runs
35. Add rate limiting to Ground Zero's own inbound API
36. Tighten CORS from allow_origins=["*"]
37. Expand curiosity-extractor lexicon beyond 13 categories, or upgrade to embeddings/LLM
38. Add accessibility props (accessibilityLabel etc.) throughout the frontend
39. Set up Jest + React Native Testing Library, write frontend tests
40. Test the app on a real iOS/Android device or simulator
41. Add DB-layer automated tests (currently only manually/live-verified)
42. Get a real OpenWeatherMap API key and live-test weather scheduling
43. Get a real WorldTides API key and live-test tide integration
44. Reconcile the Table 5 vs. Table 11 half-day slot-count inconsistency with the blueprint owner
45. Fix the stale BUDGET_TRANSPORT_HEADROOM docstring (says 10%, is actually 20%)
46. Remove dead code: unused self._rng in SlotAssemblyService
47. Remove dead code: unused top_curiosity_categories in slot_assembly.py
48. Decide and document: multi-day budget — per-day or split-total? (currently an inferred default)
49. Add structured logging / observability (e.g. Sentry) — currently only Python's stdlib logging
50. Add input length limits on free-text fields (curiosity_text, submitter_note)
51. Investigate and fix image_url/heritage_status from Wikidata being fetched then discarded
52. Wire up or remove the unused settings.wikipedia_api_url config value
53. Add Wikipedia language configurability (Kannada/Konkani support, matching the survey's own language options)

**P2 — real, but lower urgency**
54. Cross-category duplicate detection (currently misses same-place-different-category dupes)
55. Durable external-ID tracking for OSM nodes (for future reconciliation)
56. Cache repeated Wikidata/Wikipedia lookups
57. Richer tag generation (NLP over wiki_summary/description) instead of category-name-only
58. Find and implement a real Karnataka Tourism ListingSource (architecturally ready, zero concrete sources registered)
59. Load-test the API before any real traffic
60. Database connection pool tuning for concurrent load
61. Add a secrets manager instead of plain .env for any real deployment
62. Add HTTPS/TLS termination config for deployment
63. Add backup/DR strategy for the Postgres instance
64. Horizontal scaling readiness review (Redis-backed sessions are already good for this)
65. Custom illustrations for the frontend (currently zero — design system is type/color/motion only)
66. Offline handling in the frontend
67. Push notification support (not built)
68. Group Session real-time sync (members joining is wired; live sync of what they see is Layer 4, out of current scope)
69. Admin dashboard: pagination for large place/submission lists (currently loads everything)
70. Admin dashboard: manual place editing (blueprint mentions "manual overrides," not built)
71. Add a proper migration for any schema changes made to fix the above
72. Verify the full survey→HIVE chain as one live HTTP request sequence through the actual mobile app (only tested in pieces)
73. Add monitoring/alerting for ETL run failures
74. Add a data quality dashboard section showing which fields are populated vs. default, per place
75. Decide whether price_band MODERATE/PREMIUM should ever be assigned, and how
76. Community submission form: collect local_percentage/media_mentions from the submitter instead of a hardcoded default
77. Add retry/backoff tuning based on real Overpass/Wikidata behavior once actually tested live
78. Sensory accessibility: expand beyond the single tactile_paving OSM tag
79. Add category coverage audit — confirm every OSM category maps to a Ground Zero category (some may fall through to "uncategorized")
80. Review whether PriceBand.FREE heuristic (park/garden/viewpoint/beach/heritage_site) is accurate enough or needs real cost data

**P3 — polish, not blocking**
81. Calibrate cab fare against a real official/representative source (currently an estimate)
82. Voice companion mode (explicitly Layer 3+, out of current scope, but worth noting as unbuilt)
83. Ask Engine / conversational layer (Layer 3, out of scope)
84. Session/Group Sync persistence beyond what's built (Layer 4, out of scope)
85. Admin dashboard visual polish pass (functional and designed, could go further)
86. Frontend micro-copy pass for every screen state (some empty/error states are minimal)
87. Add e2e tests (Detox or similar) for the mobile app
88. Performance profiling once real data volume exists
89. Add API versioning strategy before any public API commitment
90. Document the admin dashboard's own setup/deployment separately from the main backend
91. Add a changelog / migration guide for blueprint deviations (half-day slot count, Wikipedia language, etc.)
92. Review whether DataSource.KARNATAKA_TOURISM enum value (declared, unused) should be removed or kept for the future source
93. Add explicit test for the EtlRunReport.errors surfacing behavior end-to-end
94. Add health-check depth (currently /health just returns a static OK, doesn't check DB/Redis connectivity)
95. Consider adding osm_id as a real column for source-of-truth reconciliation
96. Review whether sponsored_indicator should ever be set automatically (currently only settable manually, never is)
97. Add explicit uniqueness/collision handling for group session codes at scale (currently a UUID, effectively collision-free, but worth a stated assumption)
98. Consider rate-limiting the /admin/pipeline/run endpoint specifically, since it triggers expensive external calls
99. Add a "last successful ETL run" indicator to the admin dashboard (currently only shows the most recent run's report, not history)
100. Full accessibility audit of the admin dashboard itself (currently no aria-* attributes either)

---

## FINAL ANSWERS

**1. Can this project now be considered production ready? NO.**
No authentication on admin endpoints, zero API-layer or DB-layer automated tests, an unverified-at-scale ETL pipeline, and roughly 45% of the Place schema's fields structurally unpopulated for real data. Any one of these alone would block a production ship; together they're decisive.

**2. Can this project now generate a COMPLETE Master Data Core for Mangaluru? NO.**
The pipeline has never been run against live Overpass/Wikidata/Wikipedia — this sandbox is network-blocked from all three, confirmed directly. Even if it ran, it would populate roughly half of each place's fields (see the field table above) and do so via sequential, unbatched I/O that's never been load-tested. "Complete" is not demonstrated at any scale beyond the 8 hand-entered test rows in this session.

**3. Can this project now replace the original seeded implementation? PARTIALLY, and only architecturally.**
The clean-architecture skeleton, the Personal Fit Score math, the Hard Filters, Slot Assembly, and the Soul Survey are all real, tested, and — where I could verify — correct. But swapping this in today would replace a small hand-seeded dataset with an equally small, equally hand-entered dataset, since the automated ingestion has never actually populated a real Master Data Core. The code is a genuine foundation to build the real replacement on top of, not a working replacement yet.

**4. Would I personally ship this to production? NO.**
Before I'd approve deployment, in order:
1. Authentication on every /admin/* endpoint and the admin dashboard — non-negotiable, this is a real open door today.
2. A live, successful ETL run against real Overpass/Wikidata/Wikipedia, with the field-population gaps in the master table above closed enough that Hard Filters and Personal Fit Score are actually differentiating between places, not comparing constants.
3. visited_log actually gets written somewhere, or Return Visitor Check gets removed from marketing claims until it does.
4. API-level and DB-level automated tests, so the parts currently protected only by "I tested it live by hand once" have real regression coverage.
5. Rate limiting and CORS tightened.
6. The system tested on an actual device, not just verified to parse correctly.

None of that is a rewrite — the architecture underneath is sound, and I'd estimate it's genuinely achievable — but it isn't done, and I'm not going to tell you it is.

---

## REMEDIATION PASS — What Was Actually Closed (post-audit)

Following this audit, a remediation pass addressed the findings. This
section is written the same way the audit itself was: every claim backed
by a file, a test, or a live command actually run. Tests went from **98
to 184** (86 new tests); measured coverage (`pytest --cov`) went from
**65% to 88%** overall, with the previously-0% API and DB-layer files
specifically improving (e.g. `layer0/api/security.py` 100%,
`layer0/api/routes.py` 0%→81%, `layer1/api/dependencies.py` 0%→100%,
`layer0/infrastructure/db/models.py` 0%→100%).

**Closed, with evidence:**

1. **`resulting_place_id` now actually gets written** on submission
   approval (`community_workflow.py:approve()` → `repository_impl.py:
   update_status()`), live-verified against real Postgres.
2. **Local Secret threshold mismatch fixed** — community submission
   default raised from 0.85 to 0.92 (`layer0/api/routes.py:
   COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE`), with a permanent
   regression guard test comparing both real constants directly.
3. **The Redis fallback bug is actually fixed**, not just described as
   fixed — replaced the try/except-around-a-lazy-client pattern with a
   real cached PING health check (`layer1/api/dependencies.py:
   _redis_is_reachable`), proven empirically both ways (a real Redis and
   a genuinely closed port).
4. **Dead code removed and made functional**: `SlotAssemblyService`'s
   unused `_rng` now actually breaks ties among equal-scored candidates;
   the unused `top_curiosity_categories` variable is gone; the stale
   "10%" docstring comment (constant was actually 20%) is fixed.
5. **13 previously-always-default Place fields are now genuinely
   populated** for OSM-ingested data: `energy_requirement`,
   `crowd_level`, `dwell_time_typical_minutes`, `best_time`,
   `season_suitability`, `tide_dependency`, `etiquette_tag`,
   `estimated_cost`, `price_band` (full range), `parking`, `washrooms`,
   `food_available`, `pet_friendly`, `family_friendly`, `kid_friendly`,
   `photography_allowed` — via a new `PlaceEnricher`
   (`layer0/application/place_enricher.py`, 20 tests), with every value
   either a real OSM tag or a documented, defensible category-level
   prior — and explicitly `None` (not guessed) wherever no real signal
   exists, per the "no fabricated data" instruction.
6. **Bias signals are no longer always-default.** A new
   `BiasSignalEstimator` (`layer0/application/bias_signal_estimator.py`,
   13 tests) computes real `commercial_flags` from OSM tags, a
   category-level `tourist_popularity` prior refined by a real
   Wikidata/Wikipedia-match signal, a documented `local_percentage`
   heuristic prior, and a `media_mentions` proxy from real Wikipedia
   summary length. Live-verified: five different fake places now
   produce five genuinely different bias_index values (0.06 to 0.34)
   instead of the previous identical 0.35 for every single place.
7. **A real OSM `opening_hours` parser exists** (`opening-hours-py`,
   `layer0/application/opening_hours_parser.py`, 13 tests) — two real
   bugs were caught and fixed during live testing: a 24/7 schedule
   initially produced nonsensical output (`days=['mon']` only), and the
   library rejected `datetime.timezone.utc` outright, requiring
   conversion to Mangaluru local time (which is also a correctness fix,
   not just compatibility — OSM hours are local time).
8. **Hard Filters' "closed places" check is now actually accurate** —
   previously it only ever compared time-of-day and **never checked
   day-of-week at all**, meaning a place closed every Sunday would
   incorrectly read as open on Sundays whenever the time-of-day matched.
   Now uses the real parser's `is_open_at()` against the raw OSM string
   directly. Regression-tested.
9. **The community ETL pipeline now runs concurrently** (capped
   `asyncio.gather`, `EtlOrchestrator.enrichment_concurrency`) instead
   of fully sequentially, and **stores places in one batch transaction**
   (`PostgresPlaceRepository.bulk_upsert`) instead of one commit per
   place.
10. **Overpass bbox tiling implemented** — large bounding boxes split
    into a grid of tiles (`split_bbox_into_tiles`), queried with bounded
    concurrency, deduplicated by `(osm_type, osm_id)` across tile
    boundaries, with graceful partial-failure handling. 10 new tests.
11. **Real authentication now exists on every `/admin/*` endpoint** —
    previously zero. API-key based (`X-Admin-Api-Key` header,
    constant-time comparison), fails closed if unconfigured. Live- and
    test-verified: 401 with no key, 403 with the wrong key, 200 with the
    right one, 500 if the server itself has no key configured.
12. **Real inbound rate limiting** (`slowapi`, configurable per-minute
    limit) — previously none; the app could not protect itself from
    abuse. Live-verified with real requests hitting a real 429.
13. **CORS actually tightened** — the app now refuses to start with
    wide-open CORS outside `environment=development`, rather than
    carrying a "tighten before production" comment that was never acted
    on.
14. **Return Visitor Check's missing write path is fixed** — added
    `TouristProfileRepository.mark_visited()` and a real endpoint
    (`POST /survey/profile/{id}/visited`). Live-verified against
    Postgres including correct deduplication across repeated calls.
15. **Real API-level test coverage added** where there was none — 14
    tests in `layer0/tests/test_api_endpoints.py` using
    `httpx.AsyncClient` + `ASGITransport` against the real app. Building
    these caught **two more real bugs**: `TestClient`'s thread-portal
    pattern doesn't work with this app's pooled async engine at all
    (switched to `ASGITransport`), and even that failed until
    `pytest-asyncio`'s test *and* fixture loop scopes were both set to
    `session` (two separate config keys, easy to only set one).

**Honestly not closed, and why:**

- **The ETL has still never run against live Overpass/Wikidata/
  Wikipedia.** This sandbox's network egress doesn't reach any of them
  (confirmed 403 on Overpass and Wikidata directly). All of the above
  ingestion-side fixes are real, tested code — verified with fakes and
  live Postgres — but "does a real multi-thousand-place Mangaluru run
  actually complete cleanly" remains unverified and can only be verified
  on real infrastructure with real network access.
- **`media_mentions` and `local_percentage` remain heuristic priors, not
  real behavioral data**, exactly as documented in
  `bias_signal_estimator.py`'s own docstring — no review/check-in/
  foot-traffic data source exists in this system's specified sources.
  This is disclosed, not hidden, but it is not the same as a real fix.
- **Scheduler for periodic ETL runs**: still doesn't exist. `/admin/
  pipeline/run` still requires a human or an external cron to trigger it.
- **Frontend accessibility props, frontend tests, device testing**: not
  addressed in this pass — this remediation focused on backend/API/
  security given the scope of findings there.
- **Karnataka Tourism real data source**: still zero concrete
  `ListingSource` implementations, as instructed in an earlier session
  (don't block on searching for one).
- Several P2/P3 items from the original audit's top-100 list (caching,
  connection-pool tuning, secrets manager, HTTPS/TLS config, load
  testing, cab-fare sourcing, admin dashboard manual place editing, and
  others) were not addressed in this pass — genuinely lower priority
  than what's listed above, and not claimed as done.

**Revised honest completion estimate**: Layer 0 ~60% (up from ~45%,
still gated on a live ingestion run), Layer 1 ~85% (up from ~80%), Layer
2 ~75% (up from ~65%, Hard Filters are now meaningfully more functional
against real data), security/API surface substantially improved from a
near-zero starting point. Overall project: **~65%**, up from ~55%.
Would I ship it now? Closer, but still no — the live ETL run and a
scheduler are the two biggest remaining gates, and both need real
infrastructure this sandbox cannot provide.

