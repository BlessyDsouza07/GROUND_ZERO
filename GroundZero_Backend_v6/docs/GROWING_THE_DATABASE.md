# Growing the Master Data Core to real Mangaluru-wide coverage

## Read this part first — an honest expectation-setting note

You asked for "every single place in Mangaluru, not missing even one
corner or street." No mapping company on earth — not Google, not OSM
itself — can honestly claim 100% completeness for a city. What *is*
realistically achievable, and what this update actually builds, is:

1. A **much wider automatic net** (Layer 0's OSM collector now pulls far
   more categories — lodging, viewpoints, caves, waterfalls, sports
   venues, archaeological sites, wayside shrines, etc. — see the diff in
   `layer0/infrastructure/collectors/osm_collector.py`).
2. A **free, unlimited, non-API path** for everything OSM will never see
   — the tiny local kitchen, the neighbourhood shrine, the fisherman's
   shortcut — via a CSV spreadsheet you and trusted local contributors
   fill in directly. This is the "spreadsheet approach" you asked for.
3. A **freshness/verification loop** so places that get recommended are
   the ones the last real check actually confirmed still exist — not a
   one-time snapshot that silently rots.

None of this is a fabricated "complete" database. It's a real mechanism
that gets more complete the more you and local contributors feed it —
same as how OSM itself became comprehensive: lots of real people adding
real, verified entries over time, not one big automated claim of totality.

## Why 12 places is what you saw, and why that's expected right now

Two independent things were both true at once:

- The **live OSM/Wikidata/Wikipedia pull has never actually completed
  from any sandboxed AI environment** — this one included. My own network
  allow-list here does not include `overpass-api.de`, `query.wikidata.org`,
  or `en.wikipedia.org` (confirmed — see `network_configuration` in this
  session). This matches your own audit's finding. The pipeline code is
  real and correct; it simply has never run to completion anywhere except
  your machine/server with open internet access.
- Whatever count you saw was from **your own run**, against the
  **previous, narrower OSM tag list** (roughly a dozen amenity/tourism
  categories) over a single bounding box query. A narrower tag list plus
  whatever fraction of Overpass's dataset actually has a `name` tag in
  that box will produce a modest number — not the low hundreds you'd
  expect for the whole city.

The tag-list expansion in this update (see below) and the spreadsheet
path together should raise that count substantially the next time you
run the pipeline for real — but you should expect to see it grow over
several runs and several rounds of community contribution, not jump to
"complete" in one shot.

## The three coverage channels, after this update

| Channel | What it covers | Rate limits | Needs |
|---|---|---|---|
| OSM Overpass (existing, now wider) | Anything already mapped on OpenStreetMap: most restaurants, temples, churches, beaches, parks, shops, viewpoints, lodging | Fair-use only; already tiled + concurrency-capped in this codebase | Open internet egress from wherever you run the pipeline |
| Wikidata + Wikipedia (existing) | Enriches OSM/spreadsheet matches with description, heritage status, history | Fair-use only | Same as above |
| **Spreadsheet / CSV (new)** | Anything a local person knows about that isn't on any map API — hidden kitchens, shrines, informal viewpoints | **None — it's a local file read** | Someone to fill in the CSV |

## Channel 0 (new): Fully offline OSM — genuinely zero API, zero rate limit

Everything above (OSM Overpass, Wikidata, Wikipedia) is free and legal,
but it does make a live network call to a third-party server every time
the pipeline runs. If you want **literally zero API calls, zero rate
limit exposure, period**, here's the real mechanism for that — not a
workaround, this is how large offline map applications actually do it:

### Step 1 — get a local OSM extract file (free, one-time, no API key)

Pick one:

**Option A — custom-area extract (recommended, smaller file):**
1. Go to https://extract.bbbike.org/ in a browser.
2. Draw or paste a bounding box around Mangaluru:
   `12.75,74.78` to `13.05,75.05` (same box already in `.env`).
