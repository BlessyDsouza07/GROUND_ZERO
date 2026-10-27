# Integration notes — Layer 3, Live Mangaluru Events, and the frontend Companion

This document explains exactly what was added to the original Layers 0–2
backend + frontend skeleton, why each change was necessary, and how to run
and verify the whole thing. Read this before `README.md`'s older
Layer-0–2-only status section.

## 1. What's in this build

- **Layers 0, 1, 2** — unchanged from the original backend (places/ETL,
  Soul Survey, HIVE recommendation engine).
- **Layer 5** — was already present in the code but **had no router wired
  into `main.py`**, so none of it (chatbot, geofencing, multilingual,
  voice guide) was ever reachable over HTTP. Fixed — see `main.py`.
- **Layer 3** (`layer3/`) — Context Engine, Silence Filter, and Ask Engine.
  Added in full, unmodified internally, and mounted into the combined app.
- **Live Mangaluru Events** (`live_events/`) — a real events-verification
  microservice (JSON-LD/microdata scraping, robots.txt-respecting fetcher,
  human-vetted source allowlist). Added in full and mounted into the
  combined app, and connected to feed Layer 3's `nearby_events` signal.
- **Frontend** — a new Companion screen (`frontend/src/screens/companion/
  CompanionScreen.js`) wired in after HIVE results, plus its API client
  (`frontend/src/api/client_layer3.js`).

Run it all with **one command**: `uvicorn main:app --reload` (backend) +
`npm start` (frontend, from `frontend/`) — no separate processes needed.

## 2. Real data only — no seed/sample data drives the running app

This was a deliberate, explicit requirement and is worth stating clearly:

- **Places**: Layer 3 reads the flattened copy of `data/master_data_core.json`
  (the real, Layer-0-collected 708-place dataset) that
  `scripts/export_layer3_master_core.py` produces at
  `layer0/data_output/master_data_core.json` on every boot. Layer 3's own
  bundled `layer3/sample_data/*.sample.json` files are never referenced by
  the running app — they exist only for Layer 3's own standalone demo mode
  (`python run_layer3.py --demo`), which this integration doesn't use.
- **Events**: the Live Events module's `data/verified_seed.json` used to be
  loaded two ways — as `Source` rows (which websites to monitor) *and* as
  static, pre-verified `Event` rows inserted directly into the database.
  **The static Event-row seeding was removed from the automatic startup
  path** (`live_events/app/seed.py` / `live_events/app/main.py`). Only the
  `Source` rows are still seeded automatically — that's bootstrap
  *configuration* (which real websites the live scraper is allowed to
  fetch from), not fabricated content. Every event the running app returns
  now comes from an actual fetch → parse → verify pass over those sources,
  triggered immediately at startup (not just on the first 6-hour interval)
  via APScheduler's `next_run_time`. Until that first real scrape succeeds,
  the events endpoints correctly and honestly return `[]` — this is
  expected behavior, not a bug (see `live_events/docs/DATA_POLICY.md`'s own
  "never fabricate" policy, which this change actually upholds more
  strictly than the code as originally delivered).
  - The old seed-events behavior is still available, explicitly, for an
    offline demo with no network access — see the docstring on
    `seed_verified_events_demo()` in `live_events/app/seed.py` — but the
    app never calls it on its own.

## 3. The real bugs/gaps found and fixed

Nothing below was cosmetic — each was found by actually reading the code
paths involved (and, where the sandbox allowed it, by actually running the
real logic against the real 708-place dataset — see §5).

