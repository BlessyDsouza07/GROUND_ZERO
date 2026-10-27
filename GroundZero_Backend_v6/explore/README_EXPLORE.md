# Chunk 3 — Explore (backend)

## What's actually new here vs. what's reused

Same pattern as `trips/` (chunk 2): almost nothing needed reinventing.

| Piece | Where it really lives | What `explore/` adds |
|---|---|---|
| Place data, tags, bias/media-mentions, crowd level, best_time | `layer0` (unchanged) | Reads it through the existing `PlaceRepository` |
| Personal Fit Score (companion/energy/curiosity/crowd/time weighting) | `layer2/application/personal_fit_score.py` (unchanged) | Feeds it a **synthetic, lightweight `TouristProfile`** built from the chosen mood instead of a full 9-question survey — see "How moods work" below |
| Weather | `layer0/infrastructure/collectors/weather_collector.py` (unchanged, real Open-Meteo) | Calls it for the "Right Now" panel and "Why Now" reasoning |
| Tide | `layer0/infrastructure/collectors/tide_collector.py` (unchanged, real WorldTides/Open-Meteo Marine) | Same |
| Sunset/sunrise | — | **New**: `astral` (added to `requirements.txt`) — real offline astronomical calculation from lat/lon/date, not an API call, not a guess |
| Live events ("Happening Today") | `live_events/` (unchanged, its own DB) | Reads its DB directly for a today-count and today-list |
| Opening-hours / freshness checks | `layer0/application/opening_hours_parser.py`, `freshness.py` (unchanged) | Used for "open now" and "why now" |
| Add a place to a trip | `trips/service.py::add_place` (unchanged — the exact function chunk 2's "add a place" screen calls) | Wires Explore's "ADD TO MY JOURNEY" CTA to it |
| New: auth-optional read path | — | The one genuinely new mechanism — see below |

## How moods work (and the one honest limitation in the inherited scoring code)

A mood is **not** a stand-in for the 9-question survey — it's a deliberately light profile (`explore/service.py::_mood_profile`) so a signed-out tourist gets a real Personal Fit Score breakdown, not a fabricated "match %". Each mood maps to a small set of tag weights (`explore/mood_profiles.py::MOOD_TAG_WEIGHTS`), checked against the **real tags** in the current dataset (`heritage_site`, `beach`, `local_kitchen`, etc — verified against `layer0/data_output/master_data_core.json`, not assumed).

One thing worth flagging rather than quietly working around: `PersonalFitScoreService`'s curiosity-affinity lookup matches a profile's weight keys against either `place.category` (exact string) or `place.tags`. In the actual dataset, `category` is an upper-case bucket label (`"FOOD"`, `"SPIRITUAL"`, `"NATURE"`...) while the scoring code's own worked examples assume lower-case descriptive categories (`"restaurant"`, `"heritage_site"`). That mismatch already existed in the inherited Layer 1/2 code (it isn't something this chunk introduces), and it means category-level matching silently never fires — only tag-level matching does. Explore's mood weights are deliberately written at the tag level so they work correctly today; the category-casing mismatch itself is a Layer 1/2 fix, not an Explore one, and is called out here rather than silently patched around in a way that would mask it from whoever eventually does fix Layer 1/2.

## The auth-optional read path (the one real architectural change)

Every other router in this backend (`trips/`, `layer3`, ...) requires a bearer token on **every** request — `auth/dependencies.py::get_current_user` raises 401 if it's missing. Carol's Explore spec explicitly requires browsing to work before sign-up, with sign-in only required at save/add-to-trip/personalize moments. So:

- Every `GET /explore/*` route is reachable signed-out.
- `POST /explore/add-to-journey` is the one route that requires sign-in, using the exact same bearer-token dependency every `/trips/*` route already uses (`auth.dependencies.get_current_user`) — no new auth mechanism, just a router that doesn't force it everywhere.
- `explore/dependencies.py::get_current_user_optional` exists for future routes that want to *personalize if signed in, but not require it* — not currently used by any route in this chunk (every current route is either fully open or fully gated), kept because the spec's personalization section ("Because you liked...") will need it once real behavioral history exists.

## Endpoints