3. Choose format `.osm.pbf`, submit. bbbike emails/hosts a download link
   once it's ready (usually minutes). This is a one-time manual request
   through a web form — not a programmatic API call your app makes.
4. Save the downloaded file as `data/mangaluru.osm.pbf`.

**Option B — whole-India extract, clipped locally:**
1. Download `india-latest.osm.pbf` from
   https://download.geofabrik.de/asia/india.html (a few GB).
2. Clip it to Mangaluru **entirely offline**, no network involved:
   ```
   osmium extract -b 74.78,12.75,75.05,13.05 india-latest.osm.pbf -o data/mangaluru.osm.pbf
   ```
   (`osmium` CLI: `pip install osmium` gives you the Python library used
   by this codebase; for the command-line tool specifically, install
   `osmium-tool` — on Windows, the easiest path is via conda:
   `conda install -c conda-forge osmium-tool`, or use WSL/a Linux VM for
   this one clipping step if you don't have `osmium-tool` on Windows
   directly.)

### Step 2 — point the pipeline at it

In `.env`:
```
OSM_EXTRACT_FILE_PATH=data/mangaluru.osm.pbf
ENABLE_WIKIDATA_WIKIPEDIA_ENRICHMENT=false
```

With both set, `POST /admin/pipeline/run` makes **zero live network
calls of any kind** — OSM data comes from your local file
(`layer0/infrastructure/collectors/bulk_osm_extract_collector.py`),
Wikidata/Wikipedia enrichment is skipped entirely (places still get
everything OSM/the spreadsheet gave them, just without extra description
text — fill `description` in the CSV yourself for spreadsheet places,
which already works today).

**Refreshing later:** re-download/re-clip the extract file whenever you
want updated OSM data (OSM itself updates continuously; your local file
is a snapshot). There's no "expiry" or throttling — you control entirely
when and how often you refresh it, because it's just a file.

**Trade-off, stated honestly:** Wikidata/Wikipedia enrichment (short
history/description text for temples, churches, etc.) genuinely requires
either a live query or a 100+ GB Wikidata/Wikipedia dump — the latter
isn't practical for a project this size. Turning it off means those
description fields come only from what OSM tags or your spreadsheet
provide. If you want that enrichment back at any point, just leave
`ENABLE_WIKIDATA_WIKIPEDIA_ENRICHMENT=true` (the default) — Wikidata and
Wikipedia's public endpoints are free, unauthenticated, fair-use services
with no hard request cap for a single city's worth of places; they are
not the kind of commercially rate-limited API (like OpenWeatherMap or
WorldTides) this system otherwise avoids running without a key.

## How to use the spreadsheet channel

1. Open `data/community_places.csv` in Excel or Google Sheets (or start
   fresh from `data/community_places_TEMPLATE.csv`, which has just the
   header row).