1. **Layer 0's export shape vs. what Layer 3 reads.** Layer 0's
   `data/master_data_core.json` nests coordinates
   (`coordinates.latitude/longitude`), bias signals (`bias_signals.
   local_percentage`/`media_mentions`), and accessibility tags
   (`accessibility.tags`) one level deeper than Layer 3's own field-reading
   helpers (`layer3/layer3_utils.py`'s `pget`/`place_latlng`) look for.
   Verified concretely: **before** the fix, `place_latlng()` resolved 0 of
   708 places; **after**, 708/708. Fixed with a non-destructive adapter
   (`scripts/export_layer3_master_core.py`) — Layer 0's real export is
   never modified, and neither is Layer 3's code. Also maps Layer 0's
   category vocabulary (`heritage_site`, `street_food`, ...) to Layer 3's
   coarser purpose buckets (`SPIRITUAL`, `FOOD`, ...) so its
   time-of-day/outdoor-weather signal is meaningful rather than always
   falling back to `DEFAULT`.
2. **Layer 3's unfed `nearby_events` signal.** `layer3/layer3_sources.py`
   already had code to read a `live_events_cache.json` file — it just
   never existed (Layer 0's own event pipeline left `data/events_cache.json`
   empty). `scripts/export_layer3_events_cache.py` now feeds it from the
   Live Events module's real, verified database.
3. **A real settings collision.** The Live Events module's config read a
   bare `DATABASE_URL`/`ADMIN_API_KEY` from a cwd-relative `.env`. Mounted
   inside the combined app (same cwd, same root `.env`, which already
   defines `DATABASE_URL` for the main Postgres/asyncpg connection), it
   would have silently picked up that Postgres async URL and handed it to
   its own *synchronous* SQLAlchemy engine — a hard crash on first request,
   not a subtle bug. Fixed in `live_events/app/config.py`: env vars are now
   namespaced (`EVENTS_` prefix) and its `.env` is anchored to its own
   directory rather than resolved relative to the process's cwd.
4. **Dependency version conflicts.** The Live Events module needs
   `pydantic-settings>=2.7`, `httpx>=0.28`, `uvicorn>=0.34`; the main app
   was pinned to older versions of all three. Bumped in `requirements.txt`
   (each bump audited against this repo's actual usage first — no
   `proxies=`/`app=` httpx patterns anywhere, `shared/config.py` uses only
   basic `BaseSettings`/`Field`). Also added the 3 packages Live Events
   needs that weren't present at all: `apscheduler`, `beautifulsoup4`,
   `python-dateutil`.
5. **`/hive/generate` didn't exist.** Layer 3's own bridge code
   (`layer3/layer3_bridge.py`'s `Layer2Client`) calls
   `POST /hive/generate` with `{"profile_id": ...}` when starting a session
   from a profile_id alone. Layer 2's real, tested endpoint is
   `POST /hive/recommendations`, built independently before Layer 3
   existed. Added a small, purely additive compatibility route
   (`integration/layer2_layer3_bridge.py`) that reuses Layer 2's actual
   `HiveEngine`/`ProfileRepository` — zero duplicated logic, zero changes
   to `layer2/api/routes.py`. In the shipped app's normal flow this path
   isn't actually exercised — the frontend already has the itinerary by
   the time it starts a Companion session and passes it straight through
   (see below) — but it's there for API completeness (e.g. calling Layer 3
   directly via `/docs`, or a future Layer 4).
6. **Starlette doesn't auto-run a mounted sub-app's lifespan.** The Live
   Events module needs its own startup (DB init, source seeding, scheduler
   start) and shutdown (scheduler stop). `app.mount("/events-live", ...)`
   alone would never trigger any of that. `main.py`'s own `lifespan` now
   explicitly drives the Events module's original, unmodified `lifespan()`
   context manager.
7. **Layer 3/Layer 1/Layer 2 port mismatch.** Layer 3's own defaults
   (`LAYER1_BASE_URL`/`LAYER2_BASE_URL`) point at a fully-separated
   microservices topology (ports 8002/8003) that doesn't exist here — all
   of Layers 0/1/2/5 run on one app, one port. `main.py` points them at
   this same app (`GROUNDZERO_BASE_URL`, default `http://localhost:8000`)
   before Layer 3's settings are ever constructed.
8. **`LayerError` had no exception handler on the combined app.** Mounting
   `layer3_router` directly (rather than using Layer 3's own
   `create_app()`) skips the handler that turns a `LayerError` into the
   documented `{"error": {"code", "message"}}` JSON shape. Registered
   explicitly in `main.py` so `/l3/*` errors look the same whether Layer 3
   runs standalone or mounted here.
9. **Two secrets-hygiene issues in the root `.env`/`.env.example`** (found
   on request, audited across every `.env*` file plus a full-repo scan for
   hardcoded key-shaped strings):
   - `.env.example` — the template file meant to be safe to share/commit —
     contained the **same real-looking `OPENWEATHERMAP_API_KEY` and
     `TIDE_API_KEY` values** as the actual working `.env`. Replaced with
     plain placeholders (`your_openweathermap_api_key_here`, matching the
     safe pattern `layer3/.env.example` already used for its own
     `GROQ_API_KEY`). `.env` itself (the private, working dev config) was
     left untouched.
   - `.env.example`'s `ADMIN_API_KEY` was set to the weak, guessable
     `123456` — directly contradicting the comment two lines above it
     ("Left empty, every admin request is REJECTED (fails closed, not
     open)"). Changed to empty, matching the documented fail-closed
     default.
   - There was **no root-level `.gitignore` at all** (only
     `layer3/.gitignore`), so `.env`, `live_events/.env`, `frontend/.env`
     and every `__pycache__`/`.pyc`/sqlite-db build artifact had no
     protection from being committed if this project is ever put under
     git. Added one.
   - Format-checked (not liveness-checked — no network access here) the
     real `.env`'s `OPENWEATHERMAP_API_KEY` (32-char hex — matches
     OpenWeatherMap's format), `TIDE_API_KEY` (UUID — matches
     WorldTides.info's format), and `ADMIN_API_KEY` (44-char urlsafe —
     matches `secrets.token_urlsafe(32)`, exactly what the file's own
     comment instructs generating it with). All three are properly
     formed; whether they're still *active* keys is something only you
     can check (e.g. a quick real request to OpenWeatherMap with that
     key). `live_events/.env`'s `EVENTS_ADMIN_API_KEY` is intentionally the
     literal placeholder `change-this-local-key` in both `.env` and
     `.env.example` — it's clearly not a real secret, but change it before
     any non-local deployment.
