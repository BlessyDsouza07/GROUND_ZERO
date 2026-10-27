# Session notes — Aug 30, 2026: database completeness pass

Carol reported only ~12 places in her database and asked for
comprehensive Mangaluru coverage, verified/fresh recommendations, and a
free/legal/no-rate-limit approach (ideally spreadsheet-based). This
session's changes, read together with `docs/GROWING_THE_DATABASE.md`
(the detailed version of everything below — read that one first):

## What was actually built

1. **`layer0/infrastructure/collectors/spreadsheet_source.py` (new).** A
   `ListingSource` that reads places from a local CSV — zero API calls,
   zero rate limits, zero cost. Registered automatically in
   `layer0/api/dependencies.py`. This is the direct answer to "do it for
   free on a spreadsheet."
2. **`ListingRecord` extended** (`local_listings_collector.py`) with ~20
   new optional fields (opening hours, tags, price, accessibility,
   etiquette, and crucially `local_percentage_hint` /
   `media_mentions_hint` — real inputs to the Bias Index formula from
   `etl_orchestrator.py::_listing_record_to_place`, which was rewritten
   to use every field a curator provides and fall back to the existing
   category-level defaults for anything left blank).
3. **`data/community_places.csv` (new)** — a starter batch of 21 real,
   named Mangaluru places (beaches, temples, churches, parks, a fort, a
   museum, local eateries) pulled from public sources this session, each
   row citing its `source_url`. **Coordinates are approximate and marked
   as needing verification** — see the caveats in
   `docs/GROWING_THE_DATABASE.md`. `data/community_places_TEMPLATE.csv`
   is the blank column-header version for adding more.
4. **`osm_collector.py` tag lists widened** — added lodging, viewpoints,
   caves, waterfalls, sports venues, archaeological sites, wayside
   shrines, and more, with matching category mappings in
   `etl_orchestrator.py::_CATEGORY_MAP`. This makes the existing, correct
   OSM collection pull meaningfully more of what's already mapped.
5. **`scripts/run_periodic_pipeline.py` (new)** — calls the existing
   `/admin/pipeline/run` endpoint on a schedule so freshness/verification
   is continuous rather than only happening whenever someone remembers to
   trigger it manually. No new dependency (no APScheduler/Celery).
6. **5 new tests** (`layer0/tests/test_spreadsheet_source.py`), all
   passing, including one that parses the shipped seed CSV end-to-end.
   Full existing suite re-run: **142 passed** in this sandbox (the same 8
   tests that need a real live Postgres+PostGIS connection — not
   available in this sandbox — fail here exactly as they did before this
   session's changes; verified against the unmodified original zip too).
   A separate manual script confirmed the whole pipeline — spreadsheet
   source through bias audit, dedup, and freshness scoring — runs
   end-to-end and produces correctly differentiated bias scores (e.g.
   Panambur Beach came out `bias_index=0.34 / Balanced` vs. Sasihithlu
   Beach `bias_index=0.17 / Authentic`, matching the philosophy).

## What this does NOT achieve, stated plainly

- **This is not a claim of "every single place in Mangaluru."** No one —
  not this system, not Google, not OSM itself — can honestly claim that.
  What's built is a real mechanism (wider OSM net + unlimited spreadsheet
  channel + freshness loop) that gets more complete over real, ongoing
  contribution, not a one-shot "complete" database.
- **The live OSM/Wikidata/Wikipedia pull still has not run from any
  sandboxed AI environment**, including this one — my network allow-list
  doesn't reach those hosts (see the `network_configuration` block for
  this session). This is unchanged from the prior session's finding and
  is not something any AI assistant working in a sandbox can fix; it has
  to run from your machine or a real server with open internet.
- **The 21-row starter CSV has approximate coordinates**, sourced from
  general travel-guide descriptions, not GPS-verified. Treat it as a
  bootstrap to correct and expand, not a finished, trustworthy dataset —
  verify each row in Google Maps/OSM before depending on it for real
  geofence triggers.
- **The periodic verification script re-checks against the same free
  sources** (OSM/Wikidata/spreadsheet) — it cannot detect a real-world
  closure that hasn't yet been reflected in OSM. No free, legal,
  unlimited API exists that would let it do better than that.

## What you need to actually do next

1. `pip install -r requirements.txt` (no new dependencies were added).
2. Fill in real free-tier `OPENWEATHERMAP_API_KEY` and `TIDE_API_KEY` in
   `.env` — still blank, still your only remaining manual step for those
   two sources.
3. Open `data/community_places.csv`, correct/verify the coordinates,
   and add more rows for places your team knows locally.
4. Run the pipeline for real, from a machine with open internet (see the
   execution commands below).
5. Optionally start `scripts/run_periodic_pipeline.py` so freshness stays
   current without you remembering to re-trigger it.
