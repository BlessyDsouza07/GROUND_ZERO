# 2026-09-22 — verifying the remaining ~312 places, and the weather/tide APIs

## The remaining ~312 unverified places: real attempt, real result, not fabricated

Tried this for real, not just eyeballing it. Two things worth knowing before you decide what to do next:

**1. Your own pipeline already tried the cheap win.** `data/duplicate_cleanup_report.txt`
and `data/ingest_last_report.txt` (already in your zip from before) show an
offline-OSM cross-check already ran against this exact queue — only 7 of
327 names matched something in the OSM extract. That's not a bug, it's
because most of these (neighbourhood mosques, unmapped beaches, small
shrines) genuinely aren't in OpenStreetMap yet.

**2. I then tried real web research on a sample, and hit the same wall your
research team did.** Example: Batapady Beach — no page, no government
listing, no source anywhere gives a precise pin for the beach itself, only
for the village it's near (~1-2km off, not "coordinate_ready_for_use"
precision). Mukka Beach — same story, only the suburb's centroid is
published, not the beach. That's *why* these sat at
`NOT_YET_INDEPENDENTLY_VERIFIED` — your team already looked and came up
empty, not because nobody checked.

One did verify cleanly and is worth a look: **Aloyseum (St. Aloysius
Museum)** — Wikidata lists a coordinate for it, but that coordinate is
~4km from the known St. Aloysius College campus, which is almost certainly
a bad Wikidata import (a known, common issue with auto-imported Wikidata
coordinates for small entities). I didn't add it rather than add a pin I
don't actually trust.

**What I didn't attempt:** the ~70 individual neighbourhood mosques in the
queue (Aisha Juma Masjid, Badria Masjid, Kassaigalli Masjid, etc.). These
are hyperlocal places with no realistic public source for a verified pin,
and low tourism value even if verified — not a good use of research effort
against a tourism-recommendation dataset.

**Honest bottom line:** getting real, defensible coordinates for the bulk
of the remaining ~312 needs one of:
- A paid/registered geocoding pass (Google Geocoding API, ~$5/1000 lookups,
  or a similar service) run systematically against the address column —
  this is what would actually move the needle, not more manual search.
- Accepting locality-level precision (village/neighbourhood centroid, not
  an exact pin) for places where that's all that exists, with an explicit
  `coordinate_status=LOCALITY_LEVEL` flag so HIVE/Ask Engine know it's
  approximate. I didn't do this unprompted since it changes what
  "verified" means in your pipeline — say the word and I'll build it.

## Weather API — already solved, confirmed working

`weather_collector.py` already runs on Open-Meteo's forecast API — free,
keyless, no signup, no billing account needed (this is why it doesn't use
`OPENWEATHERMAP_API_KEY`; OpenWeatherMap's One Call 3.0 needs a
billing-enabled account even on its "free" tier, so it was swapped out
before I ever touched this). Nothing to fix here — it already works
cleanly out of the box.

## Tide API — now has a free fallback, and is actually wired up

Two real problems, both fixed:

1. **`TideCollector` existed but was never wired into the app** —
   `dependencies.py` built a `WeatherCollector` but never built a
   `TideCollector`, so even with your `TIDE_API_KEY` sitting in `.env`,
   nothing in the running app ever used it. Added `get_tide_collector()`
   to `layer2/api/dependencies.py`, same pattern as `get_hive_engine()`'s
   weather wiring, so anything (Layer 3's Context Engine, once built) can
   just `Depends(get_tide_collector)`.

2. **WorldTides (the coded primary source) isn't really free** — its free
   tier is a small one-time credit grant, not a daily quota, so it'll work
   for a demo and then stop. Added a free, keyless fallback: Open-Meteo's
   Marine Weather API (`sea_level_height_msl`), same no-signup approach
   already proven out for weather. `TideCollector.extremes()` now: uses
   WorldTides if `TIDE_API_KEY` is set and it's reachable; falls back to
   Open-Meteo Marine if the key is missing or WorldTides fails; raises
   `SourceUnavailable` (never fake data) if a coordinate is off the marine
   model's ocean grid.

   Be aware this fallback is honestly a different kind of data — Open-Meteo
   Marine's sea-level series is referenced to mean sea level, not a
   harmonic tide-station datum, and "High"/"Low" are detected as local
   peaks/troughs in that series rather than looked up from official tide
   constituents. Good enough for a rising/falling suitability signal
   (blueprint Table 6, "Tide state") — not a substitute for an official
   tide table. Every `TideExtreme` now carries a `source` field so
   downstream code always knows which kind it got.

   New test file `layer0/tests/test_tide_collector.py` (6 tests, all
   passing) covers: WorldTides path, fallback-when-no-key, fallback-when-
   WorldTides-down, correct peak/trough detection on a synthetic series,
   raising rather than faking data on an off-grid coordinate, and a
   timezone bug I found and fixed while writing the fallback (naive vs.
   aware datetime comparison would have crashed `current_state()`).

**What's still open, and it's a real gap, not something I patched around:**
nothing in Layer 3 actually *consumes* tide (or weather) data yet for the
live Context Engine two-tier check — that layer isn't built out. The data
sources are now correct and wired; the scoring logic that reads them for
the real-time silence-filter isn't there yet. Said this before and it's
still the honest state of things.

## Full verification run
`pytest layer0 layer2` (with the project's own listed dependencies
installed, no live Postgres): **231 passed, 7 failed** — all 7 failures are
`ConnectionRefusedError` against `127.0.0.1:5432` (no Postgres in this
environment), not a real regression. Nothing in this batch broke anything
that was passing before.