10. **A real Layer 2 bug, found while debugging "nothing fit today" for
    every survey answer** (unrelated to Layer 3/Events — pre-existing in
    the Layers 0–2 backend, found and fixed on request). `POST
    /hive/recommendations`'s `start_latitude`/`start_longitude` geofence
    (`layer2/application/reachability.py`) had no fallback: if the given
    coordinates fell within nothing even at its widest allowed radius
    (30km), it returned an empty candidate pool — before budget, timing,
    or any other filter ever ran. Trivial to trigger by accident: an iOS
    Simulator's default location (Apple Park, Cupertino), an Android
    emulator's default/`(0,0)` fix, or a stale cell-tower GPS fix are all
    thousands of km from every place in this Mangaluru dataset. Fixed:
    when the widest radius finds nothing, `reachability.py` now falls
    back to the full candidate pool instead of returning empty, and
    reports `geofence_radius_km: null` in that case (honestly signaling
    "no effective geofence was applied" rather than silently claiming a
    working 30km filter). Added 2 regression tests
    (`layer2/tests/test_hive_engine.py`). Also gave
    `HiveResultsScreen.js`'s empty-state a second, more specific diagnosis
    (an extra `GET /places` call, only when the queue comes back empty) to
    distinguish "the places table has zero rows" (run
    `python import_master_data.py`) from "places exist but this profile's
    budget/timing genuinely excluded all of them" — see README.md's
    updated Layer 2 section for the full writeup.