| Method & path | Auth | What it returns |
|---|---|---|
| `GET /explore/moods` | none | The 9 moods (slug/label/tagline) |
| `GET /explore/context?lat&lng` | none | "Right Now in Mangaluru": weather, tide, sunset countdown, today's event count, headline (`"A GOOD MORNING IN MANGALURU"` etc.), plus `weather_note`/`tide_note` reasoning strings |
| `GET /explore/happening-today` | none | Today's live events |
| `GET /explore/picks?mood=&lat=&lng=` | none | "GroundZero Picks" — Personal Fit ranked, each with `fit_percent`, `why_this_pick` checklist, `why_now` headline+reasons |
| `GET /explore/beyond-the-obvious?lat=&lng=` | none | Lowest-media-mention, verified-authentic places, each with `why_found_this` |
| `GET /explore/experiences?lat=&lng=` | none | The 7 Explore-by-Experience categories with a preview + total count each |
| `GET /explore/experiences/{slug}` | none | Full list for one category |
| `GET /explore/search?q=&category=&max_distance_km=&open_now=` | none | Search + suggested-searches list |
| `GET /explore/place/{place_id}` | none | Full place-detail page data: why_go, good_for, why_now |
| `POST /explore/add-to-journey` | **required** | Adds the place to the user's most recent draft trip (or returns `no_active_trip` with guidance to start New Trip, which already supports pinning this place via `pinned_place_ids`) |

## Verified, not just written

Checked against the same real, running stack chunk 2 used (Postgres 16 + PostGIS, 708 real Mangaluru places, full `uvicorn main:app` boot, all layers healthy including `live_events`):

- `/explore/moods`, `/explore/context` (weather/tide correctly report `unavailable` rather than fabricate a value — this sandbox's network proxy blocks the outbound Open-Meteo/WorldTides calls, so the "never fake it" path is the one actually exercised here, same as chunk 2's weather test), `/explore/picks`, `/explore/beyond-the-obvious`, `/explore/experiences` (and one category), `/explore/search`, `/explore/place/{id}` — all called for real over HTTP and returned real place data.
- The full auth-gating behavior: `POST /explore/add-to-journey` without a token → 401; with a token but no draft trip → `no_active_trip`; registered a real test user, ran the real 9-question survey end to end, called the real `/trips/generate` (which really calls OSRM — slow in this sandbox because the network proxy blocks it and the resilient HTTP client retries before giving up gracefully, same pre-existing behavior as chunk 2, not something this chunk changed), then called `/explore/add-to-journey` again — it found that draft trip automatically and added the place. Fetched the trip back via `GET /trips/{id}` and confirmed the place is really in there.
- `pytest trips/tests/` — all 3 still pass (Explore reuses `TripsService.add_place` unmodified).
- A pre-existing `MissingGreenlet` async-relationship bug (same shape as the one chunk 2 found and documented in `trips/README_TRIPS.md`) was found and fixed in `explore/routes.py::_find_draft_trip`: querying a trip without `selectinload(Trip.places)` and then calling `TripsService.add_place` (which reads `trip.places` synchronously) raises `MissingGreenlet` under asyncio. Fixed the same way chunk 2 fixed it — `selectinload`, never a manual re-query assigned to the relationship attribute.

## What's genuinely deferred (and why)

- **Real photography.** There is no image/photo field anywhere in this dataset (`layer0/domain/entities.Place` has no such field, confirmed by inspecting the actual 708-place dataset). Every `image_url` in Explore's API responses is `null`. Per Carol's own explicit instruction ("don't fabricate stories... don't invent descriptions simply to make the UI attractive"), this chunk does not wire in stock-photo placeholders pretending to be real place photos — the Flutter frontend instead uses a deliberately plain, honestly-labeled placeholder tile (category icon + color wash from the existing palette), not a fake photo. Wiring real photography is a data-sourcing project of its own (a `photo_url` field + an actual source for it — OSM image tags, a photo upload flow, or a licensed stock source), not something to fake at the API layer.
- **"Because you liked..." personalization.** The spec's behavioral-personalization section needs actual interaction history to be honest (this is also exactly what the "backend reference" doc's event-logging pipeline describes as future work) — no `user_events` table exists yet. `get_current_user_optional` is wired and ready for it, but no route uses it for personalization yet because there's no real signal to personalize on. Building this now would mean fabricating "you seem to like the coast" from zero data, which fails the same "real, verified, defensible" bar everything else in this project holds to.
- **Local-secret "micro stories."** The spec explicitly bans inventing local-legend flavor text. `beyond_the_obvious`'s `why_found_this` field is intentionally the one honest sentence the real data actually supports (media-mention count) rather than a fabricated narrative.
- **MMR-style diversity / embedding-based mood matching / LightGBM ranking** — all explicitly flagged as "eventually" upgrades in the Project's own "backend reference" and "refer for backend" docs, not a literal build instruction for this chunk. `picks()` ranks by the existing, real Personal Fit Score formula; nothing here pretends a learned ranking model exists.
- **`category` upper/lower-case mismatch** in the inherited `PersonalFitScoreService` (see above) — flagged, not silently patched, since fixing it belongs to Layer 1/2, not Explore.

## Run it

Same server, same command as chunks 1-2 — Explore is one more router on the same app:

```
uvicorn main:app --reload
```

New dependency: `astral` (added to `requirements.txt`) — pure-Python, no network, no API key.
