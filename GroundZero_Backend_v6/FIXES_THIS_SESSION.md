# Fixes — this session (Aug 25, 2026)

Carol reported: Layer 0 not collecting/forwarding data, recommendations
not happening, personalized tour planning not working. Investigated by
actually running the stack (real Postgres 16 + PostGIS, real Redis, real
FastAPI server, real HTTP calls) rather than trusting bundled docs.

## Headline finding

The bundled `README.md` and `audit/AUDIT_REPORT.md` are **stale** —
written against an earlier version of this code. Nearly everything they
flag as "missing" (bias signal estimation from OSM tags, opening-hours
parsing, bulk insert, enrichment concurrency, the Redis fallback bug,
`resulting_place_id` write, `visited_log` write, rate limiting, CORS
lockdown, the Local Secret threshold mismatch) is **already implemented**
in the code as shipped. Don't trust these two docs for current status —
they need a rewrite, not this codebase.

## Bug #1 — the real blocker (fixed)

**Symptom this explains**: pipeline appears to work once, then silently
stops doing anything useful; recommendations don't reflect real data;
Layer 0 looks "dead" even with a database and API keys configured.

**Root cause**: `layer0/infrastructure/db/models.py`, `PlaceModel`. The
`updated_at` column uses a server-side `onupdate=func.now()`. Whenever
`bulk_upsert()` **updates a place that already exists** (which is every
single ETL run after the first one, and any re-scoring pass), SQLAlchemy
tries to lazily re-fetch that server-generated value from Postgres —
inside an async session, with no event loop available to await it — and
crashes with `sqlalchemy.exc.MissingGreenlet`.

Reproduced live: inserting brand-new places worked; re-upserting those
same places (the normal, everyday path) crashed every time until fixed.

**Fix**: added `__mapper_args__ = {"eager_defaults": True}` to
`PlaceModel`, so SQLAlchemy fetches server-generated columns via
`RETURNING` as part of the same flush instead of a follow-up round trip.
Verified: re-upsert of 26 already-stored places (mix of new/existing)
succeeded cleanly after the fix, computed real differentiated
`bias_index` values, no crash.

## Bug #2 — test suite couldn't run at all (fixed)

`layer0/domain/repositories.py`'s `PlaceRepository` interface gained a
`record_visit()` abstract method (added to support the Return Visitor
Check), but the `FakePlaceRepository` test doubles in 5 test files were
never updated to implement it — so those tests couldn't even instantiate,
raising `TypeError` at collection time. This alone caused **35 of 220
tests to fail** on a cold run, which would make the whole backend look
broken even though the logic underneath was fine.

**Fix**: added a no-op `record_visit()` to all 5 `FakePlaceRepository`
classes:
- `layer0/tests/test_etl_local_listings_seam.py`
- `layer0/tests/test_community_workflow.py`
- `layer2/tests/test_hive_engine.py`
- `layer2/tests/test_multi_day.py`
- `layer2/tests/test_budget_enforcement.py`

## Verification performed (not just claimed)

- Installed real PostgreSQL 16 + PostGIS 3.4 and real Redis in a clean
  environment, ran `alembic upgrade head` cleanly against them.
- **220/220 tests passing, 88% coverage**, against the live database —
  not sqlite, not mocks.