11. **`confirmDay()` could permanently block ever reaching Layer 3 on a
    connectivity hiccup.** `HiveResultsScreen`'s "Confirm my day" required
    two backend calls (`POST /hive/itinerary/{id}/save`, then `.../confirm`)
    to both succeed before revealing "Begin your trip" — so any network
    problem (backend not running, wrong `EXPO_PUBLIC_API_BASE_URL`, a
    transient hiccup) didn't just fail to save; it made Layer 3
    unreachable, with no way to retry except hoping the network fixed
    itself. Both routes were checked and are correctly registered/wired —
    this was a frontend resilience gap, not a missing/broken route. Fixed:
    a failed save/confirm now shows the error **plus the exact backend URL
    it tried** (`client.js`'s exported `BASE_URL`) **plus a "Continue
    without saving →" button** that proceeds locally — since the itinerary
    data Layer 3 needs already exists client-side in `items`, nothing
    about starting a Companion session actually depends on the server-side
    `ConfirmedItinerary` row existing. Only the *saved copy on the server*
    is affected by a failed save, never the tourist's ability to start
    their trip.
    - **"Failed to fetch" specifically** is the browser's own message for
      a request that never got any HTTP response at all (not a 404/500 —
      those throw a different, `API <status>: ...`-prefixed error from
      `client.js`'s `request()`). The most common cause in this codebase,
      already flagged in `client.js`'s own original header comment: on
      Expo web or iOS Simulator, `http://localhost:8000` (the shipped
      default) reaches the dev machine fine; on a **physical phone via
      Expo Go, or most Android emulators, `localhost` means the
      phone/emulator itself** — nothing is listening on its own port 8000,
      so every call fails exactly this way. `frontend/.env`'s comment was
      rewritten to spell out the fix (find your computer's LAN IP, set
      `EXPO_PUBLIC_API_BASE_URL` to it, fully restart `npx expo start` —
      env vars are read once at bundle time). If you're already on
      web/Simulator and still see this, it means the backend genuinely
      isn't reachable at that address right now — check it's running
      (`uvicorn main:app --reload`) and check `/health`.
    - This also directly answers "why didn't Layer 3 run after Confirm":
      it's not that Layer 3 needs anything else built (there is no Layer 4
      in this codebase, and Layer 5 is already wired in — see its
      section). Layer 3 is one tap away, behind "Begin your trip," which
      only appeared after the save+confirm calls succeeded. With this fix
      it now appears either way.
    - **Layer 3 itself does not require being physically in Mangaluru.**
      `POST /l3/ask`, `/l3/quiet`, `/l3/sos` all work with no location at
      all (checked against Layer 3's actual Pydantic schemas — `lat`/`lng`
      are `Optional` on all of them). `POST /l3/location/ping` requires
      real coordinates (its schema has them as required, not Optional),
      so `CompanionScreen.js` only calls it when a location was actually
      obtained — never with a wrong/missing one. A wrong or absent
      location just means arrival-based nudges won't fire (Layer 3 has no
      equivalent of the Layer 2 geofence bug above — a mismatched location
      degrades to "nothing to report," never to an error or a dead end).
      The Companion screen's header now says this directly.

Every one of the above was found by reading the actual code on both sides
of the seam — not assumed — and every fix is additive/non-destructive to
the original layers' own logic and tests.

## 4. How the frontend actually uses this

`HiveResultsScreen`'s confirmed-day screen now has a **"Begin your trip"**
button (only shown when a `onBeginTrip` callback is supplied — additive,
doesn't change the screen for any other caller). `AppNavigator.js` wires
that callback to store the confirmed itinerary and navigate to the new
**Companion** screen, which:
- Starts a Layer 3 session with that exact itinerary (`POST /l3/session/
  start`) — no separate Layer 2 round-trip needed, sidestepping the
  `/hive/generate` seam entirely in the app's real flow.
- Runs the same "every ~30–60s or on GPS update" check-in loop
  `layer3/README.md` describes, via `POST /l3/location/ping` +
  `POST /l3/context/evaluate`, plus an instant **"I'm here"** manual
  trigger.
- Shows the one-sentence companion message + etiquette whisper when
  Layer 3 decides to speak, with **"Tell me more"**.
- A grounded **Ask Engine** box (`POST /l3/ask`).
- **Quiet Hours** and **SOS** controls (`POST /l3/quiet`, `POST /l3/sos`,
  with a confirm step before sending).
- **"I've arrived"** per stop (`POST /l3/visit`).
- A **"Happening nearby, verified"** section from the Live Events module
  (`GET /events-live/events/itinerary-safe`) — only rendered when
  non-empty, matching the app's "silence by default" philosophy and the
  events module's "never show unverified/fabricated events" policy.

Every field name used in `CompanionScreen.js` was checked against Layer
3's actual orchestrator/route code (`layer3/layer3_orchestrator.py`,
`layer3/layer3_api.py`), not guessed — see e.g. the exact `decision`/
`message`/`notification_id` shape `POST /l3/context/evaluate` returns.

