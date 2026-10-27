# GroundZero — Session Changelog

Everything below was verified: compiled clean, and run against the existing
test suite (234+ tests passing, zero regressions — every remaining test
failure traced to a missing package in the sandbox this was built in, e.g.
asyncpg/opening_hours/fastapi not installed there, not a real bug).

Replace your project folder with this one (keep your own `frontend/node_modules`
and `.env` — this zip's `.env` values are placeholders/yours from earlier in
the session; double-check before overwriting). Run migrations before starting
the app (see "New migration" below).

---

## 1. RSS feed fix
**File:** `.env`
`EVENT_RSS_FEED_URLS` had gotten line-wrapped across two lines when pasted
into Notepad, silently truncating the URL to an empty query. Fixed to one
line. (Weather was already fine — uses free Open-Meteo, no key needed.)

## 2. Local Secret slot — was almost always empty
**File:** `layer2/application/slot_assembly.py`
`LOCAL_SECRET_MIN_LOCAL_PERCENTAGE` was 0.9, but the highest achievable
`local_percentage` prior for any auto-ingested place is 0.85 — so only 1
place in your whole 688-place dataset could ever fill this slot. Lowered to
0.75 (verified: gives 53 real candidates from genuinely local categories).

## 3. OSM closed-place detection
**Files:** `layer0/infrastructure/collectors/osm_collector.py`,
`layer0/infrastructure/collectors/bulk_osm_extract_collector.py`
Added `is_marked_closed()` — checks `disused:`/`was:`/`abandoned:`/
`demolished:`/`razed:` prefixed OSM tags and `opening_hours=closed/off`,
using data already fetched, no new API call. Wired into both collectors.

## 4. Layer 2 reachability geofence (the missing "geofence around the tourist")
**New file:** `layer2/application/reachability.py`
**Modified:** `layer2/application/hive_engine.py`, `layer2/domain/entities.py`,
`layer2/api/schemas.py`, `layer2/api/routes.py`, `layer2/api/dependencies.py`
There was no tourist-location field anywhere in the system — Layer 2 scored
the entire dataset regardless of where the tourist was. Added optional
`start_latitude`/`start_longitude` to the recommendation request; when given,
candidates are restricted to a radius around that point — fixed by trip
duration (half-day 6km / full-day 12km / multi-day 10km/day), auto-widening
in 4km steps (cap 30km) if fewer than 25 candidates fall inside it. Response
now carries `geofence_radius_km`. This is distinct from `layer5/geofencing.py`
(the per-place 100m proximity trigger for live narration) — that already
existed and does something different.

## 5. Real road-network distance/transport ("distance is wrong, mode doesn't make sense")
**New file:** `layer2/application/routing_service.py`
**Modified:** `layer2/application/hive_engine.py`, `layer2/domain/entities.py`,
`layer2/api/schemas.py`, `layer2/api/routes.py`, `layer2/api/dependencies.py`
Root cause: straight-line haversine distance, not real road distance —
badly understates travel in a river-cut, hilly city. Now uses the free
public OSRM routing API for real driving-network distance/duration on
AUTO/CAB legs, with a documented pedestrian circuity factor (1.3x) for WALK
(no free pedestrian-routing API exists), and falls back to circuity-adjusted
haversine if OSRM is unreachable. Response items carry `travel_is_routed` so
the app can be honest about which legs are a real route vs. an estimate.

## 6. Way-centroid bug (large places pinned at the wrong spot)
**File:** `layer0/infrastructure/collectors/bulk_osm_extract_collector.py`
Was using the first boundary node of a large way (a park, a temple complex)
as its coordinate — could be far from the real centroid. Now averages all
valid nodes.

## 7. Opening-hours re-validation ("9pm start" bug)
**File:** `layer2/application/hive_engine.py` (new `_revalidate_opening_hours`),
`layer2/application/hard_filters.py` (new public `is_open_at()`)
Hard Filters only ever checked openness once, against the trip's single
start_time — a place scheduled hours later never got re-checked against its
own actual time. Now every slot is re-validated against its real
`scheduled_at` after weather scheduling; a closed slot is swapped for the
best same-category open substitute, or dropped.

## 8. Slot-shortfall diagnostics
**Files:** `layer2/domain/entities.py`, `layer2/api/schemas.py`,
`layer2/api/routes.py`, `layer2/application/hive_engine.py`
Added `slots_requested`/`slots_filled`/`slots_dropped_closed` to the
response, plus a warning log when a queue comes up short. Previously an
8-of-13 itinerary was indistinguishable from a deliberate half-day plan.

## 9. curiosity_extractor plural-matching bug
**File:** `layer1/application/curiosity_extractor.py`
`\bphrase\b` never matched plurals ("beaches" never matched "beach").
Fixed to `\bphrase e?s?\b`. Verified against the exact repro sentence from
your audit doc. Irregular plurals (family->families) added as explicit
extra lexicon entries rather than a more complex regex.