- Booted the actual `uvicorn main:app` server and ran a **complete live
  HTTP flow**: `POST /survey/start` → 13× `POST /survey/{id}/answer`
  (Asha's exact blueprint answers) → `POST /survey/{id}/finalize` → real
  `TouristProfile` with correctly extracted `curiosity_vector` → `POST
  /hive/recommendations` against 5 real hand-seeded Mangaluru places
  (Milagres Church, Mrs. Lobo's Home Kitchen, Kadri Manjunath Temple,
  Panambur Beach, Summer Sands Resort) plus leftover test data.
- **The bias-correction philosophy visibly worked**: Milagres Church
  (bias_index 0.004, low hype) and Kadri Manjunath Temple (0.010) were
  selected with `personal_fit` scores of 0.86 and 0.85; Summer Sands
  Resort (bias_index 0.23, 500 media mentions, 5% local) was **never
  selected** for any slot. This is Table 10's worked example, live,
  end-to-end, over real HTTP.
- Confirmed `POST /survey/profile/{id}/visited` genuinely writes to
  `TouristProfile.visited_log` (the real Return Visitor Check write
  path — this lives in Layer 1, not the vestigial `record_visit` stub
  on the Layer 0 place repository, which only validates a place exists
  and is otherwise a no-op; harmless, not a functional gap).

## What is NOT fixed, and can't be from a sandboxed session

- **`OPENWEATHERMAP_API_KEY` and `TIDE_API_KEY` are blank in `.env`.**
  Weather-adaptive scheduling and tide checks fail-closed (correctly, by
  design — no fake data) until you fill these in with real free-tier
  keys from openweathermap.org and worldtides.info.
- **The live ETL against OSM/Wikidata/Wikipedia/OpenWeatherMap has never
  run successfully from any sandboxed environment** — this one included.
  My network egress here doesn't reach `overpass-api.de`,
  `query.wikidata.org`, or `openweathermap.org`, matching exactly what
  your own audit already found. This has to run from your machine or a
  real server with open internet access:
  `docker compose up -d` → fill in `.env` → `alembic upgrade head` →
  `uvicorn main:app` → `curl -X POST http://localhost:8000/admin/pipeline/run`
  (send the `X-Admin-Api-Key` header — see `.env`'s `ADMIN_API_KEY`).
- **Karnataka Tourism / local listings source** is still an unfilled
  plug-in seam (`layer0/infrastructure/collectors/local_listings_collector.py`)
  — no concrete source registered. Not touched this session.
- Frontend (Expo/React Native) was not touched or re-verified this
  session — out of scope for this bug report.

---

# Session 2 (same day) — Tourist-Added Place feature + full re-verification

Carol asked for: since automated data collection can't reach every real
local place yet, let a tourist add a place they already have in mind —
either found via a map/search, or typed in fresh if it's genuinely not in
the system — and guarantee two things: (1) it actually ends up in their
itinerary, and (2) if it wasn't already in the Master Data Core, it gets
added automatically, from the tourist's own info, so future tourists
benefit too. Then: re-verify everything from Layer 0 to the end, one more
time, and fix anything still inactive.

## New feature: Tourist-Added Places

**New service**: `layer0/application/custom_place_service.py` —
`CustomPlaceService`. Two operations:

- `search_nearby(lat, lon, radius_meters)` — powers "search the map":
  shows what's already known near a dropped pin, closest first.
  **Deliberately ignores category** when matching (unlike the existing
  `find_duplicates`, which requires an exact category match — a real gap
  the original audit flagged, since a tourist has no idea the internal
  taxonomy calls a place `heritage_site` instead of `church`).
- `add_or_find(name, lat, lon, category, note, estimated_cost)` — the
  core operation. Runs the same geo+name dedup match against everything
  nearby; if it's a genuine match, **reuses the existing place**
  (`was_newly_created: false`). If not, **creates it immediately** —
  `source=[DataSource.TOURIST_ADDED]`, self-reported bias signals
  (`local_percentage=0.80`, `media_mentions=0` — same self-reported
  convention as Community Submissions), real `bias_index`/`grade`
  computed through the normal Bias Audit pipeline, and the tourist's own
  `note` stored as the place's description. **No admin approval gate** —
  unlike Community Submissions, this is the tourist's own real-time
  itinerary need, not a public claim awaiting moderation.

**New API** (`layer0/api/routes.py`):
- `GET /places/nearby?latitude=&longitude=&radius_meters=` — search
- `POST /places/custom` — add-or-find, returns the resulting place +
  `was_newly_created`

**HIVE integration** (`layer2/application/hive_engine.py`): both
`POST /hive/recommendations` and `/hive/recommendations/multi-day` now
accept `pinned_place_ids: [str]`. Any place ID passed there:
- Is pulled out of the ordinary candidate pool before Hard Filters run,
  so it's **never silently dropped** for being closed, over budget,
  failing an accessibility check, or simply scoring lower than
  something else — the tourist chose it, not HIVE.
- Gets a new dedicated role, `SlotRole.TOURIST_PICK`, added alongside
  Grounding/Signature/Anchor/Personal/Local Secret/Wildcard, and is
  added to the same budget-protected set as those backbone roles — the
  Wallet Tracker's trimming pass will drop ordinary Personal slots to
  make room for it, never the pinned place itself.
- Still goes through real scheduling (time-ordered placement, weather
  pre-shift, transport tagging to/from its neighbors) exactly like every
  other slot — "added" means "you'll actually be taken there," not
  "noted somewhere and maybe shown."
- On a multi-day trip, pinned places apply to Day 1 only (a specific
  place picked once, not one to repeat daily) and are automatically
  excluded from later days via the existing return-visitor-exclusion
  mechanism.

**Tests added** (9 new, all passing):
- `layer0/tests/test_custom_place_service.py` (5): creates a genuinely
  new place with correct bias computation; reuses an existing place on a
  fuzzy name + close-but-not-exact coordinates match even with a
  completely different guessed category; correctly does NOT merge a
  different place that happens to be nearby; `search_nearby` sorts
  closest-first and excludes out-of-radius places; rejects a blank name.
- `layer2/tests/test_hive_engine.py` (4 new): a pinned place is included
  even when `temporarily_unavailable` (would normally fail Hard
  Filters); a pinned place survives budget enforcement even when priced
  at ₹100,000 with a ₹500 budget; a pinned place is never *also* picked
  as an ordinary slot; passing no `pinned_place_ids` behaves identically
  to before this feature existed (no regression).

## Full Layer 0 → Layer 2 re-verification (this session)

Ran the complete stack again from scratch after all changes:
- **229/229 tests passing**, live PostgreSQL 16 + PostGIS + Redis (not
  mocks) — 220 pre-existing + 9 new.
- Booted the real server, ran `GET /places/nearby` and `POST
  /places/custom` live: correctly reused an existing seeded place on a
  fuzzy match, correctly created "Aunty Priya's Neer Dosa Corner" as a
  brand-new place with real computed `bias_index: 0.07` / `grade:
  "authentic"`.
- Pinned that new place into a **live** `POST /hive/recommendations`
  call for Asha's profile: it appeared as the final slot, role
  `tourist_pick`, correctly transport-tagged (cab, 30 min, ₹275.05),
  correctly included in `total_estimated_cost`, with the honest reason
  text "You added this place yourself — it's included no matter what
  HIVE would have scored it."
- Spot-checked the unrelated Community Submission flow (`POST
  /places/submissions`) still works — confirming this session's changes
  didn't disturb it.

**Everything checked out working. Nothing found inactive this pass**
beyond the items already listed above under "What is NOT fixed" (blank
weather/tide API keys, live ETL requiring real internet access, the
unfilled local-listings seam, and the frontend, none of which changed
this session).