## 5. What was actually verified, and how (given this sandbox has no
   network and cannot `pip install`)

- **Every one of the ~200 Python files in the combined project compiles**
  (`python3 -m py_compile`), including every new and every edited file.
- **The Layer-0→Layer-3 data adapter was run for real** against the actual
  708-place `data/master_data_core.json`, and its output was fed through
  Layer 3's *actual* parsing code (`layer3_utils.place_latlng`,
  `parse_opening_hours`, `place_category`, `normalize_crowd_level`,
  `normalize_energy` — all pure-stdlib, importable without FastAPI/
  SQLAlchemy) — not simulated. Confirmed: 708/708 places resolve lat/lng
  (0/708 before the fix), 51 places have parsable opening hours, and the
  category mapping produces sane bucket counts.
- **The events-cache adapter's row shape was verified** by running Layer
  3's real `pget`/`parse_dt`/keyword-matching code against a row built
  exactly the way `export_layer3_events_cache.py` builds it.
- **The whole frontend `src/` tree was checked for balanced brackets/
  braces/parens** (a from-scratch checker, since no npm packages —
  including the project's own `@babel/parser` devDependency — could be
  installed here). Clean, including the pre-existing files, confirming the
  checker itself is sound.
- **What could not be verified here**: an actual `pip install -r
  requirements.txt` + `uvicorn main:app --reload` boot (no network in this
  sandbox to install FastAPI/SQLAlchemy/etc. at all), the real Postgres
  connection, an actual live scrape of the Events module's seeded source,
  and `npm install` + Expo/Metro bundling of the frontend. These need your
  machine. See §6 for exactly what to run.

## 6. Setup / run / verify, in your own environment

```bash
# Backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp .env.example .env        # already includes GROUNDZERO_BASE_URL / GROQ_API_KEY (optional) additions
cp live_events/.env.example live_events/.env   # optional — has working defaults either way
docker compose up -d        # Postgres + PostGIS, Redis — see README.md's original Setup section
alembic upgrade head
python import_master_data.py   # loads data/master_data_core.json into Postgres, if not already done
pytest -v                      # Layers 0/1/2/5's own test suite
cd live_events && pytest -v && cd ..   # Live Events module's own test suite (parser + dedupe)
uvicorn main:app --reload
# -> http://localhost:8000/docs — look for /l3/* and /events-live/* alongside the original routes
# -> http://localhost:8000/health should report layer3_available: true, live_events_available: true

# Frontend
cd frontend
npm install
npm start   # Expo — see App.js/README for device/simulator instructions
```

A quick manual smoke test once the backend is up:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/events-live/health
curl -X POST http://localhost:8000/admin/pipeline/run   # if you haven't imported real place data yet
curl -X POST http://localhost:8000/l3/session/start \
  -H "Content-Type: application/json" \
  -d '{"profile_id": "<a real profile id from your Postgres tourist_profiles table>"}'
```

If Layer 3 or Live Events fail to import for any reason, `/health` will
say so explicitly (`layer3_available`/`live_events_available: false`) and
the rest of the app (Layers 0/1/2/5) still runs — check the server logs
for the exception `main.py` logs, rather than the app failing to start
entirely.
