# Chunk 2 — New Trip (backend)

## What's actually new here vs. what's reused

Almost nothing in chunk 2 needed reinventing — this backend already had a
fully-built recommendation engine and live-trip orchestrator from before
this chunk. `trips/` is a thin integration layer:

| Piece | Where it really lives | What `trips/` adds |
|---|---|---|
| 9-question survey, skip-logic from free text | `layer1/application/survey_service.py` (unchanged) | Drives it in Carol's exact question order, auto-answers the 4 steps she didn't ask for (purpose, group size, voice personality, group-session setup) |
| Itinerary generation (tag matching, geofence, budget, 13-slot roles) | `layer2/application/hive_engine.py` (unchanged) | Calls it, stores the result as an editable `Trip`/`TripPlace` row set |
| Live-trip mechanics: geofence arrival, silence filter, wallet, SOS, ask engine, pause/resume | `layer3/` (unchanged, mounted at `/l3`) | Hands off to it at confirm time (`POST /trips/{id}/confirm` calls `layer3_orchestrator.start_session`) |
| Tourist-added places | `layer0/application/custom_place_service.py` (unchanged) | Calls it from `POST /trips/{id}/places` |
| New: `Trip`, `TripPlace`, `JournalEntry`, `TripEvent` tables | — | The one thing that didn't already exist: a per-user, editable draft itinerary, journal storage, and a behavioral event log |

## The 9 questions vs. layer1's step order

Carol's list and layer1's own `SurveyStep` order aren't identical — layer1
also asks about purpose, group size, and voice personality, none of which
she wanted asked. `trips/service.py`'s `_AUTO_FILLED` dict auto-answers
those with sensible defaults (or with whatever the opening free-text
sentence already inferred) so the frontend only ever sees Carol's 9:

1. `opening_prompt` — free text
2. `q2_energy` — slider (0–100 → EnergyBand)
3. `q3_crowd_tolerance` — slider (0–100 → CrowdTolerance)
4. `q4_budget` — number stepper
5. `q5_dietary` — choice list (allergy detail is UI-only in this pass — see below)
6. `accessibility` — yes/no + which
7. `q8_trip_duration` — 1 / 2 / 3+ days
8. `q9_start_time` — which part of day
9. `return_visitor_check` — yes/no

One honest deviation: Carol's spec put "have you visited before" as Q8 and
"start now or later" as Q9. layer1's real step machine asks them in the
opposite order (start-time preference, then return-visitor). Reordering
that would mean forking layer1's survey machine instead of reusing it, for
a difference that changes nothing about what's collected — just re-tested
and left as-is. If this needs to match exactly, `_STEP_ORDER` in
`layer1/application/survey_service.py` is the one place to change it.

