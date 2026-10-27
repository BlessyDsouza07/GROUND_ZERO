# Session 2026-09-24 — Live Events swap, Transport-Mode fix, Dataset pass

Three things were asked for: (1) remove the seeded demo events and wire in
the real "no-seed" live events module, (2) fix wrong-looking transport
mode recommendations, (3) find and add real places still sitting in the
geocoding queue. Here's exactly what happened on each, including the
parts that did **not** get done, on purpose.

---

## 1. Live Mangaluru Events — seeded demo replaced with the real module

`live_events/` (previously: `data/verified_seed.json` + a
`seed_verified_events_demo()` loader that fabricated 3 demo events at
startup) is now the "FINAL_LIVE_NO_SEED" build you supplied: real adapter
(`StAloysiusAdapter`, JSON-LD-first with an HTML fallback), a
robots.txt-respecting fetcher (`robots.py`), and a `collector.py` that
runs the adapters on a schedule. `app/seed.py` is now a documented no-op —
confirmed by its own `tests/test_no_seed.py` (both tests pass): no
`verified_seed.json` file, and nothing in `data/sources.json` claims to
be an "events" source without a real adapter behind it.

**Bug found and fixed in the new zip before wiring it in:** its
`config.py` read a bare `DATABASE_URL` env var via `load_dotenv()` (cwd
default). Ground Zero's main app already owns `DATABASE_URL` for its own
Postgres/asyncpg connection — if both ran in the same process (which they
do; `main.py` mounts `live_events.app.main` directly), the events module
would try to open the main app's async Postgres URL with its own *sync*
SQLAlchemy engine and fail immediately. Fixed by restoring the same
`EVENTS_`-prefixed, module-anchored `.env` isolation the old module used
(`live_events/app/config.py`, `live_events/.env.example`). Default is
still a local SQLite file at `live_events/data_output/`, same as before.