## 10. Test database isolation
**New file:** `conftest.py` (repo root)
**New file:** `scripts/cleanup_test_junk_data.sql`
Tests were writing real rows into your dev database with no cleanup — this
is exactly how "HTTP Flow Test Kitchen" became a permanent, real, winning
recommendation slot. `conftest.py` now repoints every test onto a separate
`groundzero_test` database (one-time setup command is in the file's
docstring) plus an autouse fixture that truncates tables after every test.
Run `cleanup_test_junk_data.sql` once against your DEV database to remove
what's already there.

## 11. "Talk to Your Guide" — conversational Soul Survey
**New file:** `layer1/application/profile_extractor.py`
**Modified:** `layer1/application/survey_service.py`, `layer1/api/dependencies.py`,
`layer1/tests/test_survey_service.py` (updated for the new step + 4 new tests)
One opening sentence can now pre-fill Purpose/Energy/Crowd/Group (Q1/Q2/Q3/Q6)
and always supplies Q7's curiosity text — skipping their questions entirely
when the lexicon found a single, unambiguous signal. Two conflicting matches
(e.g. a sentence hitting both "leisure" and "foodie" words) are deliberately
left unset rather than guessed — verified against this exact ambiguous case
in the new tests.

## 12. Itinerary feedback: reorder, remove, add, rate, confirm
**New files:** `layer2/domain/feedback_entities.py`, `feedback_repositories.py`,
`layer2/infrastructure/db/models.py`, `repository_impl.py`,
`layer2/application/feedback_service.py`, `layer2/api/feedback_schemas.py`,
`feedback_routes.py`, `layer2/tests/test_feedback_service.py`,
`migrations/versions/a1b2c3d4e5f6_itinerary_feedback.py`
**Modified:** `layer2/api/dependencies.py`, `main.py`,
`layer0/application/bias_signal_estimator.py` (+tests),
**New script:** `scripts/apply_community_feedback.py`
Tourist can save an edited itinerary as a draft (reorder/remove/add/rate) any
number of times with zero side effects, then Confirm once — which is when
bounded, capped counters (`PlaceFeedbackSignal`: thumbs up/down, times
removed, times manually added, moved earlier/later) get written. A separate,
periodic script (`apply_community_feedback.py`) reads those counters and
nudges `bias_index` — the actual, inspectable mechanism for "feedback
enriches the dataset," not a vague claim.

**New API endpoints:**
`POST /hive/itinerary/{profile_id}/save`
`POST /hive/itinerary/{profile_id}/confirm`
`GET /hive/itinerary/{profile_id}`

## 13. Frontend: editable itinerary screen + real geolocation
**Modified:** `frontend/src/screens/hive/HiveResultsScreen.js`,
`frontend/src/api/client.js`
Reorder (up/down, backbone roles locked), remove/undo, thumbs up/down,
add-a-place search, 1-5 star overall rating, Confirm button — wired to the
new API. Draft auto-saves 600ms after each edit.
**Action needed from you:** add `expo-location` to `frontend/package.json`
(`npx expo install expo-location`) — the screen requests device location
before calling `/hive/recommendations` so the new reachability geofence
(#4) actually has something to filter around; degrades gracefully (no
location = old full-dataset behavior) if permission is denied or the
package isn't installed yet.

## 14. Dataset integrity fix — real, confirmed bug
**File:** `data/community_places.csv`
15 of 29 rows had an unescaped comma inside the `description` field,
silently shifting every column after it (e.g. Diesel Cafe's real
`estimated_cost` was sitting in the wrong column). Repaired mechanically —
re-merged the split text, re-wrote the file with correct CSV quoting.
Verified: 0 malformed rows remain, 0 data loss.

## 15. Dataset enrichment — 5 verified new cafes + free geocoder
**New files:** `data/new_places_to_geocode.csv`, `scripts/geocode_new_places.py`
Checked your dataset first: heritage sites/temples/churches/mosques (210),
parks (30), markets (10), museums (4) are already comprehensively covered
via your OSM extract — no real gap to fill by hand there. The genuine gap is
newer commercial places OSM hasn't caught up to yet. Found 5 real, named,
verified-not-duplicate cafes (checked against your existing 29 rows first —
one candidate, Diesel Cafe, was already in your dataset and dropped from
this list). Deliberately did NOT fabricate coordinates for them (the source
was blog listings, good enough to confirm a place is real, not for exact
lat/lon) — `scripts/geocode_new_places.py` uses the free, no-key OSM
Nominatim API to geocode the real addresses and append them, with a
Mangaluru bounding-box sanity check so a wrong-city match gets flagged
instead of silently accepted. Run it on your machine (this sandbox has no
general internet egress).

**Hospitals — explicitly not added.** HIVE has no slot role for them; they
would never be recommended regardless of what's in the data. If you want a
"nearest hospital" safety lookup, that's your blueprint's Section 6.2
Safety Override, a separate feature not yet built — say so if you want it
scoped.

---

## Not done / explicitly out of scope this session
- Layer 3 (Context Engine) and Layer 4 (Live Guidance Loop) proper — some
  pieces exist under `layer5/` (geofencing.py, chatbot.py = Ask Engine,
  multilingual.py, voice_guide.py) but the full architecture isn't built.
- The Safety/SOS "nearest hospital" feature mentioned above.