Also: "start now or schedule later" is handled at **confirm time**
(`POST /trips/{id}/confirm`'s `start_now`/`scheduled_start_at`), not inside
the survey. That's a deliberate design call, not a miss — you review and
edit the itinerary before deciding whether to leave now, and the survey's
own Q9 (`q9_start_time`) is genuinely a different question: which part of
the day you'd *prefer* to start, independent of whether that's today.

## Geofence radius: her literal numbers vs. what's actually wired

Carol's spec said "200m radius, step up by 50m." The real
`ReachabilityService` (unchanged, reused as-is) works in **kilometers**
(6–30km, stepping by 4km, minimum 25 candidates) — a literal 200m radius
around a point in Mangaluru would return zero places almost every time.
`trips/` reuses the km-scale service exactly as built (it already
implements the "step up if the area's too sparse" idea she asked for, just
at a scale that actually returns results) and surfaces
`geofence_radius_km` on every generated trip so the frontend can show
tourists what radius was actually used, rather than either silently
following the literal 200m (breaking the feature) or silently overriding
her stated number without telling her.

## Verified, not just written

This was checked against a real, running stack in this sandbox — not just
read over:
- A local Postgres 16 + PostGIS instance, with the full Alembic migration
  chain (including this chunk's own migration,
  `migrations/versions/c8d2e3f4a5b6_trips.py`) applied cleanly on top of
  chunks 0/1's existing schema.
- The full `main.py` app booted with `uvicorn`, all layers reporting
  healthy (`layer0` through `layer5`, `live_events`), 708 real Mangaluru
  places loaded via `import_master_data.py`.
- A full curl-driven run of the real HTTP flow: register → survey (all 9
  questions, in this exact order) → finalize → generate (produced a real
  12-place itinerary from real data, with roles/costs/travel
  modes/reasons) → add a tourist-added place → remove a place → rate the
  draft → confirm (which really did hand off to layer3 — the returned
  `layer3_session_id` matches) → arrive → checkout (budget correctly
  decremented, `suggest_rest_stop`/`budget_covers_rest_of_trip` correctly
  computed) → top up budget → skip a place → add a journal entry → read
  the journal timeline → exit with a reason.
- 3 automated tests (`trips/tests/test_trips_survey.py`) covering the
  slider→enum threshold mapping and the full 9-question auto-fill/skip
  sequence against the real `SurveyService` — no mocks of the survey
  logic itself, only the DB/profile-repository layer is faked.

Two real bugs were found and fixed by this process, both worth knowing
about:
1. `trips/service.py`'s `get_trip()` originally assigned a freshly-queried
   list directly to the `Trip.places` relationship attribute, which made
   SQLAlchemy lazy-load the *old* collection first to diff against — under
   asyncio that raises `MissingGreenlet` instead of just working. Fixed by
   using `selectinload` instead of a manual re-query + assignment.
2. `layer0/infrastructure/http_client.py`'s retry logic caught
   `ConnectError`/`TimeoutException`/etc. as a signal to raise
   `SourceUnavailable` (Layer 2's intended "skip this source, don't crash
   the itinerary" degradation) but not `httpx.ProxyError` — which is what
   an environment routing egress through a blocking forward proxy raises
   instead of `ConnectError`. Without this, a blocked weather API call
   crashed itinerary generation with a raw 500 instead of degrading
   gracefully (itinerary generation without a weather forecast, exactly as
   the code already intended for other kinds of network failure). Fixed
   by adding `httpx.ProxyError` to the caught tuple.

## What's genuinely deferred (and why)

- **Allergy/accessibility free-text detail**: collected in the Flutter UI
  for the tourist's own reference, but not sent to the backend — there's
  no field for it in `TouristProfile`'s dietary/accessibility enums, and
  adding one would mean changing layer1's domain model, which felt like
  the wrong tradeoff against reusing it untouched. If this needs to
  actually influence recommendations (not just be remembered), the real
  fix is a new `TouristProfile.notes` free-text field that
  `CuriosityExtractor` also scans.
- **Continuous background GPS + automatic arrival detection**: layer3
  already has the real mechanism (`/l3/location/ping` +
  `/l3/context/evaluate`, with the Silence Filter deciding when to speak).
  The Flutter app in this chunk wires the manual "I'm here" / "listen now"
  controls, not a background location stream feeding those endpoints
  continuously — that's a real feature, not a stub, but it's a
  `Timer.periodic` + `geolocator` background listener away from the
  automatic version, not a backend change.
- **Real media upload for journal photos/videos**: `JournalEntry.media_url`
  stores whatever URL the client sends. The Flutter app in this chunk
  sends the local file path as an honest placeholder rather than faking a
  real upload — wiring actual object storage (S3-compatible, or a
  dedicated `/trips/{id}/journal/upload` endpoint) is a drop-in swap of
  one call once that storage exists, not a redesign.
- **A produced photo/video "creative timeline"** (transitions, music,
  auto-editing): needs a media-processing pipeline this backend doesn't
  have. `GET /trips/{id}/journal` gives the honest version — every capture,
  in order, with which place it was at — and the Flutter app renders that
  as a scrollable timeline instead of claiming a produced montage that
  doesn't exist.
- **"Upgrade vs. stick with the original list" on resume outside the
  geofence**: the distance check itself (is the tourist still within
  `geofence_radius_km` of `origin_latitude/longitude`) is cheap enough to
  do client-side without a round trip, so `POST /trips/{id}/resume` takes
  the tourist's decision (`upgrade: true/false`) rather than making that
  call itself — the Flutter app in this chunk does the distance check and
  offers the choice at the point it applies.