**Also updated to match the new (no-seed) Event schema** — it no longer
has `verification_status` / `category` / `organizer` fields:
- `scripts/export_layer3_events_cache.py` — Layer 3's "events near me"
  cache export now filters on `status=ACTIVE` + fresh `last_verified_at`
  (same freshness rule the module's own `/events` endpoint uses) instead
  of a `verification_status` field that no longer exists.
- Root `requirements.txt` — bumped `fastapi`/`uvicorn`/`pydantic` to the
  new module's minimum versions, swapped `python-dateutil` → `dateparser`,
  added `psycopg[binary]` (only actually needed if you later point
  `EVENTS_DATABASE_URL` at Postgres instead of the sqlite default).

**Verified, not just written:** clean `pip install -r requirements.txt`
in a fresh venv, then `pytest live_events/` (2/2 pass) and the full
`layer2/` suite (74/74 pass, see below — nothing here touches layer2, but
it's your highest-traffic layer so it got a full re-run anyway).

---

## 2. Transport mode recommendation — real bug, found and fixed

**Root cause:** `layer2/application/routing_service.py` decided the
WALK / AUTO / CAB bucket using **straight-line** (haversine) distance,
then computed the cost and duration actually shown to the tourist from a
**different, larger** distance — a circuity-adjusted or real OSRM-routed
number. In a river-cut, hilly city those two numbers regularly disagree:
two places 700m apart as the crow flies can be a genuine 1.3km by the
only real road (a bridge detour, a hill). That's exactly what produced
recommendations that "look wrong" — a hop tagged WALK whose real distance
was already into AUTO territory, or AUTO whose real routed distance was
already well into CAB range.

**Fix:** the bucket decision and the cost/duration calculation now always
use the *same* distance number for a given leg — the circuity-adjusted
walking distance decides WALK, the real OSRM-routed (or circuity-adjusted
driving) distance decides AUTO vs CAB. See the updated module docstring
and inline comments in `routing_service.py` for the exact before/after.

**Verified:** added `layer2/tests/test_routing_service.py` — 4 new tests,
each proving a specific case the old logic got wrong (a leg whose
straight-line distance says AUTO but whose real routed distance is CAB
territory; a leg whose raw straight-line distance says WALK but whose
circuity-adjusted distance doesn't; a short hop that's still correctly a
free walk with zero OSRM calls). All pass, plus the full pre-existing
`layer2/` suite (74/74, no regressions).

---

## 3. Dataset — one real coordinate bug fixed, queue cleaned, nothing fabricated

### Bug found: Swami Vivekananda Planetarium had the wrong coordinate

Cross-checking the queue against `community_places.csv` turned up a real
error already sitting in the live dataset (not something I added): the
Planetarium's stored coordinate (`12.8686971, 74.8384518`) is Wikipedia's
own infobox figure for that article — and it's ~9km from every other
independently-corroborated coordinate for the Pilikula Nisargadhama
complex the Planetarium is physically inside, including:
- this dataset's own `Pilikula Nisargadhama` entry (12.9241, 74.8918)
- this dataset's own `Pilikula Zoological Garden` entry (12.92754, 74.90213)
- a third, non-Wikipedia source (latitude.to) that independently places
  Pilikula Nisargadhama at 12.9245, 74.8907 — matching this dataset, not
  Wikipedia

**Fixed**: reset to `12.9241, 74.8918` (the verified Pilikula anchor
point) — complex-level precision (correct enough to route/walk to), not
an exact-door pin, and the row's own address field now documents exactly
why and what it was corrected from. Re-verified through the real
`SpreadsheetListingSource.fetch()` loader and `test_spreadsheet_source.py`
(5/5 pass) — the dataset still parses cleanly, still 80 rows.

I also spot-checked a second candidate this same way (Tannirbhavi Tree
Park, from a queued Wikipedia coordinate) and it failed the same
cross-check — 6+ km from this dataset's already-verified `Tannirbhavi
Beach` entry — so I did **not** add it. Given that I'd just caught
Wikipedia's own infobox data wrong once already in this exact
neighborhood, I didn't trust a second, uncorroborated Wikipedia figure
enough to write it into a live recommendation dataset. It's still in the
queue, tagged for a real pin.

### Queue cleaned, then run through your own real ingest pipeline

- Removed 8 rows that were leftover corruption from an earlier partial
  run — retry/error text ("...previous geocode landed on a shared generic
  point...") that had gotten written into the `address` column as if it
  were real queue data, several duplicated.
- Ran `scripts/ingest_new_places.py` for real (not a dry run) — this is
  your own already-built pipeline: it matches queue rows against the
  offline `mangaluru.osm.pbf` extract (3,395 features, zero network,
  zero rate limit) first, and only ever accepts a coordinate that's a
  confirmed, identity-checked match. It found 10 rows already present in
  `community_places.csv` under the same name (deduplicated, nothing
  double-added) and confirmed **no new offline-extract matches** — the
  same offline extract was already fully mined by the ingest run on
  2026-09-21 (7 places added then), so there was nothing left for it to
  find automatically this time. That's a real, verified result, not a
  skipped step.
- I did **not** hand-type coordinates for the rest. Two separate
  Wikipedia-sourced coordinates in this same small area turned out to be
  wrong when cross-checked (see above) — good evidence that hand-picking
  more from search-engine snippets would risk writing bad data into a
  "best recommendation" dataset, which is worse than leaving a place
  queued.

**What's left: 309 rows in `data/new_places_to_geocode.csv`**, now
cleanly organized by your own script's priority system:
- **115** `A - recommendable stop` — real, specific street addresses,
  genuinely tourism-relevant (churches, temples, shrines, museums,
  viewpoints, a food street, etc.) — these are worth a Google Maps pin.
- **49** `A - recommendable stop (address is vague)` — same category, but
  the only address on file is "Mangaluru, Karnataka, India" — needs a
  name search, not just a geocode.
- **145** `B - reference only` — mostly mosques (64), restaurants/hotels
  with no distinguishing address (56), pharmacies, and other rows your
  own taxonomy already marks as never itinerary-eligible.
- **80 locality names** (Balmatta, Jeppu, Kottara Cross, ...) were
  correctly routed to `data/mangaluru_localities.csv` by the ingest
  script's own logic rather than forced into fake single-point Place
  rows — a neighbourhood name isn't a visitable stop, and the pipeline
  already knows that.

**Fastest real next step, for you** (this needs your own internet
access — Nominatim isn't reachable from this sandbox): open each `A`
priority row's `maps_link` in `new_places_to_geocode.csv`, right-click
the correct pin on Google Maps, copy the lat/lon, paste into that row's
`pin_lat` / `pin_lon` columns, then re-run
`python scripts/ingest_new_places.py` — it picks up hand-pasted pins
automatically (see the script's own docstring) and adds a real,
verified coordinate with zero risk of a wrong online match. For the
generic-address tail, `python scripts/geocode_new_places.py` on your
machine (real internet, respects Nominatim's 1 req/sec policy) is the
other option already built for exactly this.

---

## Full verification run (this session, clean venv)

```
pip install -r requirements.txt      # clean, no conflicts
pytest layer2/                       # 74 passed
pytest live_events/                  # 2 passed
pytest layer0/tests/test_spreadsheet_source.py   # 5 passed (dataset still loads cleanly)
pytest layer0/ layer2/ live_events/  # 252 passed, 9 failed
```

The 9 failures are pre-existing and environment-only — every one of them
is `[Errno 111] Connect call failed ('127.0.0.1', 5432)`: they need a
live Postgres+PostGIS instance, which this sandbox doesn't have. Same
gap documented from prior sessions, not something this session touched
or broke.