2. `data/community_places.csv` already has a **starter batch of ~21 real,
   named Mangaluru places** pulled from public sources this session
   (Wikipedia's "Tourist attractions in Mangaluru" article, Incredible
   India's official Karnataka tourism page, and a few travel-guide
   round-ups — every row's `source_url` column says exactly where it came
   from). **Every coordinate in that starter file is my best approximate
   placement, not a GPS-verified pin** — several rows say so explicitly in
   the `address` column. Before you rely on any of them for real geofence
   triggers (Layer 3's 300m proximity check), open each one in Google Maps
   or OpenStreetMap and correct the lat/lon. This is exactly the kind of
   verification pass the blueprint's admin workflow expects before data
   is trusted.
3. Add rows for places you and your team actually know — this is where
   "every corner, every street" genuinely gets closer to true, because
   it's the one channel with no ceiling and no API to wait on.
4. Save/export as CSV, keep it at `data/community_places.csv` (or point
   `SPREADSHEET_PLACES_CSV_PATH` in `.env` at wherever you keep it).
5. Run the pipeline (`POST /admin/pipeline/run`, or the periodic script —
   see below). Every row becomes a `Place` and flows through the exact
   same accessibility detection, Wikidata/Wikipedia enrichment attempt,
   bias audit, dedup-against-OSM, and freshness scoring that an
   OSM-sourced place gets. Nothing downstream (HIVE, Hard Filters,
   Context Engine) needs to know or care which source a place came from.

## Column reference (`data/community_places_TEMPLATE.csv`)

Only `name`, `category`, `lat`, `lon` are required. Leave anything else
blank if you don't know it — the system falls back to a documented
category-level default (see `layer0/application/place_enricher.py`)
rather than guessing on your behalf, exactly like it does for OSM data.

| Column | Meaning |
|---|---|
| `name` | Place name (required) |
| `category` | e.g. `beach`, `heritage_site`, `local_kitchen`, `park`, `museum`, `viewpoint`, `market`, `attraction` |
| `lat` / `lon` | Decimal coordinates (required) |
| `address` | Free text |
| `description` | 1-2 sentences — feeds the Ask Engine's grounded answers |
| `curator` | Who added this row (for accountability, not shown to tourists) |
| `source_url` | Where you got the info, if anywhere public |
| `opening_hours` | e.g. `09:00-18:00` or an OSM-style opening_hours string |
| `tags` | Semicolon or pipe separated, e.g. `temple;heritage;quiet` |
| `price_band` | `free` / `budget` / `moderate` / `premium` |
| `estimated_cost` | INR, numeric |
| `energy_requirement` | `low` / `moderate` / `high` |
| `crowd_level` | `low` / `moderate` / `high` / `variable` |
| `dwell_time_typical_minutes` | Numeric |
| `tide_dependency` | `true`/`false` — for coastal spots |
| `season_suitability` | Semicolon list, e.g. `winter;monsoon-avoid` |
| `accessibility_tags` | Semicolon list, e.g. `wheelchair;stairs-only` |
| `etiquette_tag` | Short whisper line, e.g. `remove footwear` |
| `best_time` | `morning` / `sunset` / etc. |
| `parking` / `washrooms` / `food_available` / `family_friendly` / `kid_friendly` / `photography_allowed` | `true`/`false` |
| `contact_phone` | Free text |
| `local_percentage_hint` | 0-1 or 0-100 — **this directly feeds the Bias Index formula.** A local person's honest estimate here is a real signal, more reliable than the system's category-level guess. |
| `media_mentions_hint` | Integer — same idea, for how much online/press coverage the place has. Low number + high local_percentage is exactly what should win a Local Secret slot. |

## The verification/freshness loop (Section: "ensure recommended places are open, not closed/relocated")

This part of your ask was already partly built into the blueprint and
this codebase — it just needed to actually run on a schedule:

- Every place has a `freshness_score` that decays over time
  (`layer0/application/freshness.py`) and a `temporarily_unavailable`
  flag. Layer 2's Hard Filters (5.1) already drop any place whose
  freshness_score is too low or that's flagged unavailable — a stale or
  closed place is mechanically excluded from recommendations, not just
  "hopefully" fine.
- What was missing: something to actually *re-run the checks* regularly,
  so freshness reflects reality instead of slowly decaying toward the
  180-day default with no fresh evidence either way.
- `scripts/run_periodic_pipeline.py` (new) closes that gap for free, with
  no new scheduler dependency: it calls the existing
  `/admin/pipeline/run` endpoint on an interval you choose. Every place
  the sources still confirm gets its freshness refreshed to "just
  verified"; a place that's vanished from OSM (closed/demolished/no
  longer tagged) simply stops getting refreshed and ages out of
  recommendations on its own within days, not 180.

This is honest about its limits too: it re-checks against the same free
sources, so it can't catch a closure that hasn't been reflected on OSM
yet. There is no free, legal, unlimited API that gives real-time
open/closed status for arbitrary small businesses — if one existed, every
travel app would already use it.
