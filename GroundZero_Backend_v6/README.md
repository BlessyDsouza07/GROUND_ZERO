
## Ninth audit response pass (Oct 2026) — real ownership records for tourist_profiles and community_submissions, plus a persistent Save feature

Continuing the Eighth pass's explicit "worked through deliberately, piece
by piece" plan rather than attempting the full multi-week scope at once.
Three concrete items from that remaining list, picked because each is
independently real, independently verifiable, and backward-compatible
with both this combined app and layer0/layer1's standalone deployments:

### Fixed / added

1. **`tourist_profiles` gained a real `user_id` ownership column.**
   `shared/ownership.py::enforce_profile_ownership` previously had no
   direct ownership record to check — it inferred the owner by searching
   the `TripEvent` log for the most recent `survey_completed` event
   referencing a profile, and only rejected access when that log named a
   *different* user. A profile with no matching log entry (log never
   written, pruned, or predating that feature) was treated as unowned,
   i.e. readable by anyone who had the id. Added `user_id` (nullable, no
   FK — `layer1` also runs standalone with no `users` table on its own
   sys.path at all, same trust boundary as before) via
   `migrations/versions/a4b5c6d7e8f9_tourist_profile_ownership.py`,
   stamped at finalize time (`layer1/application/survey_service.py
   ::finalize`, from `SurveySession.user_id` — itself added by an earlier
   pass), mapped through `layer1/infrastructure/db/repository_impl.py`,
   and checked first by `enforce_profile_ownership` (falling back to the
   old TripEvent-log inference only for rows finalized before this column
   existed). **Verified live:** two real signed-in users, one finalizes a
   survey, the other's `/trips/generate` call against that profile_id is
   rejected `403 "This profile does not belong to your account."`; the
   owning user's own call is not rejected on ownership grounds (it
   proceeds to routing, which is where this sandbox's known OSRM-network-
   block slowness lives — a separate, pre-existing, non-bug).
2. **`community_submissions` gained a real `submitter_user_id` column.**
   `POST /places/submissions` already required a signed-in user (an
   earlier pass's auth gate) but never recorded *which* one — `user` was
   fetched and then unused beyond the dependency check. Added
   `submitter_user_id` (same nullable/no-FK pattern, same standalone-
   deployment reasoning) via `migrations/versions/
   b5c6d7e8f9a0_submission_submitter_ownership.py`, threaded through
   `layer0/application/community_workflow.py::CommunitySubmissionService
   .submit` and `layer0/api/routes.py::submit_place`. **Verified live:**
   submitted a place as a real signed-in user, then queried
   `community_submissions` directly in Postgres and confirmed
   `submitter_user_id` matches that user's real id.
3. **Added the persistent Save feature** (`personal/` module — see
   `personal/README_PERSONAL.md`'s new "Saved Places" section for full
   detail): `POST /personal/saved-places/{place_id}`, `DELETE
   /personal/saved-places/{place_id}`, `GET /personal/saved-places`, new
   `saved_places` table with a real FK to `users` (`ondelete="CASCADE"`
   — `personal/` only runs inside this combined app, so unlike the two
   items above there's no standalone deployment to stay compatible with)
   and a `UniqueConstraint` on `(user_id, place_id)`. Save/unsave are
   both idempotent (re-saving or re-unsaving is a 201/204 no-op, not an
   error or a duplicate row). `DELETE /auth/me` (account deletion) was
   also updated to explicitly clear a deleted user's `saved_places` rows,
   matching the existing defensive pattern already used for
   `contribution_records`. **Verified live:** save → idempotent re-save
   → list (1 row, real place name/category) → unsave → idempotent
   re-unsave → list (empty) → save against a nonexistent place_id (404),
   all against the real running stack, not mocked.

All three migrations applied cleanly to both `groundzero` and
`groundzero_test`; the full 366-test suite passes after each one
(reconfirmed after all three combined).

### Deliberately NOT attempted this pass, and why

Still correctly out of scope per the Eighth pass's own reasoning, and
unchanged by this pass: a real media-upload pipeline with object storage;
a grounded Talk-to-Guide/voice implementation; finishing
Notifications/Settings end-to-end beyond what already exists; complete
5-language localization audited screen by screen; Android/iOS platform
projects with a committed `pubspec.lock` and real platform builds (this
sandbox has no Flutter SDK at all — confirmed via `which flutter dart`
returning nothing); and the full production infrastructure checklist
(managed Postgres, HTTPS/domain, object storage, backups with a restore
drill, observability, secrets management, legal/privacy documents) — none
of which a code-editing sandbox can truthfully claim to deliver. This
pass picked the items that were genuinely finishable and verifiable
end-to-end in one sitting; the rest remains exactly what the Eighth pass
said it was — real, substantial, multi-session work, not something to
rush through unverified just to call the scope "complete."

## Eighth audit response pass (Oct 2026) — a zip-hygiene regression found by inspecting the delivered archive, plus extending the Seventh pass's fail-closed config pattern to the main app

Two more review documents arrived, this time explicitly framed as the
**complete remaining release-readiness specification** — effectively
every item from RELEASE BLOCKs 2–9 at once, consolidated and
cross-referenced against OWASP's API security guidance, with an explicit
recommended sequence spanning backend contracts, frontend completion,
infrastructure, and device/E2E testing. The review's own conclusion is
direct about scope: *"treat this as one coordinated release-completion
project with explicit workstreams, not one enormous rewrite,"* and it
lists, as things that categorically "cannot honestly be guaranteed" from
inside a code-editing environment: a real Android build and
physical-device test, an iOS build, a deployed HTTPS environment, a
database backup/restore drill, tests against real external integrations'
failure modes, and final legal/licensing review. That assessment is
accurate for this sandbox too — none of those are possible here, this
pass or any other.

One finding from the review was concrete, specific to the two ZIPs
already delivered, and immediately actionable — so it's fixed here rather
than deferred to a future staged pass:

### Fixed

1. **The delivered backend ZIP wasn't actually clean — `layer3.db-wal`
   and `layer3.db-shm` leaked through.** The Seventh pass's zip-build
   command excluded `*.db` (catching `layer3/data_output/layer3.db` and
   `live_events/data_output/groundzero_events.db` correctly) but SQLite's
   WAL-mode sidecar files — `layer3.db-wal` (70,072 bytes) and
   `layer3.db-shm` (32,768 bytes) — don't end in `.db`, so that pattern
   silently missed them. Confirmed by `unzip -l` against the actually-
   delivered archive, not just by re-reading the build command. Fixed by
   adding explicit `-x "*.db-wal" -x "*.db-shm" -x "*.db-journal"` (plus
   the equivalent `.sqlite3-*` sidecar patterns, for the same class of
   gap) to the zip-build exclude list. This is purely a packaging fix —
   nothing on disk in this sandbox was touched or deleted, since the
   review correctly cautioned that blindly deleting WAL/SHM files next to
   a database that might still be open is unsafe; excluding them from the
   zip sidesteps that entirely. **Verified:** `unzip -l` against the
   freshly rebuilt archive shows zero `.db`/`.db-wal`/`.db-shm`/`.sqlite`/
   `.env`/`__pycache__` entries, and a full extract-into-a-fresh-directory
   + `python3 -m compileall -q .` against the extracted copy (not the
   working tree) is clean — the "final archive verification" step the
   review's own checklist calls for.
2. **The main app's own config had none of the Seventh pass's fail-closed
   checks.** That pass added "refuse to start outside `ENVIRONMENT=
   development` without an explicit, real value" to Layer 3's and Live
   Events' database/admin-key settings, but left the main app's own
   `shared/config.py` — the actual `DATABASE_URL` the whole rest of the
   app runs on — with no equivalent check: `ENVIRONMENT` could be any
   string at all (a typo silently behaves like "not development"
   everywhere else, but nothing ever validated it), and `DATABASE_URL`
   could point at SQLite even in production, since nothing checked the
   scheme. Fixed by extending `get_settings()` with the same two checks,
   same shape as the CORS-wildcard check already a few lines above it in
   `main.py`: `ENVIRONMENT` must be one of `development`/`staging`/
   `production` or startup raises `RuntimeError`; outside `development`,
   `DATABASE_URL` starting with `sqlite` also raises. **Verified:**
   `ENVIRONMENT=production` with a `sqlite:///...` `DATABASE_URL` raises
   the new error; `ENVIRONMENT=not-a-real-env` raises the other new
   error; this sandbox's real `ENVIRONMENT=development` setting is
   unaffected — confirmed by a full app restart booting cleanly and the
   full 366-test suite passing afterward.

### Deliberately NOT attempted this pass, and why

Both new review documents are, by their own explicit framing, the
complete remaining scope — not a short list to fix in one sitting. Line
items include: full ownership/deletion modeling across every
user-generated record type; a persistent Save feature with real
endpoints; a real media-upload pipeline with object storage; a grounded
Talk-to-Guide/voice implementation; finishing Contributions, Notifications,
and Settings end-to-end; complete 5-language localization audited screen
by screen; Android/iOS platform projects with a committed `pubspec.lock`
and real platform builds; and the full production infrastructure
checklist (managed Postgres, HTTPS/domain, object storage, backups with a
restore drill, observability, secrets management, legal/privacy
documents). This is, honestly, several weeks of coordinated backend +
frontend + infrastructure + device-testing work, exactly as the review
itself describes it ("one coordinated release-completion project with
explicit workstreams") — not something that can be truthfully claimed
done, in full, "line by line," inside one more pass. Attempting all of it
at once, without stopping to verify each piece live the way every pass in
this changelog has, is exactly the failure mode every review so far has
warned against, including this one. The two concrete, verifiable items
above were fixed; the rest needs to be worked through deliberately,
piece by piece, each one checked against the real running stack before
being called done — the same discipline this entire changelog has used
from the start.

## Seventh audit response pass (Oct 2026) — RELEASE BLOCK 1 (backend authorization), start of RELEASE BLOCK 2 (data integrity) and RELEASE BLOCK 3 (fail-closed production config)

Two new review documents arrived together (an internal audit and an
OWASP-API-Top-10-framed release-readiness review), both independently
organizing ~40 remaining items into numbered "RELEASE BLOCKs" and both
converging on the identical instruction: fix RELEASE BLOCK 1 (backend
authorization) first, in full, before touching anything else — "do not
work on 33 things randomly." This pass follows that instruction exactly:
RELEASE BLOCK 1 is done and verified live in full; RELEASE BLOCK 2 (data
integrity) and RELEASE BLOCK 3 (production database architecture) are
started — the two items from each that are genuine code-level fixes
rather than infrastructure/ops work this sandbox cannot do — and the rest
of both blocks, plus RELEASE BLOCKs 4–9 (real media, frontend
completion, live intelligence features, full localization, release
infrastructure, and device/E2E testing), are deliberately untouched this
pass, consistent with both reviews' own staging and every prior pass's
reasoning against doing many unrelated things at once.

### Fixed — RELEASE BLOCK 1: backend authorization

1. **Survey sessions had no owner.** `SurveySession` (`layer1/application/
   survey_service.py`) carried no `user_id` at all. Both survey HTTP
   surfaces — `/trips/survey/*` (`trips/routes.py`) and the legacy
   `/survey/*` (`layer1/api/routes.py`), which share the exact same
   `SurveyService`/session-store instance via dependency injection —
   required being signed in, but never checked *which* signed-in user a
   given `session_id` belonged to. Since `session_id` is returned in
   every response body, any authenticated User B who obtained User A's
   `session_id` (logged, leaked, guessed, or simply intercepted) could
   read, advance, or finalize A's in-progress survey — classic OWASP API1
   Broken Object Level Authorization. Fixed by adding
   `user_id`/`requesting_user_id` through `SurveySession`,
   `SurveyService.start_session/get_session/answer/finalize`, both
   routers, and `RedisSurveySessionStore`'s (de)serialization (a field
   that round-trips through Redis the same way `inferred_steps` already
   had to, per that fix's own precedent in this file) — a new
   `SurveySessionNotOwned` exception maps to `403` on both surfaces.
   Optional parameters throughout (`requesting_user_id: Optional[str] =
   None`) so the lower-level `SurveyService`'s existing no-user-context
   test callers (`layer1/tests/test_survey_service.py`) stay unaffected;
   `trips/service.py`'s wrapper methods make `user_id` genuinely
   required, since every real production call site always has one.
   **Verified live, both surfaces:** registered two real users (A, B); A
   started a survey and got a `session_id`; B's `GET`, `POST .../answer`,
   and `POST .../finalize` against A's session each returned `403` with
   `SurveySessionNotOwned`'s message, on both `/trips/survey/{id}` and
   legacy `/survey/{id}`; A's own `GET`/`POST .../answer` against the
   same session continued to return `200` and correctly advanced the
   state machine (`opening_prompt` → `q2_energy`). Full existing test
   suite (`trips/tests/test_trips_survey.py`,
   `layer1/tests/test_survey_service.py`) passes unmodified in spirit —
   the one test file whose calls *would* break under the now-required
   `user_id` (`trips/tests/test_trips_survey.py`, which called
   `TripsService`'s wrapper methods with no user) was updated to pass a
   consistent `test_user_id` throughout, not to skip or weaken the check.

2. **`POST /l3/session/start` let any signed-in tourist mint an arbitrary
   Layer 3 live-guidance session.** This endpoint (`layer3/layer3_api.py`)
   required being signed in but had no ownership check — by necessity, a
   brand-new session has no owning `Trip` row yet, which is exactly what
   every *other* `/l3/*` endpoint uses to enforce ownership
   (`_check_session_ownership_or_403`, added in an earlier pass). That
   left a real gap: any authenticated tourist could call this directly
   with an arbitrary `profile_id`/inline profile that wasn't theirs,
   creating full live-guidance sessions with no `Trip` ever pointing to
   them — and so no ownership check ever applying to them again. The real
   Flutter product never calls this HTTP endpoint at all:
   `trips/routes.py::confirm_trip` starts every real session by calling
   `Layer3Orchestrator.start_session()` **in-process**, then stamps the
   result onto `Trip.layer3_session_id` — which is how every other `/l3/*`
   endpoint can enforce ownership in the first place. Fixed by gating
   `POST /l3/session/start` behind `require_admin` (the same
   `X-Admin-Token`/loopback-only guard this file already used for
   `/l3/safety/advisory`) — internal/service-only, closing it to ordinary
   tourists without touching the real tourist flow, which never reaches
   it. **Verified live:** with `LAYER3_ADMIN_TOKEN` configured, a signed-in
   tourist's call with no admin token (or the wrong one) returns `403
   admin_required`; with the correct token, the call proceeds to its
   normal business logic. (Un-configured — this sandbox's default,
   `ENVIRONMENT=development` — the existing loopback exemption applies,
   same as `/l3/safety/advisory` already had; see the standalone
   `test_api_security_headers_and_admin_guard` test, unmodified, which
   already asserted exactly that loopback behavior for `/l3/safety/advisory`.)

### Fixed — RELEASE BLOCK 2: data integrity (started)

3. **`POST /places/custom` wrote straight into trusted Master Data, with
   no review at all.** A tourist's self-reported place (name, pin
   location, category, a generous default `local_percentage=0.80` bias
   signal) was stored immediately and was from that moment
   indistinguishable from vetted, ETL-collected places — visible to
   *every other tourist* via `GET /places`, `/places/nearby`, and HIVE's
   recommendation pool. Community Submissions (blueprint 3.1's #7
   source) already has a real admin-approval queue for exactly this kind
   of human-submitted data; tourist-added places had no equivalent gate.
   Fixed with a `verification_status` column on `places` (new Alembic
   migration `f3a4b5c6d7e8`; all 708 existing rows default to
   `"verified"` — this does not second-guess already-live Master Data,
   only new tourist-added rows start `"pending"`). `GET /places`
   (`layer0/api/routes.py`) and HIVE's general recommendation candidate
   pool (`layer2/application/hive_engine.py::build_recommendation_queue`)
   both now exclude `"pending"` places. Pinning a place a tourist just
   added into *their own* trip is unaffected — HIVE resolves
   `pinned_place_ids` by id directly out of the unfiltered place list,
   independent of the candidate-pool filter, so "you'll be taken there"
   still holds for the tourist who added it; it just isn't silently
   recommended to anyone else. A new admin surface closes the loop:
   `GET /admin/places/pending` lists them, `POST
   /admin/places/{id}/verify` promotes one to `"verified"` (same
   `X-Admin-Api-Key` gate as every other `/admin/*` route).
   **Deliberately not built this pass:** a reject/delete endpoint — a
   pending place that's never promoted simply never reaches anyone but
   its own tourist, which is a safe default, not a gap; an actual
   moderation UI (vs. these raw JSON endpoints) is frontend work, out of
   scope for this backend pass. **Verified live, full lifecycle:** added
   a custom place as a signed-in tourist (`201`, `verification_status`
   not yet "verified"); confirmed it does **not** appear in `GET /places`
   but direct `GET /places/{id}` still resolves it; confirmed it appears
   in `GET /admin/places/pending`; called `POST
   /admin/places/{id}/verify` (`200`); confirmed it **now** appears in
   `GET /places`. Full test suite (366 tests, including every existing
   `PlaceRepository` fake across `layer0`/`layer2`/`layer5` test files,
   none of which needed changes since `verification_status` defaults to
   `"verified"` on the dataclass) passes.

### Fixed — RELEASE BLOCK 3: production database architecture (started)

4. **Layer 3 silently fell back to a local SQLite file in production.**
   `layer3_config.py::_default_db_url()` returned a `sqlite:///...` path
   whenever `LAYER3_DATABASE_URL` wasn't set — with nothing checking
   which environment it was running in, including a real production
   deployment of the combined app. SQLite means no concurrent-worker
   safety and a session store nothing in production's backup/monitoring
   tooling knows about. Fixed by mirroring the fail-closed pattern
   `main.py` already uses for `CORS_ALLOWED_ORIGINS="*"`: SQLite still
   works exactly as before for `ENVIRONMENT=development` (the default,
   and what Layer 3's own standalone test/dev usage needs with no
   Postgres around); any other `ENVIRONMENT` value without
   `LAYER3_DATABASE_URL` explicitly set now raises `RuntimeError` at
   settings-load time instead of starting with an unannounced SQLite
   fallback. **Verified:** `ENVIRONMENT=production python3 -c
   "...layer3_config.get_settings()..."` with no `LAYER3_DATABASE_URL`
   raises the new `RuntimeError`; `ENVIRONMENT=development` (this
   sandbox's setting) is unaffected — confirmed by a full app restart
   booting cleanly afterward.
5. **Live Events had the same SQLite fallback, plus a real default admin
   key.** `live_events/app/config.py` defaulted `DATABASE_URL` to SQLite
   the same way, and separately defaulted `ADMIN_API_KEY` to the literal
   string `"change-this-before-deployment"` — a real, guessable key that
   would protect `POST /admin/refresh` (`live_events/app/main.py`) in
   name only if ever actually deployed with it. Worse: the module's own
   committed `live_events/.env` (loaded automatically, not an
   `.env.example`-only placeholder) had **both** set to working-but-weak
   values (`EVENTS_DATABASE_URL=sqlite:...`,
   `EVENTS_ADMIN_API_KEY=change-this-local-key`) — meaning a production
   deployment that just shipped this repo's `live_events/.env` as-is
   would have sailed past an "is it set?" check entirely, since it
   genuinely was set, just to something insecure. Fixed in two parts:
   `live_events/app/config.py` now fails closed the same way
   `layer3_config.py` does (`ENVIRONMENT != "development"` and either
   var unset → `RuntimeError` at import time); **and**
   `live_events/.env` had both lines removed (kept in `.env.example` as
   documentation of what a real deployment must set), so local
   development falls through to the Python-level `ENVIRONMENT=development`
   fallback instead of a hand-typed value sitting in a file that would
   otherwise ship unchanged into any deployment. **Verified:**
   `ENVIRONMENT=production python3 -c "...live_events.app.config..."`
   with the `.env` lines removed now raises `RuntimeError` for both;
   `ENVIRONMENT=development` still resolves to the exact same SQLite path
   and a loudly-fake key as before.

### Verification method for this pass

Every item above was checked against the real, running Postgres+Redis+
uvicorn stack (restarted as needed — this sandbox's environment resets
periodically; `pg_isready`/`redis-cli ping`/a `GET /docs` 200 check
precede every round of live testing), not accepted on the review's word
or from reading the code alone. `python3 -m compileall -q .` is clean
across every edited file. The full pytest suite (366 tests) passes,
including four previously-broken tests in
`layer0/tests/test_api_endpoints.py` found and fixed along the way (not
part of either review, but turned up by running the whole suite rather
than only the files touched this pass): `/survey/*` and
`/places/submissions` already required a signed-in user from an earlier
round, but this test file had never been updated to send a bearer
token (401s on every call), and one assertion still expected the survey's
pre-redesign first step name (`"q1_purpose"` instead of the real
`"opening_prompt"`). Both are now fixed rather than left red.

### Deliberately NOT changed this pass, and why

- **The rest of RELEASE BLOCK 2** (real Saved Places persistence, Trip
  state-machine enforcement, idempotency) and **the rest of RELEASE
  BLOCK 3** (Alembic migrations for every remaining table, Master Data
  count verification, real `/health/live` + `/health/ready`) — each is
  its own focused piece of work, not a drive-by addition to this pass.
- **RELEASE BLOCKs 4–9** (real media/object storage, finishing the
  frontend's remaining screens and design-system application, live
  intelligence features — real Talk to Guide, background GPS, TTS,
  behavioral personalization —, full 5-language localization, release
  infrastructure, and device/E2E testing) — unchanged, exactly as scoped
  out of this pass by both reviews' own staging. Specifically out of
  reach from this sandbox regardless of scoping: real Android/iOS device
  testing, app-store release, object storage, production HTTPS/domain
  deployment, legal/privacy policy drafting, and backup/restore drills —
  all require infrastructure or physical devices this environment
  doesn't have.

## Sixth audit response pass (Oct 2026) — Phase A current-code defects from a fresh direct inspection

A sixth review inspected the fifth pass's actual delivered ZIPs (not the
source tree in the abstract) and confirmed the three P0 fixes were
present and not reverted, and that archive hygiene stayed clean. It then
raised 30 new "RELEASE BLOCKER" items, but — consistent with every prior
review's own advice — explicitly scoped its own recommendation down to
"PHASE A — Immediate current-code defects" (7 items) as the only work to
attempt in a pass like this, deferring ownership-model migration,
production database architecture, Flutter release engineering, feature
completion, and full E2E/security testing to a staged program (Phases
B–F). This pass works through Phase A's 7 items one at a time, each
verified against the real source or a live Postgres+Redis+uvicorn stack
before being called fixed — not applied on the review's word alone.

### Investigated and found NOT to be a real bug

- **A1: claimed route-order shadowing of `GET /trips/places/search` by
  `GET /trips/{trip_id}`.** The review's reasoning was that because
  `/{trip_id}` is registered before `/places/search` in `trips/routes.py`,
  and FastAPI/Starlette route matching is order-sensitive, a request to
  `/trips/places/search` could be captured by `/{trip_id}` with
  `trip_id="places"`. This doesn't hold: a plain `{trip_id}` path
  parameter (no `:path` converter) only matches exactly one URL path
  segment with no slashes, and `/trips/places/search` has *two* segments
  after the `/trips` prefix (`places` and `search`) — which a
  single-segment pattern structurally cannot match, regardless of
  registration order. Verified live: `GET /trips/places/search?query=temple`
  with a valid bearer token returns `200` with real place-search results
  from the Master Data Core, not the 404 the shadowing theory would
  predict. As a control, `GET /trips/some-garbage-id` (a genuinely
  single-segment path) correctly reaches `/{trip_id}` and 404s with
  "badly formed hexadecimal UUID string" — confirming `/{trip_id}` *is*
  live and reachable, which rules out the possibility that routing was
  broken some other way that happened to mask the claimed bug. No code
  change made for A1 — reordering the routes would have been harmless
  but pointless, and applying an unverified fix for a non-bug isn't
  something this pass does.

### Fixed

1. **A2: the Flutter survey flow never sent its auth token.**
   `TripsApiClient.startSurvey()` and `.answerSurvey()`
   (`lib/core/trips_api_client.dart`) took no `token` parameter at all —
   only `.finalizeSurvey()` did — despite the backend's own third-pass
   fix requiring authentication on `POST /trips/survey/start`,
   `GET /trips/survey/{session_id}`, and `POST /trips/survey/{session_id}/answer`.
   Verified live before fixing: `POST /trips/survey/start` with no
   Authorization header returns `401`. Fixed by threading a required
   `token` parameter through both methods into the `Authorization: Bearer`
   header (same pattern `.finalizeSurvey()` already used), and updating
   `SurveyScreen`'s two call sites (`lib/screens/new_trip/survey_screen.dart`)
   to read `widget.auth.accessToken` and guard with the same "you need to
   be signed in" message `_finalizeAndGenerate()` already had. Verified
   live end-to-end afterward: registered a test user, drove the full
   9-step survey through `/trips/survey/start` → `/answer` (×9) →
   `/finalize` → `/trips/generate` with the token attached throughout,
   and got back a real generated trip.
2. **A4: journal entries could attach a `trip_place_id` from a different
   trip.** `TripsService.add_journal_entry` (`trips/service.py`) never
   checked that the `trip_place_id` it was given actually belonged to
   the trip it was being added to — unlike `arrive`, `checkout`, and
   `skip_place`, which all call the existing `_require_place(trip,
   trip_place_id)` membership check first. The route already confirms
   the *trip itself* is owned by the caller, but nothing stopped a
   caller from passing any `trip_place_id` — including one belonging to
   a completely different trip — and having it linked into their own
   journal entry (an IDOR via foreign-key insertion). Fixed by calling
   `_require_place` in `add_journal_entry` when a `trip_place_id` is
   given, and wrapping the route's call in `except LookupError: 404`
   (`trips/routes.py`), matching the existing pattern. Verified live: a
   journal entry with a `trip_place_id` that's a real UUID but not a
   member of that trip now 404s with "Place not in this trip"; a
   journal entry with a `trip_place_id` that genuinely belongs to the
   trip still succeeds (`200`); a journal entry with no `trip_place_id`
   at all (the field is optional) still succeeds (`200`) — no
   regression on the common case.
3. **A5: resuming a trip with `upgrade: true` dropped every new place's
   coordinates.** The regenerate-on-resume path in
   `POST /trips/{trip_id}/resume` (`trips/routes.py`) builds a fresh
   `TripPlace` row per regenerated item the same way
   `TripsService.generate_trip` does — except it never looked the place
   up to set `latitude`/`longitude`, unlike `generate_trip`'s otherwise
   near-identical loop. Every `TripPlace` created by a resume-and-upgrade
   had `NULL` coordinates, breaking the map and arrival geofencing for
   the rest of that trip. Fixed by adding the same
   `place_repository.get_by_id(item.place_id)` lookup `generate_trip`
   already does, and setting `latitude`/`longitude` from
   `place.coordinates`. Verified live: generated a real trip, confirmed
   it, called `/resume` with `upgrade: true` and a real lat/long — all 8
   newly regenerated pending places came back with real, non-null
   coordinates (checked explicitly: 0 of 8 missing lat/long, versus what
   would have been 8 of 8 before this fix).
4. **A6: "Schedule for later" led to a dead end.** Choosing it set
   `trip.status = "scheduled"` and stored `scheduled_start_at`
   (`trips/service.py`'s `confirm_trip`), but nothing in the backend
   ever promotes a scheduled trip to `"active"` at that time — confirmed
   by reading every scheduler job registered in `main.py` (only the
   events-cache refresh job exists) and every `trip.status = "active"`
   assignment in `trips/service.py` (only `confirm`'s start-now branch
   and `resume_trip`, neither of which anything calls automatically for
   a trip sitting in `"scheduled"`). A tourist who picked that option
   would have their trip sit there permanently with no way to actually
   start it from the app. Rather than ship a control that leads nowhere,
   `ItineraryScreen`'s confirm dialog (`lib/screens/new_trip/itinerary_screen.dart`)
   now always confirms with `startNow: true` and says so plainly, until
   a real activation mechanism exists — a scheduler job, or a "start
   this trip now" action on a scheduled trip, neither of which exists
   yet. That real mechanism is a feature to build, not a bug to patch
   here, so it's listed under Deliberately NOT changed below, not
   invented on the spot.
5. **A7: hardcoded pre-2022 emergency numbers in the Layer 5 chatbot.**
   `layer5/chatbot.py`'s `ChatIntent.EMERGENCY` replies quoted the old
   separate Police (100) / Ambulance (102) / Fire (101) numbers.
   `layer3/layer3_i18n.py`'s `safety_sos` strings already correctly use
   India's unified pan-India emergency number, 112, in all four
   supported languages (English, Hindi, Kannada, Konkani) — this was the
   one place left behind. Updated both chatbot reply variants to point
   to 112 instead.

### Verified live, this pass

Restarted the full stack (`service postgresql start`,
`redis-server --daemonize yes`, fresh `uvicorn main:app`) and confirmed
healthy (`pg_isready`, `redis-cli ping`, `GET /docs` → 200) before any
test. Registered a real test user and drove the entire New Trip flow —
survey start through all 9 answers, finalize, generate — with the token
attached as A2's fix requires, producing a real generated trip against
the live Postgres-backed place catalog (OSRM routing unavailable in this
sandbox, as in every prior pass; `routing_service.py`'s existing
circuity-adjusted haversine fallback handled it, exactly as designed).
Confirmed and then resumed that trip with `upgrade: true` to exercise
A5's exact code path, and inspected every regenerated place's
`latitude`/`longitude` directly in the response. Exercised A4's fix with
three journal-entry calls against that same trip: a valid own
`trip_place_id` (succeeds), a `trip_place_id` that's a real UUID but not
a member of the trip (404s), and no `trip_place_id` at all (still
succeeds, confirming the optional-field case wasn't broken by the new
check). Re-ran `python3 -m compileall -q .` across the full backend tree
— clean. The Flutter changes (A2, A6) were checked by hand — brace/paren
balance confirmed, both `TripsApiClient` call sites updated, no leftover
references to the removed scheduling controls — since no Dart/Flutter
SDK is available in this sandbox to run `flutter analyze`, the same
limitation as every prior pass.

### Deliberately NOT changed, and why

- **A3, regression tests for A2/A4/A5.** `trips/tests/test_trips_survey.py`
  already states this project's own testing boundary explicitly: pure
  logic (slider-to-enum mapping, survey auto-fill) gets unit tests with
  no database; itinerary generation and live-trip endpoints need a real
  Postgres-backed place catalog and are "exercised manually against a
  running stack instead." A4's and A5's fixes are exactly that
  category — DB-session-dependent trip/place logic — so adding unit
  tests for them here would mean inventing a new testing pattern this
  codebase doesn't otherwise use, rather than extending its existing
  one. They were instead verified live, in detail, as described above.
  A real DB-backed integration test suite for `trips/` is a reasonable
  thing to build, but it's a standalone piece of work, not a drive-by
  addition to a bug-fix pass.
- **A6's real fix — an actual way to start a scheduled trip.** Disabling
  the dead-end control (done, above) is a safety fix. Building the
  actual feature — a scheduler job that promotes `"scheduled"` trips to
  `"active"` at `scheduled_start_at`, or a manual "start now" action
  exposed on a scheduled trip in My Trips — is new functionality with
  its own design questions (what happens if the tourist isn't at the
  origin point when the scheduled time arrives? does it need a push
  notification?) that belong in the staged roadmap the fifth and sixth
  reviews both call for, not decided unilaterally inside this pass.
- **Phases B–F of the sixth review** (ownership-model/`user_id` FK
  migration, production database architecture, Flutter release
  engineering and platform scaffolding, feature completion, full
  E2E/security testing) — unchanged, per the review's own explicit
  staging and every prior pass's same reasoning: these are multi-day/
  multi-week efforts, not bug fixes, and attempting pieces of them
  inside a pass like this is what every review so far has warned
  against.

## Fifth audit response pass (Oct 2026) — the three concrete P0 bugs from a production-readiness review

A fifth review was a full production-readiness assessment (97 sections)
rather than another endpoint-by-endpoint audit. Its own conclusion was
explicit: GroundZero is "a strong hardened development baseline with
several known production-readiness gaps," the architecture should not
be rewritten, and the right move is "not another loosely modified ZIP"
but a deliberate, staged hardening program — starting with only the
concrete P0 security/correctness bugs, not all ~30 items at once. This
pass follows that advice literally: it fixes the three P0 items that
are genuine, narrowly-scoped code defects with an exact described fix,
verifies each live, and leaves the much larger architectural program
(a real `user_id` FK + Trip-as-source-of-truth migration, SurveySession
ownership, the full feature-completion/infrastructure/testing phases)
as the explicit next program, not attempted piecemeal here — doing
pieces of a multi-week migration inside a bug-fix pass is exactly what
the review itself warned against.

### Fixed

1. **P0-1: `GET /layer4/session/{session_id}` was fail-OPEN, not
   fail-closed.** The fourth pass added an ownership check
   (`if owner_id is not None and owner_id != user.id: reject`) but
   never handled the case where `owner_id` is `None` — a `session_id`
   with no matching `Trip` row at all fell through to "allowed" instead
   of being rejected. Unlike `tourist_profiles` ownership (where a
   `None` owner can legitimately mean "predates the ownership log" —
   see the third pass's notes), every real Layer 4 `session_id` is
   created by `/trips/{id}/confirm` in the same transaction that sets
   `Trip.layer3_session_id`, so a `session_id` with no owning `Trip` is
   never a legitimate case — it's a typo or a guess, and should 404.
   Fixed: `owner_id is None` now raises 404 before the 403 check even
   runs (`layer4/api.py`). Verified live: a garbage `session_id` now
   404s instead of reaching the orchestrator.
2. **P0-2: `/l3/place/report-unavailable` let the client assert its own
   reporting identity.** `UnavailableBody.reported_by` was a plain
   client-supplied string written into the report record as-is — an
   authenticated caller could claim to be reporting on behalf of
   anyone. Removed `reported_by` from the request body entirely;
   `report_unavailable()` now always uses `str(user.id)` from the
   verified bearer token (`layer3/layer3_api.py`). Verified live: sent
   a request with `"reported_by": "someone-else-id"` in the body,
   queried the real `l3_place_flags` row it wrote, and confirmed the
   stored `reported_by` is the actual signed-in user's own id, not the
   value the client tried to inject.
3. **P0-3: `/l3/visits/{device_id}` had no real ownership model** —
   `device_id` isn't linked to a user anywhere in the schema, so the
   existing auth check only proved *someone* was signed in, not that
   they owned that device's data. Added the trip-owned alternative the
   review asked for: `GET /trips/{trip_id}/visits`
   (`trips/routes.py`), using the same already-verified
   `_get_owned_trip` ownership check every other `/trips/*` route uses,
   then resolving visits via `Trip.layer3_session_id` — the real Layer
   3 session link `/trips/{id}/confirm` already establishes — instead
   of a client-supplied device_id. This needed one small addition to
   the orchestrator (`Layer3Orchestrator.visits_for_session`, a thin
   wrapper around a repository method — `layer3_repository.py`'s
   `visits_for_session` — that already existed but had no caller). The
   old `/l3/visits/{device_id}` endpoint is left in place, still
   signed-in-required, for a caller that genuinely only has a
   device_id and no trip context; the new one is what the normal
   product flow should use. Verified live: 401 anonymous, 404 for a
   nonexistent/unowned trip via the same ownership path already proven
   for every other `/trips/*` route.

### Verified live, this pass

Registered a real user; confirmed `GET /layer4/session/{garbage-id}`
now 404s instead of passing through. Submitted a real
`/l3/place/report-unavailable` call with a forged `reported_by` in the
body and queried the actual SQLite row it wrote
(`layer3/data_output/layer3.db`'s `l3_place_flags` table) to confirm
the stored value is the real authenticated user's id, not the forged
one — this is the strongest form of verification available short of
a second malicious client, since it inspects what actually landed in
storage rather than trusting the response. Confirmed the new
`GET /trips/{trip_id}/visits` 401s anonymously and 404s for a
nonexistent trip through the same ownership path already live-verified
for `/trips/{id}/story` and the rest of `/trips/*`. Ran
`python3 -m compileall` across the full tree after every edit: no
syntax errors. Checked the Flutter app for any existing call site
depending on `reported_by` in the report-unavailable request: none
exists, so removing it from the schema breaks nothing live.

### Deliberately NOT changed, and why

The review's other ~25 "fix before production" items are a genuine,
well-reasoned staged production-readiness program, not bugs with a
one-file fix — and the review's own final recommendation is to treat
them as such rather than squeeze them into "another ZIP." Restated
here rather than dropped:

- **`tourist_profiles.user_id` FK, `SurveySession.user_id`/`trip_id`
  (plus binding Redis survey state to it), and making `Trip` the
  actual source-of-truth object every other table hangs off.** The
  review is right that the current `TripEvent`-log-based ownership
  check is a real, if currently paper-thin, piece of technical debt —
  and it correctly says this needs a careful, tested, backed-up
  migration sequence (nullable column → backfill → quarantine
  unowned rows → `NOT NULL` → drop the old check), run against a real
  staging environment, not a patch applied inside the same pass as
  three unrelated route fixes.
- **Real persistence for Saved Places, Journal, Notifications, Media
  (object storage), and the remaining 4 Flutter contribution screens
  ("coming soon" buttons)** — all correctly flagged as "don't ship a
  visible button that doesn't work," all substantial net-new features,
  unchanged since the third/fourth passes' notes.
- **Trip and TripPlace state machines, secure Flutter token storage,
  centralized API/401 handling, rate limiting (especially on
  auth/contribution/AI-backed endpoints), a real Talk-to-Guide rebuilt
  on the Layer 3 Ask Engine, real voice, Flutter `android/`/`ios/`
  platform scaffolding, environment separation (dev/staging/prod),
  HTTPS, CORS lockdown, observability/monitoring, backup/restore
  testing, and a formal cross-user authorization test suite.** All
  correctly identified as real production-readiness gaps. None of
  these are "bugs" in the sense the three P0 items above are — they're
  the staged program the review itself lays out (its own Phase 1
  through Phase 8), and attempting fragments of infrastructure,
  mobile-release, and database-migration work inside an afternoon's
  bug-fix pass is the "patch-on-patch" pattern the review explicitly
  warns against, not a shortcut to it.

## Fourth audit response pass (Oct 2026) — the authorization gaps the third pass missed, plus two real crash bugs

A fourth audit re-inspected the actual zip contents (confirmed: no
`.db` files, no shipped `.env`, no `frontend/`, `compileall` clean, the
third pass's auth changes genuinely present) and found several more
real defects the third audit missed, alongside a long list of
architecture-level product work correctly identified as still
incomplete. This pass fixed every concrete, verifiable defect from that
audit — new unauthenticated endpoints and two real runtime crash bugs —
and is explicit about the large architectural items (real `user_id` FK
on `tourist_profiles`, full survey-session ownership, trip/place state
machines, a real media pipeline, the remaining 4 Flutter contribution
screens, secure token storage, a Talk-to-Guide rebuild, voice, Flutter
platform scaffolding, localization, and more) that are correctly named
as real gaps but are deliberate, documented roadmap items, not fixed in
this pass — see "Deliberately NOT changed" below. All of what follows
was checked against a real, running Postgres + Redis + `uvicorn main:app`
stack (DB persists across sandbox restarts in this environment, so the
same users/profiles/trips from earlier passes were still there to test
against).

### Fixed

1. **`/hive/itinerary/{profile_id}/save`, `/confirm`, and `GET` were
   fully unauthenticated** (`layer2/api/feedback_routes.py`) — a
   separate file from `layer2/api/routes.py`, which is presumably why
   the third pass's otherwise-thorough `/hive/*` fix missed it. Same
   bug class as `/hive/recommendations` before the third pass: anyone
   who knew a `profile_id` could read, overwrite, or confirm that
   itinerary. All three now require a signed-in user and the same
   `shared/ownership.py` profile check every other `/hive/*` and
   `/trips/*` route already uses. Verified live: 401 anonymous, 403 for
   a non-owner, 200 for the owner.
2. **`POST /hive/generate` was fully unauthenticated**
   (`integration/layer2_layer3_bridge.py`). This one is architecturally
   different from the others: it's not called by the Flutter app at
   all — it exists only so Layer 3's own internal bridge
   (`layer3/layer3_bridge.py`'s `Layer2Client`) can ask Layer 2 for a
   recommendation queue server-to-server, with no tourist's bearer
   token in the picture to check ownership against. A per-user
   ownership check is the wrong tool for an endpoint with no end-user
   behind the call. Fixed the way `/admin/*` already is: gated behind
   the same fail-closed shared-secret `X-Admin-Api-Key` header
   (`layer0/api/security.py::require_admin_api_key`, reused as-is, not
   duplicated), and `Layer2Client.generate()` now sends that header.
   Verified live: no key → 401, wrong key → 403, correct key → reaches
   the real logic (404 for a nonexistent profile, not an auth error).
3. **`GET /layer4/session/{session_id}` was fully unauthenticated**
   (`layer4/api.py`) and returned real personal trip data (status,
   current slot, wallet remaining, queue). Layer 4's `session_id` is
   the same id as the Layer 3 session it supervises, so it's checked
   the same way Layer 3's own session endpoints already are —
   `Trip.layer3_session_id` resolves the real owner. Verified live:
   401 anonymous; a non-owner's 403 and the owner's success follow the
   same pattern already verified for `/l3/*` in the third pass.
4. **Real crash bug: `GET /personal/notifications` could 500 once a
   user had any of the four newer contribution kinds.**
   (`personal/service.py::notifications`). `suggest_update`,
   `local_tip`, `report_incorrect`, and `add_media` are logged with
   `submission_id=None` by design (only `add_place` goes through the
   layer0 `CommunitySubmission` pipeline — see `personal/service.py`'s
   own `submit_contribution`), but this method unconditionally did
   `submission_repo.get_by_id(r.submission_id)` for every recent
   contribution. `get_by_id` does `uuid.UUID(submission_id)` internally,
   and `uuid.UUID(None)` raises `TypeError` — confirmed directly,
   not assumed. Fixed by only looking up a submission when
   `r.kind == "add_place" and r.submission_id`; the other four kinds
   have no review step to notify about yet (honest, matches
   `README_PERSONAL.md`), so they're skipped rather than faking a
   notification. Verified live end-to-end: registered a fresh user,
   submitted a real `local-tip` (confirmed its `submission_id` comes
   back `null`), then called `/personal/notifications` and got a clean
   `200` with the old code path's exact crash trigger present — this is
   the real scenario, not a synthetic one.
5. **Real crash bug (frontend): `GZContribution.fromJson` would throw a
   type-cast error on exactly the same four contribution kinds.**
   (`/home/claude/gz/lib/core/personal_api_client.dart`). The backend's
   `ContributionOut.submission_id` is `null` for those four kinds (both
   before and after this pass — that's the correct, documented
   behavior), but the Dart model declared `submissionId` as a
   non-nullable `String` and cast with `as String`, which throws on
   `null` rather than producing a usable value. Made `submissionId` and
   `placeId` nullable (`String?`) and added the `kind` field so the UI
   can branch on the actual contribution kind instead of inferring it
   from whether `submissionId` happens to be present. Checked for other
   call sites reading `.submissionId` elsewhere in the Flutter app:
   none exist yet (the four kinds' screens are still "coming soon" —
   see item 10 of the third pass's deferred list, unchanged), so this
   is a model-correctness fix ahead of that screen work, not a UI
   change by itself.

### Verified live, this pass

Confirmed 401 anonymous on all three `/hive/itinerary/*` routes,
`/hive/generate`, and `/layer4/session/{id}`. Confirmed `/hive/generate`
specifically: 401 with no admin key, 403 with a wrong key, and a real
404-not-auth-error response with the correct key — proving the gate
works without breaking the endpoint's actual logic. Confirmed a
non-owner gets 403 on `/hive/itinerary/{id}` for another user's real
profile. Reproduced the notifications crash scenario for real: created
a user, submitted a real `local_tip` contribution (confirmed
`submission_id: null` in the response), then called
`/personal/notifications` and got `200` instead of the `TypeError` the
old code would hit (confirmed `uuid.UUID(None)` raises `TypeError`
directly, isolated from the rest of the app, to be sure the claim is
real). Ran `python3 -m compileall` across the full tree after every
edit: no syntax errors.

### Deliberately NOT changed, and why

This audit raised 28 "fix before final" items; the five above are the
ones that are genuine, narrowly-scoped defects (an auth gap on a
specific route, or a crash bug with a reproducible trigger). The rest
are correctly-identified product/architecture work, most already on
the third pass's roadmap, restated here rather than silently dropped:

- **`tourist_profiles.user_id` FK, and binding `user_id` into survey
  sessions (Redis and in-memory) instead of the current
  `TripEvent`-log ownership check.** The audit is right that the
  current `shared/ownership.py` approach has a real edge case (no
  ownership record = not restricted) and that a real FK is the correct
  permanent fix. This is schema-migration-plus-backfill work on a real
  database, not a route-level patch — attempting it inside the same
  pass as five other fixes, without a dedicated backfill/verification
  cycle, is how data gets corrupted. Left as the clear next dedicated
  task, with the audit's own phased migration plan (nullable column →
  backfill from `trip_events` → quarantine unowned profiles → `NOT
  NULL` → drop the `TripEvent` workaround) as the right shape for it.
- **Trip and TripPlace state machines, `/l3/visits/{device_id}` and
  `/l3/place/report-unavailable`'s missing ownership models, per-trip
  (not just per-user) geofencing, idempotency keys on contribution/
  media/journal submissions.** Real gaps, all already structural work
  rather than fixes, unchanged this pass.
- **Real media pipeline, real Explore "Save"/"Go There", the
  remaining 4 Flutter contribution screens, contribution moderation
  workflow, points ledger, data export, persistent notification
  preferences, personal-place vs. trusted-master-data separation for
  custom places, secure token storage, Talk-to-Guide rebuilt on the
  Layer 3 Ask Engine, real voice (Flutter TTS/STT instead of the
  server-side placeholder), full Flutter platform scaffolding
  (`android/`/`ios/`/`web/` — this is still a Flutter source tree, not
  a built app), centralized Flutter API/401 handling, and full
  localization.** All correctly identified, all substantial net-new
  subsystems rather than bug fixes, all already named on the third
  pass's roadmap or the audit's own phased plan. Not attempted here —
  doing any one of them properly is its own focused pass, and doing
  several badly in one pass is how "hardening" turns into more surface
  area to re-audit.

## Third audit response pass (Oct 2026) — closing every authorization gap

Carol forwarded a third, far more detailed audit (72 numbered findings,
🔴/🟠/🟡/🟢 severity, with a 14-phase recommended fix order) that found
the previous pass's fixes were real but incomplete — most critically,
several entire API surfaces were still fully unauthenticated. This pass
went through that audit's Phase 0 (zip purge) and Phase 1 (close every
listed authorization gap) in full, verified everything against a real
running Postgres + Redis + `uvicorn main:app` stack, and is explicit
about the larger architectural items (Phases 2-14) that are correctly
identified as real gaps but are not attempted here — see "Deliberately
NOT changed" below.

### Fixed

1. **Zip purge (Phase 0).** The previous backend zip shipped
   `layer3/data_output/layer3.db` (+ `.db-wal`/`.db-shm`) and
   `live_events/data_output/groundzero_events.db` — real SQLite files
   containing actual survey/session data from live-verifying earlier
   passes, a genuine privacy leak. It also still bundled the obsolete
   React Native/Expo frontend (`backend/integrated_v2/frontend/`), long
   superseded by the Flutter app. This zip excludes all `*.db`,
   `*.db-wal`, `*.db-shm`, `*.db-journal` files and the entire
   `frontend/` subtree, confirmed by listing the built zip's contents
   and checking the counts are zero.
2. **`POST /places/{place_id}/mark-visited` was fully public.** Now
   requires `auth.dependencies.get_current_user`
   (`layer0/api/routes.py`). (`record_visit()` itself is still a
   Phase-1 existence-check stub with no real per-user write — see its
   own docstring — so this was a public-surface fix, not a data-leak
   fix, but the endpoint's name and docs implied otherwise.)
3. **The entire legacy `/survey/*` API (Layer 1) was unauthenticated**,
   including `/survey/profile/{id}/visited` (read/write someone's
   personal travel history) and `/survey/group/{id}/members`. All five
   routes (`start`, `GET {id}`, `{id}/answer`, `{id}/finalize`,
   `group/{id}/members`) now require a signed-in user
   (`layer1/api/routes.py`). The two profile-specific endpoints
   (`mark_places_visited`, `get_visited_places`) now also enforce
   ownership via the same `shared/ownership.py` check `/trips/generate`
   already used — a non-owning user gets 403.
4. **The new `/trips/survey/*` flow only checked ownership/auth at
   `finalize`, not at `start`/`answer`/`get state`** — a guessable
   `session_id` let anyone read or advance someone else's in-progress
   survey. All three now also require a signed-in user
   (`trips/routes.py`). (No ownership check was added to these three
   specifically, because there is nothing to own yet — the survey
   session isn't linked to anyone until `/finalize` creates the
   `TouristProfile` + the `survey_completed` `TripEvent`. That link is
   what every later ownership check is actually built on.)
5. **`/hive/recommendations` and `/hive/recommendations/multi-day` were
   fully public** and accepted an arbitrary `profile_id`. Both now
   require a signed-in user and the same profile-ownership check as
   `/trips/generate` (`layer2/api/routes.py`). Verified live: a second
   user gets 403 calling either endpoint with the first user's real
   `profile_id`; the owner succeeds.
6. **All 13 `/l3/*` endpoints were essentially unauthenticated** —
   session start/get/queue/state, location ping, context evaluate,
   notify dismiss/engage/tell-more, ask, quiet, sos, sos/clear, visit,
   visits/{device_id}, place/report-unavailable. Every one now requires
   a signed-in user. The ones that take a `session_id` (`get`, `queue`,
   `state`, `location/ping`, `context/evaluate`, the three `notify/*`,
   `quiet`, `sos`, `sos/clear`, `visit`) also check that the session
   belongs to the caller, resolved through `Trip.layer3_session_id` —
   the real linkage `/trips/{id}/confirm` already sets when it starts a
   Layer 3 session in-process. `sos` gets the exact same check as every
   other session-scoped endpoint (the audit's concern was the missing
   *authentication*, not a request to bypass ownership for safety
   calls). `session/start` takes no ownership check (there's no owner
   yet — it's a new session) and `visits/{device_id}` /
   `report-unavailable` get authentication only, since neither has a
   device- or report-ownership model to check against yet (tracked as
   a residual gap below). Layer 3 can still run standalone
   (`run_layer3.py --serve`, outside the combined app, with no `auth`
   package on its `sys.path`) — handled with a defensive import that
   falls back to a clear log warning instead of crashing; verified both
   import modes actually work, not just reasoned about.
7. **`/companion/geofences/load` and `/companion/geofences/gps` used one
   process-wide `GeofencingEngine()` shared by every signed-in user** —
   not an auth gap the audit asked for by name, but a real multi-user
   correctness bug found while fixing the auth gap on these two routes:
   User A loading their itinerary's geofences and User B sending a GPS
   ping would evaluate B's position against A's active fences and
   mutate the same shared state. Fixed by keying a `dict` of engines by
   `user.id` instead of one shared instance (`layer5/api/dependencies.py`).
   Both routes now also require a signed-in user. Verified live: two
   different users loading geofences and pinging GPS get fully
   independent engine state — a ping from an unrelated location
   produces zero events instead of stale cross-user fence state.
8. **A malformed/tampered bearer token could 500 instead of 401.**
   `auth/dependencies.py::get_current_user`'s `uuid.UUID(user_id)` call
   on a token whose `sub` claim isn't a real UUID previously raised
   unhandled. Now wrapped and returns the normal 401. The same bug
   existed independently in `auth/routes.py`'s `/me` and
   `DELETE /me` handlers (see next item) and is fixed there too.
9. **Auth logic was duplicated between `auth/routes.py` and
   `auth/dependencies.py`.** `/auth/me` re-implemented bearer-token
   parsing inline instead of depending on the one canonical
   `get_current_user` every other router already uses — a second copy
   that could silently drift (and had already drifted: it was missing
   the malformed-token fix above until this pass). `/me` now depends on
   `get_current_user` via a small lazy-import wrapper (avoids a circular
   import, since `auth.dependencies` itself imports `get_db` from
   `auth.routes`) — verified the import graph actually resolves at
   runtime, not just assumed.
10. **`personal/schemas.py`'s `AddPlaceIn.price_band` was a bare `str`**
    (so `"Budget"` or a typo would pass validation and then not match
    anything downstream). Now the same `Literal["free","budget",
    "moderate","premium"]` pattern already used in
    `layer0/api/schemas.py` / `trips/schemas.py`.

### Verified live, this pass (real Postgres + real Redis + real `uvicorn main:app`, no mocks)

Confirmed 401 with no token on all of: `mark-visited`, legacy
`/survey/start`, `/trips/survey/start`, `/hive/recommendations` (both),
`/l3/session/start`, `/companion/geofences/load` and `/gps`, legacy
`/survey/profile/{id}/visited` (GET and POST), `/survey/group/{id}/members`.
Confirmed a malformed bearer token 401s instead of 500 on `/auth/me`.
Registered two real users; ran a complete real 9-step `/trips/survey/*`
flow end to end and finalized it into a real `TouristProfile`; confirmed
the second user gets 403 from both `/hive/recommendations` endpoints
using the first user's real `profile_id`, and the real owner is let
through; confirmed the second user gets 403 reading the first user's
legacy visited-places record, and the owner can read their own; loaded
geofences and sent GPS pings as both users and confirmed fully isolated
engine state. Directly exercised the new Layer 3 session-ownership
helper (`_session_owner_user_id` / `_check_session_ownership_or_403`)
against two real `Trip` rows already in the database from earlier
passes — confirmed it correctly resolves the real owner from
`Trip.layer3_session_id`, lets that owner through silently, and raises a
403 `LayerError` for a different user. (The full HTTP-level `/l3/*`
round-trip for a brand-new session could not be exercised end-to-end in
this sandbox within a reasonable time — this sandbox's egress proxy
blocks `router.project-osrm.org` outright, and the HIVE itinerary engine
retries OSRM 3 times per leg before falling back to haversine, which
turns a normal recommendation call into a multi-minute one here. This is
a sandbox network-policy artifact, not a code defect; the ownership logic
itself was verified directly against real data instead, per above.)
Ran `python3 -m compileall` across the full tree after all edits: no
syntax errors. Rebuilt and inspected the zip directly: confirmed zero
`.db`/`.db-wal`/`.db-shm` and zero `frontend/` or `.env` entries.

### Deliberately NOT changed, and why

This audit's own recommendation was "a deliberate Hardening + Completion
Pass," not another patch. Phase 0 and Phase 1 (above) are that pass's
authorization-and-privacy slice, done in full. The following are real,
correctly-identified gaps from the same audit that are architecture-level
work, not fixes, and are left as an explicit roadmap rather than
half-done in this pass:

- **No real `user_id` FK on `tourist_profiles`.** The ownership checks
  added in this pass and the previous one (`shared/ownership.py`,
  built on the `survey_completed` `TripEvent` log) are a correct and
  verified stopgap, not a substitute for a real foreign key. Until that
  column exists, account deletion also can't cascade-clean
  `tourist_profiles`, and any profile never run through the new
  `/trips/survey/*` flow has no recorded owner at all (an unset owner is
  treated as "not restricted," matching the trust boundary that existed
  before any of these checks did).
- **Trip state machine still accepts invalid status/place-status
  transitions** — no enforcement that, e.g., a trip can't be checked
  out of before it's arrived.
- **No real media pipeline.** `add_media` is metadata logging, Journal
  photo upload still sends a raw local `file.path` as `media_url` — both
  already flagged as the top item for the next pass in the previous
  round's notes, unchanged here.
- **Flutter only wires 1 of the 5 contribution actions** the backend now
  supports (`contributions_screen.dart` still shows "coming soon" for 4
  of them) — a frontend task, not touched in this backend-focused pass.
- **Bearer token still in `SharedPreferences`, not
  `flutter_secure_storage`** — frontend, not touched this pass.
- **No moderation-queue states, reputation ledger, data export, rate
  limiting on auth endpoints, or password policy beyond length** — all
  correctly flagged, all genuinely new subsystems, not fixes.
- **"Talk to Guide" is a keyword-based chatbot, not the claimed
  grounded Ask-Engine/HIVE/weather/tide intelligence, and voice TTS /
  speech recognition are explicit backend placeholders** returning fake
  `file:///audio/...` URLs. Both correctly reclassified by the audit as
  architecturally stubbed, not "missing frontend only" — a real rebuild,
  not attempted here.
- **`/l3/visits/{device_id}` and `/l3/place/report-unavailable`** got
  authentication in this pass but not an ownership check — there's no
  device- or report-ownership model yet to check against. Noted as a
  residual gap, not silently closed.
- **Localization completeness, Explore map/photography, behavioral
  personalization** — unchanged, as previously documented.

## Audit response pass (Oct 2026) — security, data-integrity, and contributions follow-up

Carol forwarded two external AI-generated audits of the chunk-4 delivery.
This pass went through both line by line, verified each claim against
the real code and a real running backend/Postgres/Redis stack (not
assumed), fixed what was genuinely broken, and explicitly documents what
was deliberately left alone and why. Nothing below is described as done
unless it was actually run against a live server in this sandbox.

### Fixed

1. **Exposed secrets in the shipped zip (critical).** The previous
   `GroundZero_Backend_FINAL.zip` included the real `backend/integrated_v2/.env`,
   `frontend/.env`, and `live_events/.env` files. This zip excludes all
   three — only the blanked `.env.example` templates are included. The two
   secrets this backend controls directly (`AUTH_SECRET_KEY`,
   `ADMIN_API_KEY`) have been rotated in this sandbox's own `.env`.
   **Carol still needs to, herself, outside this sandbox**: rotate the
   `OPENWEATHERMAP_API_KEY` and `TIDE_API_KEY` values at their respective
   providers (openweathermap.org, worldtides.info) — this agent has no
   access to those accounts — and change the Postgres password if that
   database is reachable from anywhere beyond this sandbox.
2. **`POST /places/custom` and `POST /places/submissions` were
   unauthenticated.** Both write into the shared Master Data Core
   immediately (by design — see `custom_place_service.py`'s docstring for
   why `/custom` skips the moderation queue). An anonymous caller could
   previously inject arbitrary places into trusted data. Both routes now
   require `auth.dependencies.get_current_user` (`layer0/api/routes.py`).
   Verified live: both return 401 with no token, 201 with one.
3. **Trip survey session state silently broke once Redis actually backed
   it.** Found while verifying the fixes above against a real Redis
   instance, not mentioned in either audit: `RedisSurveySessionStore`
   (`layer1/infrastructure/survey_session_store.py`) never serialized
   `inferred_steps`, so every session round-trip through real Redis reset
   it to empty. That broke the skip-logic for steps the opening-prompt
   sentence already answered by inference (`q7_curiosity_text` in
   particular), and the survey state machine would walk onto that step as
   a real "current step" — one with no UI name and no auto-fill — and
   silently report `next_step: null` while `done: false`, stalling the
   survey forever. The in-memory fallback store masks this completely,
   which is why it went unnoticed. Fixed by serializing/restoring
   `inferred_steps`. Verified live end-to-end: a real 9-question survey
   now completes and finalizes correctly with Redis actually running.
4. **Negative `amount_spent` could inflate `budget_remaining`.**
   `trips/schemas.py`'s `CheckoutIn.amount_spent` now has `ge=0`.
5. **No bounds on latitude/longitude/cost/price_band anywhere a tourist
   supplies them.** Added `Field(ge=-90, le=90)` / `Field(ge=-180, le=180)`
   / `Field(ge=0)` to `GenerateItineraryIn`, `AddPlaceIn` (both the trips
   and personal module versions), `ResumeDecisionIn`, `CustomPlaceIn`, and
   `CommunitySubmissionIn`; `price_band` is now a `Literal` matching
   `PriceBand`'s real values instead of a bare `str`. Verified live: all
   of these now 422 cleanly on bad input instead of either succeeding
   silently or raising a 500 deep in domain code.
6. **Tourist-added profile ownership wasn't enforced.** `tourist_profiles`
   has no `user_id` column (layer1 has its own standalone domain model not
   aware of `auth`), so nothing stopped one signed-in user from generating
   a trip off another user's `profile_id` if they obtained it. Rather than
   add a `user_id` column to `tourist_profiles` — risky, since layer1 also
   runs as its own standalone app with its own domain entities — this pass
   added `TripsService._enforce_profile_ownership()`, which checks the
   `survey_completed` `TripEvent` already logged by `finalize_survey()`
   (it already records both `user_id` and `profile_id`) and raises a 403
   if they don't match. Verified live: a second user generating a trip
   from the first user's `profile_id` now gets 403; the normal flow is
   unaffected.
7. **Only one of the five contribution actions had a backend.** `personal/`
   now has all five: `POST /personal/contributions` (add a place, through
   the existing layer0 moderation pipeline — unchanged), plus
   `POST /personal/contributions/suggest-update`, `/local-tip`,
   `/report-incorrect`, and `/add-media`. All five log through the same
   `ContributionRecord` table (now with `kind`, `status`, `place_id`,
   `metadata_json`, `reviewed_at` columns — migration
   `e2f3a4b5c6d7_contribution_kinds.py`). **Honest limitation, not hidden**:
   the four new kinds are logged with `status="pending"` and are visible in
   `GET /personal/contributions`, but there is no admin review action yet
   that moves them off "pending" — only `add_place`'s status is live,
   reflecting the real layer0 submission. Wiring a review queue for the
   other four is the next real step (same shape, no new architecture —
   see `personal/models.py`'s docstring).

### Verified live, this pass (real Postgres + real Redis + real `uvicorn main:app`, no mocks)

Registered two real users; confirmed `/places/custom` and
`/places/submissions` 401 anonymously and 201 authenticated; confirmed
422s on out-of-range lat/lon, negative cost, and an invalid `price_band`;
ran a complete real 9-question survey end to end (including the Redis
session-store fix above) and finalized it into a real profile; confirmed
a second user is refused (403) generating a trip from the first user's
`profile_id`, and the owner succeeds (200); generated a real trip;
submitted all four new contribution kinds against a real place and
confirmed a nonexistent `place_id` 404s; listed them back via
`GET /personal/contributions`; ran `DELETE /auth/me` against an account
holding a custom place and a contribution record and confirmed the token
stops working afterward (401).

### Deliberately NOT changed, and why

- **`CustomPlaceService`'s "write immediately, no moderation queue"
  design for tourist-added custom places.** One audit recommended scoping
  these to the trip only (`TripPlace` with a synthetic id, never touching
  the global `Place` table) or routing them through Community Submission
  review instead. This is a real, already-documented architectural choice
  from this codebase's own blueprint (see `custom_place_service.py`'s
  module docstring: a tourist adding a real-time, real-world place they
  know about, tagged `DataSource.TOURIST_ADDED` with conservative bias
  signals, needs to be usable in their itinerary immediately — a
  moderation queue would defeat the point). This pass fixed the actual gap
  (no auth) without overriding that design. Revisiting the design itself
  is a product decision, not a bug fix, and is left for Carol to decide.
- **Real object-storage media pipeline** (Journal photos, contribution
  media) — both audits correctly note `media_url` is a placeholder path,
  not a real upload. Building S3-compatible multipart upload, MIME
  validation, and a shared `MediaService` is a substantial new subsystem,
  not a fix; it's the top item for the next pass and is tracked, not
  silently dropped.
- **Persistent account-level travel/notification preferences,
  points-ledger table, "Download my data" export, Talk to Guide UI, voice
  playback wiring, full 5-language localization of chunks 2-4, Explore's
  map view and real photography, moving the auth token to
  `flutter_secure_storage`, a centralized app-level API/error-handling
  layer.** All real, all correctly identified, all out of scope for what
  could be built AND actually live-verified in this pass. Not faked,
  not silently ignored — listed here as the honest next-phase roadmap,
  roughly in the priority order the audits suggested: (1) real media
  pipeline, (2) the four new contribution kinds' review queue +
  preferences/points/export, (3) Talk to Guide + voice, (4) localization +
  Explore polish, (5) frontend hardening (secure storage, centralized API
  layer, typed error handling).

## Chunk 4 — My Trips / Journal / Contributions / Notifications (Flutter integration, final chunk)

This is the final chunk of the Flutter frontend build (chunks 1-4 — see
`/home/claude/gz/README.md` for the frontend side). What's new on this
backend for it:

- **My Trips / Journey Story** — added directly to the existing `trips/`
  module: `GET /trips` (your journeys, split into upcoming/completed)
  and `GET /trips/{trip_id}/story` (an auto-generated story — distance,
  duration, photo/video counts, highlights — computed entirely from
  `Trip`/`TripPlace`/`JournalEntry` rows chunk 2 already writes; no new
  table, nothing fabricated). See `trips/schemas.py`'s
  `TripSummaryOut`/`TripStoryOut` and `trips/service.py`'s
  `list_my_trips`/`trip_story`.
- **Contributions + Notifications** — a new `personal/` module. See
  `personal/README_PERSONAL.md` for exactly what it wraps (layer0's
  existing, already-correct community-submission pipeline), what's new
  (one small `contribution_records` table), and what's honestly not
  wired yet (four of the five contribution actions the spec lists are
  UI-only "coming soon" affordances for now).
- **Account deletion** — `DELETE /auth/me` added to `auth/routes.py`,
  distinct from logout. Deletes the account's trips (cascading to their
  places/journal via the existing ORM relationship), trip events, and
  contribution records, then the user row. Verified live against a real
  account with a real trip.
- **New migration**: `migrations/versions/d1e2f3a4b5c6_contribution_records.py`,
  chained off chunk 2's `c8d2e3f4a5b6`. Run `alembic upgrade head`.

### What was verified live (this chunk)

Real Postgres, real `uvicorn main:app`, no mocks: registered a real
user, ran the real 9-question survey, generated a real itinerary
against real Mangaluru place data, confirmed it, arrived/checked out at
a real place, added a real journal entry, then exercised every new
endpoint — `GET /trips`, `GET /trips/{id}/story`,
`POST`/`GET /personal/contributions`, `GET /personal/notifications`
(both before and after an admin approved the submission, to see the
notification and impact message flip), and `DELETE /auth/me` against an
account that actually owned a trip with a checked-out place and a
journal entry (this caught and fixed a real foreign-key-ordering bug —
see `personal/README_PERSONAL.md`). Everything above is what actually
happened in this sandbox, not a description of what should happen.

Known gap, disclosed rather than hidden: the OSRM routing calls
`layer4`/`layer2` make during itinerary generation are blocked by this
sandbox's network policy (same free OSRM public servers chunk 2 always
used) — every call correctly falls back to the existing circuity-
adjusted haversine estimate (`groundzero.layer2.routing_service`'s own
fallback, not something added for this chunk), so trips still generate
correctly, just slower in this sandbox than on an unrestricted network.

## Current integrated v4 fixes

### Alembic: missing `1547c464d7fe` revision
If an existing PostgreSQL database reports `Can't locate revision identified by '1547c464d7fe'`, this source tree now contains `migrations/versions/1547c464d7fe_legacy_compatibility.py` and the current `a1b2c3d4e5f6` migration is chained after it. Do not delete or manually edit `alembic_version`. Run:

```powershell
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
```

The expected head is `a1b2c3d4e5f6`. The compatibility migration is intentionally a no-op bridge because the original legacy migration source is not present in the integrated tree.

### Companion / Tell Me More
The Companion screen no longer needs an Ask Engine textbox. After **I've arrived** is tapped, the place's own **Tell me more** button appears on the same page. Its response is exactly one sentence from stored Wikipedia/Wikidata data; no Groq/LLM call is made for this interaction. If neither source contains usable information, the UI says: `Information is not available for this place at the moment.` The sentence can be read aloud with the inline voice button.

### Voice Personality now actually changes tone and voice (fixed)
Picking **Warm Local Friend / Calm Historian / Witty Companion** at survey time now audibly and textually changes the companion, everywhere it "speaks":
- **Proximity companion-voice lines** (`layer3_i18n.TEMPLATES`) already had distinct wording per personality; unchanged.
- **Ask Engine** (`layer3_ask_engine.py`) previously always told the LLM to "be warm" no matter which personality was selected — fixed: the session's personality is now passed through (`orchestrator.ask` → `AskEngine.ask(..., voice=...)`) and picks a different tone instruction (`ASK_TONE_BY_VOICE`), so LLM-phrased answers read warm / historian / witty while the underlying facts stay identical.
- **Tell Me More** stays strictly grounded and LLM-free per Blueprint §7.2 (that guarantee is not touched) — it now prefixes the stored sentence with a short personality lead-in in English (e.g. Witty: *"Here's a fun fact: …"*, Historian: *"For the record: …"*, Warm: *"Here's something lovely about it: …"*). Non-English packs are left as-is since they're first-draft translations pending native review.
- **Text-to-speech** (`CompanionScreen.VOICE_TUNING`) already varied `rate`/`pitch` per personality for both the proximity read-aloud and Tell Me More read-aloud; confirmed working, no change needed.
- Safety/SOS messages deliberately stay personality-neutral (Blueprint's safety logic is special-cased and must not vary by tone).

### SOS / trip controls
SOS records the safety event, pauses the trip, and hands the device to its `tel:112` phone handler. A custom consent window is used before the handoff. On platforms without a phone handler (for example a desktop without a configured `tel:` application), the trip remains paused and the UI asks the user to call 112 manually. Trip Options provides **Pause and resume later**, **Exit trip**, and **Close**.

### OSM navigation flow (updated)
Route Map (`ItineraryMapScreen`) uses OpenStreetMap tiles and the Layer 4 OSM/OSRM routing service (`POST /layer4/navigation/route`) to draw a live **you are here** dot that tracks the phone's real GPS, plus the current road-network leg to the next not-yet-visited stop (HIVE priority order preserved), with a distance/ETA banner. A **◎ recenter** control re-follows the live position after the map is panned manually.

The previous in-app, custom turn-by-turn screen (`NavigationScreen`) has been removed — public OSRM demo servers don't carry live traffic and were the source of unreliable guidance. **Navigate** now hands the current leg straight to the phone's own Maps app (Google Maps on Android/web, Apple Maps on iOS) via a deep link, exactly like a person tapping "Directions" in Maps — real turn-by-turn, real live traffic, in its own tab/app, with zero extra backend dependency. The in-app map stays for the trip-wide overview and live position; the phone's own Maps app is the right tool for the turn-by-turn part. If OSRM is briefly unreachable the in-app leg still falls back to a distance/ETA estimate, clearly labelled as such — the **Navigate** hand-off is unaffected either way since it only needs the next stop's coordinates.

No backend change was required for this: `layer4/navigation.py` and `POST /layer4/navigation/route` are unchanged and still power the in-app overview leg.

# Ground Zero — Layers 0–5 + Live Mangaluru Events

"A Human-Centric & Necessity-Driven Intelligence for Tourism"

> **This build adds Layer 3 (Context Engine / Silence Filter — see its own section below), wires in Layer 5 (see below), and
> adds the Live Mangaluru Events module (see below) to the Layers 0–2
> backend this README was originally written for. For the complete,
> itemized list of every seam-level bug found while integrating all of
> this — with exact setup/verification steps — see
> [`INTEGRATION_NOTES.md`](./INTEGRATION_NOTES.md).**

## Status (honest, as of this build)

This is a **real, working, tested backend skeleton** for Layers 0–2, built
clean-architecture style (domain / application / infrastructure / api per
layer), plus a lightweight React Native frontend skeleton. It is NOT yet a
populated tourism app — there is no data in the database until you run the
ETL pipeline against a real network connection.

**What's genuinely verified right now (77 automated tests, all passing):**
- Bias Index formula (`layer0/application/bias_audit.py`) — property-tested
- Freshness scoring, accessibility detection, deduplication — unit-tested
- Soul Survey state machine + curiosity vector extraction — unit-tested,
  including a real bug the tests caught and fixed (a lexicon mis-mapping)
- **Personal Fit Score formula verified exactly against the blueprint's own
  Table 10 worked examples** (Milagres Church, Summer Sands Resort, Mrs.
  Lobo's Home Kitchen)
- Hard Filters — all 7 exclusion rules from the brief, each with its own test
- Slot Assembly — full-day (13 slots) and half-day slot counts match
  Table 5 exactly, no place double-booked, wildcard designation works
- Transport Tagger — real haversine-distance-based mode/cost thresholds
- Weather Scheduler — rain-hour outdoor/indoor swap logic
- **Full HIVE pipeline integration test** — Hard Filters through
  Recommendation Queue, using fakes, produces a correct 13-item day

Run them yourself: `pytest -v` (see Setup below).

**Now verified live against a real PostgreSQL 16 + PostGIS 3.4 instance**
(installed and run directly in the build environment — genuinely executed,
not simulated). This caught and fixed **three real bugs** that would have
broken on first use:
1. Alembic's async migration never committed its transaction
   (`connectable.connect()` → `connectable.begin()`) — migrations were
   silently running and rolling back with no error.
2. GeoAlchemy2's `Geography` column auto-creates its own spatial index via
   a DDL event, colliding with Alembic's own tracked index and crashing
   `CREATE TABLE` with a duplicate-index error — fixed by disabling
   GeoAlchemy2's auto-management (`spatial_index=False`) and letting
   Alembic own it.
3. Accessing `model.location` directly to compute lat/lon triggered an
   implicit synchronous lazy-load inside the async session
   (`MissingGreenlet`) — fixed by querying by `id` instead of touching the
   ORM attribute.

After those fixes, verified working end-to-end against the live database:
storing and fetching a `Place` (coordinates and bias signals round-trip
correctly), the real `ST_DWithin` spatial duplicate-detection query, the
full Community Submission workflow (submit → pending → approve → bias
audit → Master Data Core), the `TouristProfile` save/fetch cycle, and the
full HIVE engine reading real rows from Postgres and correctly excluding
an unverified (no `last_verified_at`) place via the freshness Hard Filter.

**Still unverified against live external services** (this sandbox's network
egress doesn't reach them — confirmed 403 on Overpass and Wikidata before
writing any collector code):
- `layer0/infrastructure/collectors/*` — OSM Overpass query, Wikidata
  SPARQL query, Wikipedia REST call, OpenWeatherMap One Call, WorldTides,
  RSS feeds. The query/request code is correct and will run for real
  wherever network egress is open (your machine, a VPS, GitHub Actions,
  etc.) — it has not been run end-to-end here.

**What's still a stub / next step**, clearly marked in code:
- `layer0/infrastructure/collectors/local_listings_collector.py` defines the
  *contract* for Karnataka Tourism / local listing sources but has zero
  concrete `ListingSource` implementations registered — there is no single
  stable public API for these, so real sources need to be identified and
  implemented per-site.
- Survey session state is in-memory (single-process) — noted in code as
  needing a Redis-backed store before multi-worker deployment.
- Frontend is a functional-but-plain skeleton wired to the real API
  (Soul Survey tap-cards + HIVE results list actually call your backend) —
  none of the "premium/Airbnb/Headspace" visual design work from the brief
  (glassmorphism, micro-animations, custom illustrations) has been done yet.
  That's the frontend deepen pass.

## A blueprint inconsistency found and flagged (not silently resolved)

Table 5's half-day slot counts (Grounding 1 + Signature 1 + Anchor 1 +
Personal 4 + Local Secret 1 = **8**) don't match Table 11 step 8's summary
("7 slots for half-day"). This implementation follows Table 5 (the
authoritative per-role table) — `layer2/domain/entities.py` and the slot
assembly tests document this explicitly. Worth reconciling in the source
blueprint doc.

## Layer 1 — deepened (this pass)

Per instruction, Layer 1 is now fully deepened while Layer 0 stayed
architecturally open for a future Karnataka Tourism source (see below).

**Real bug found and fixed:** `TouristProfile` had no `device_id` field at
all — `SurveySession.device_id` was captured but never made it onto the
saved profile, so the Return Visitor Check (blueprint 4.5) could never
actually find a prior session. Fixed, with a regression test.

**Survey session storage moved to real Redis** (`layer1/infrastructure/
survey_session_store.py`), replacing the single-process in-memory dict.
Verified against a live Redis instance: store, fetch, TTL, delete, and a
full multi-step survey flow (start → 13 answers → finalize) all confirmed
working end-to-end against the real service, not a mock. Falls back to
an in-memory store (with a loud warning log) if Redis is unreachable, so
local dev without Redis running doesn't hard-fail.

**Group Session join flow actually implemented** (blueprint 4.7): starting
a group mints a `group_session_id`; a second person can now join with
that exact code via `POST /survey/start {"join_group_session_id": "..."}`
instead of getting their own separate code. `GET /survey/group/{id}/
members` lists everyone linked to a group so the app can show "Jia and
Dion have joined." Covered by a real multi-session test proving two
separate survey completions land on the same group_session_id.

**Frontend Soul Survey is now fully wired**, not a placeholder: real tap-
cards for single-select questions, toggle-and-continue for multi-select
(dietary flags, accessibility flags), a numeric input for budget, a
free-text box for the curiosity question (Q7 — "the most important
input"), a day-count follow-up for multi-day trips, a Start screen with
"start new" vs. "join with a code," and a Group Share screen that polls
`/survey/group/{id}/members` so the group organizer can watch people
join. All 8 frontend files verified to parse with a real Babel parser;
`npm install` confirmed the full dependency tree resolves.

## Layer 0 — kept modular for Karnataka Tourism (this pass)

No time was spent searching for a real Karnataka Tourism / local listings
API, per instruction. Instead, the plug-in seam was verified and, in
review, found to be incomplete — `LocalListingsCollector` existed but was
never actually called by the ETL orchestrator. Fixed: it's now wired into
`EtlOrchestrator` (Step 1b, same tier as OSM), with `ListingRecord ->
Place` conversion flowing through the exact same accessibility/enrichment/
bias-audit/dedup/storage pipeline OSM places use. Proven with tests using
a fake source (`layer0/tests/test_etl_local_listings_seam.py`) — including
one for a source that fails outright, confirming it can't take down the
whole ETL run. When a real API is found later, registering it is exactly
the one-line change documented in `layer0/api/dependencies.py`.

## Layer 2 — deepened (this pass)

**Real bug found and fixed — budget was never actually enforced across a
day.** Hard Filters only checked each place individually against the
*full* budget, never tracking cumulative spend. Reproduced concretely: a
₹500 budget with ₹100 places produced a ₹1,556.75 day (3x over). Fixed
with two passes — an approximate pre-transport trim (drops low-fit
Personal/Wildcard slots first, protects the narrative backbone: Grounding/
Signature/Anchor/Local Secret) and a strict post-transport pass that
iteratively re-tags transport and re-checks the real total until it
genuinely fits, or only the protected backbone remains. Verified against
live Postgres with real Mangaluru place coordinates (Milagres Church,
Kadri Manjunath Temple, Panambur Beach, and others) and a ₹400 budget —
came in at ₹285.82, correctly staying under budget with real transport
fares.

**Multi-day trips implemented — previously didn't exist.**
`TouristProfile.multi_day_count` was on the domain model since Layer 1
but nothing in Layer 2 ever consumed it; every call produced exactly one
day regardless of `trip_duration_hours`. Added
`HiveEngine.build_multi_day_recommendation_queue()`, exposed via `POST
/hive/recommendations/multi-day`: generates one queue per day, excluding
every place used on an earlier day of the same trip so day 2 doesn't
repeat day 1's Signature pick. Also respects genuine cross-trip Return
Visitor exclusions on top of that. 6 tests covering day count, no
repeats, 24h spacing, and exclusion inheritance.

**Transport fares calibrated against real Mangaluru rates**, not
estimates: the auto rickshaw fare now models the actual two-tier official
Dakshina Kannada RTA tariff (₹35 flat for the first 1.5km, then ₹20/km —
per the December 2025 revision, reported by Daijiworld) instead of a
flat per-km guess from zero. Cab rate uses a representative local sedan
rate (~₹13/km, ~₹80 base) — flagged in the code as more approximate than
the auto rate, since no single official local-ride tariff card was found
for cabs the way one exists for autos.

98/98 backend tests passing after this pass (up from 90).

**Real bug found and fixed (this build) — a real geofence that could
silently zero out an entire day, for any survey answer.** Layer 2 added
`start_latitude`/`start_longitude` to `POST /hive/recommendations` — a
genuine, well-motivated feature (blueprint 5.1's "reachable time-and-
distance budget" Hard Filter had never actually been implemented; nothing
read the tourist's position before this). But `reachability.py`'s radius
search had no fallback: if literally nothing fell within even its widest
allowed radius (30km), it returned an empty candidate pool — before
budget, timing, or anything else ever ran. The most common way a caller
ends up passing a wildly-wrong location isn't user error, it's routine
dev/test reality: an iOS Simulator's default location (Apple Park,
Cupertino), an Android emulator's default/`(0,0)` fix, or a stale
cell-tower GPS fix — any of which is thousands of km from every place in
this dataset. Result: "Nothing quite fit today" for every survey answer,
regardless of budget or timing. Fixed — when the widest radius still
finds nothing, `reachability.py` now falls back to the full candidate
pool (an untrustworthy location degrades gracefully to "don't geofence,"
never to "return nothing"), and `geofence_radius_km` in the response
becomes `null` in that case so it's honestly reported as unfiltered, not
silently claimed as a working 30km filter. 2 new regression tests
(`layer2/tests/test_hive_engine.py`) covering both the fallback and that
a real, in-coverage location still narrows the pool correctly. The
frontend (`HiveResultsScreen.js`) was also given a second, more useful
empty-state diagnosis — see Frontend section below — since geofencing
isn't the only thing that can legitimately produce zero results (an
un-imported places table is the other common one, and the two used to be
indistinguishable from the UI alone).

## Layer 3 — Context Engine / Silence Filter / Ask Engine (this build)

Everything above (Layers 0–2) gets a tourist a *day*: a ranked, budgeted,
transport-tagged itinerary. Layer 3 is what runs *during* that day — it
decides, moment to moment, whether the app should actually say anything
right now, and answers questions grounded only in what's actually known
about wherever the tourist is standing. It lives in `layer3/` as a
self-contained module (own config, own small operational SQLite DB for
sessions/visits — separate from the main Postgres, which it only ever
*reads*) and is mounted into the combined app at `/l3/*` — see
`main.py`'s `attach_layer3(app)` call.

**What it actually does, end to end:**
- **Silence Filter** — the default state is silence. A location update
  alone is not a reason to say anything; Layer 3 only speaks when there's
  a genuine reason to (arrived somewhere new, a real safety condition, an
  etiquette moment worth a heads-up) and respects Quiet Hours and a
  per-tourist notification cooldown so it never nags.
- **Context Engine** — `POST /l3/context/evaluate` is the one call that
  matters: given a session and a location, it weighs Tier A (hard,
  deterministic signals — arrival, safety, schedule drift) and Tier B
  (softer live signals — weather, tide, crowd, nearby events) and returns
  one of `speak` / `silent` / `safety_alert`, with a single templated (or,
  optionally, LLM-composed) sentence when it does speak — never a wall of
  text.
- **Ask Engine** — `POST /l3/ask` answers a free-text question **only**
  from that place's own stored record (description, Wikipedia extract,
  opening hours, accessibility, etc.) plus live data for genuinely
  time-sensitive questions ("is it open right now"). If the record
  doesn't say, it says so — it does not guess or hallucinate a plausible-
  sounding answer.
- **Companion Voice** — turns a decision into one short, humane sentence
  (plus an optional etiquette whisper — a quiet cultural heads-up, e.g.
  removing shoes before a temple), in the tourist's chosen language.
- **Safety** — a manual SOS (`POST /l3/sos`) always breaks through Quiet
  Hours; genuine safety conditions are Tier A, never softened by the
  Silence Filter the way an ordinary "you might like this" nudge is.

**How it's wired into the rest of the stack** (all in `main.py` +
`scripts/`, none of it inside `layer3/`'s own code, which is unmodified):
- Layer 3 was built to read a *flattened* master-data export
  (`layer0/data_output/master_data_core.json`) with top-level `lat`/`lng`,
  flat bias/accessibility fields, etc. Layer 0's real export
  (`data/master_data_core.json`) nests those one level deeper — both
  shapes are legitimate, independently-designed exports, exactly the kind
  of seam Layer 3's own bridge code says it expects to have to tolerate.
  `scripts/export_layer3_master_core.py` is the missing half: a
  non-destructive adapter, regenerated automatically on every boot, that
  never modifies Layer 0's real export or Layer 3's own code. Verified for
  real against the live 708-place dataset: 708/708 places resolve
  lat/lng correctly (0/708 before the fix).
- Layer 3's `nearby_events` signal already had the code to read a
  `live_events_cache.json` file — it just never existed. The **Live
  Mangaluru Events** module (below) now feeds it, via
  `scripts/export_layer3_events_cache.py`.
- Layer 3's own defaults assume a fully-separated microservices topology
  (Layer 1 on :8002, Layer 2 on :8003). Here everything runs on one app,
  one port — `main.py` points `LAYER1_BASE_URL`/`LAYER2_BASE_URL` at
  itself (`GROUNDZERO_BASE_URL`, default `http://localhost:8000`) before
  Layer 3's settings are constructed.
- A small additive compatibility route, `POST /hive/generate`
  (`integration/layer2_layer3_bridge.py`), lets Layer 3's own bridge code
  reach Layer 2's real engine under the path name it expects — reusing
  Layer 2's actual dependency-injected engine, zero duplicated logic. In
  the app's real flow this isn't actually needed: the frontend already
  has the confirmed itinerary by the time it starts a Companion session
  and hands it straight to `POST /l3/session/start`.
- Runs on **real Layer 0 data only** — Layer 3's own bundled
  `layer3/sample_data/*.sample.json` is never read by the running app;
  that's exclusively for Layer 3's own standalone demo mode.

**Frontend**: `frontend/src/screens/companion/CompanionScreen.js` +
`frontend/src/api/client_layer3.js`. Reachable from HIVE results — once a
day is confirmed, a **"Begin your trip"** button starts a Layer 3 session
with that exact itinerary and opens the Companion screen: a live
check-in loop (mirrors the ~30–60s/GPS-update cadence Layer 3's own docs
describe) plus an instant **"I'm here"** button, the one-sentence
companion message with **"Tell me more,"** a grounded **Ask** box, **Quiet
Hours**, **SOS** (with a confirm step), **"I've arrived"** per stop, and a
**"Happening nearby, verified"** section fed by Live Events — shown only
when genuinely non-empty. Every field name in that screen was checked
against Layer 3's actual orchestrator/route code, not guessed.

See `INTEGRATION_NOTES.md` for the complete list of every seam-level bug
found while wiring this in (config collisions, a missing exception
handler, dependency-version conflicts) and exact setup/verification
steps.

## Layer 5 — Companion signal sources (wired into the app in this build)

Layer 5's code (`layer5/`: chatbot, geofencing, multilingual support,
voice guide) already existed in this codebase before this build, but
**had no router included in `main.py` at all** — none of it was ever
reachable over HTTP despite the classes existing and presumably being
tested in isolation. Fixed by including `layer5.api.routes.router` in the
combined app (mounted at `/companion`). Layer 3's Context Engine and
Silence Filter are conceptually the successor to (and, where they
overlap, a more fully-specified version of) what Layer 5's geofencing and
chatbot pieces were reaching for — Layer 3 is what the Companion screen
above actually talks to. Layer 5's endpoints remain available in their
own right at `/companion/*`.

## Live Mangaluru Events (this build)

A real events-verification service (`live_events/`): JSON-LD/microdata
scraping, a robots.txt-respecting fetcher, and a human-vetted source
allowlist — never crawls the open web, only fetches from sources someone
has explicitly added and verified is safe to scrape (see
`live_events/docs/DATA_POLICY.md`). Mounted at `/events-live/*`, with its
own small SQLite DB (separate from the main Postgres) and its own
APScheduler-driven periodic refresh.

**Runs on real, live-collected data only — no static seed events.** The
module originally seeded the database two ways: `Source` rows (which
websites to monitor — legitimate bootstrap *configuration*) and static,
pre-verified `Event` rows inserted directly, bypassing the actual
scrape/parse/verify pipeline. The static event seeding was removed from
the automatic startup path (`live_events/app/seed.py`); only the source
allowlist is still seeded automatically, and a real scrape now runs
immediately at boot (not just after the first 6-hour interval) so the app
is driven by genuinely fresh data from the moment it starts. Until a
source's first real scrape succeeds, its events endpoints correctly and
honestly return `[]` — expected behavior, not a bug, per the module's own
"never fabricate" policy.

Feeds Layer 3's `nearby_events` signal (see above) and the Companion
screen's "Happening nearby, verified" section — both only ever see
events that came from an actual live fetch of a vetted source.

## Frontend (this build, extending the section below)

`HiveResultsScreen.js`'s empty-state ("Nothing quite fit today") used to
give one generic explanation ("your budget or timing ruled out
everything") regardless of actual cause. It now makes one extra `GET
/places` call, only when the queue comes back empty, to distinguish two
genuinely different problems that used to look identical: **the places
table itself has zero rows** (an admin needs to run
`python import_master_data.py`) vs. **places exist, but this profile's
budget/timing genuinely ruled all of them out**. See the Layer 2 section
above for the geofence bug this was partly written to help diagnose.

## Admin Dashboard (this pass)

Built as a standalone web app (`admin-dashboard/index.html`) rather than
bolted onto the React Native tourist app, since staff-facing tooling and
a mobile consumer app have different natural homes. Design direction:
Mangaluru is a port city and the bias index is fundamentally an
instrument reading, so the UI is built around a harbor-instrument-panel
metaphor — deep indigo-teal, brass accent, radial gauge dials for bias
scores (the signature element) instead of plain progress bars, slab
serif headings, monospace data readout. Covers pipeline status/trigger,
grade distribution, the community review queue with approve/reject, and
a searchable/filterable Master Data Core browser — all of it calling the
live backend directly, nothing mocked.

**Real bug found and fixed while verifying this against the live stack:**
community submissions defaulted to `local_percentage=0.0`, so a genuine
hidden-gem submission (exactly what the community pipeline exists to
surface) scored `bias_index=0.35`, graded merely "balanced" — undermining
the point of the whole pathway. Confirmed via an actual submit → approve
round-trip against the live backend, fixed to default toward
`local_percentage=0.85`, re-verified the same way: a second real
submission through the running API now scores `bias_index=0.0525`,
correctly graded "authentic."

## Frontend visual deepening (this pass)

The tourist-facing app was functionally wired since an earlier pass but
visually plain — this pass does the actual design work the original
brief asked for ("Apple, Airbnb, Notion, Headspace, Calm... Framer
Motion, Glassmorphism, soft gradients, micro animations... Elegant
onboarding").

**Design direction**: Mangaluru is a specific place, not a generic
"travel app" — the visual language is built from it. Colors trace to
real coastal materials (deep-tide teal for the Arabian Sea at dusk,
laterite red-clay for the region's iconic roof tiles, temple brass,
monsoon leaf green) rather than being picked abstractly. Type pairs
Fraunces (an editorial serif with organic, hand-cut curves — reserved
for the hero moment) against Manrope (clean humanist body text).

**Signature element**: the Signal Ring — a slow-breathing brass ring
(Reanimated, ~3.4s loop) representing the guide's quiet presence rather
than a spinner or chattering assistant. Directly expresses the product's
"silence by default" philosophy: it's present and attentive, not
performing activity at you. Appears as the Start screen's hero and as a
small ambient presence indicator during the survey and results loading.

**What's real**: every screen (Start, Soul Survey, Group Share, HIVE
Results) rebuilt with glassmorphic cards (`GlassCard`, real `expo-blur`
frosting), Reanimated entrance/exit transitions between survey
questions, a proper skeleton-loading component (not spinners) for the
HIVE results wait, and real empty/error states with copy that fits the
product's voice instead of generic "no data" messages.

**Verified, not assumed**: this sandbox can't render React Native, so
verification took a different form — confirmed `npm install` resolves
the two new Google Fonts packages (1153 packages total), confirmed the
exact loaded font family strings (`Fraunces_600SemiBold_Italic`, etc.)
against the installed package's real file names rather than guessing,
confirmed `LinearGradient`/`BlurView`/every Reanimated animation import
used (`FadeInRight`, `Layout`, `useSharedValue`, etc.) actually exists
in the installed package via its type declarations, all 10 new/changed
files parse cleanly with a real Babel parser, and cross-checked every
single token reference (`colors.x`, `typography.x`, `spacing.x`,
`radii.x`) across every screen against the actual token definitions —
zero typos. This catches the most common way a design pass silently
breaks (a renamed token, a wrong import) without needing a device to
run on.

**Not done in this pass**: the Admin Dashboard's visual design (already
distinct — harbor-instrument-panel, done in an earlier pass) is
unrelated to this; this pass covers only the mobile tourist app. Custom
illustrations from the original brief still don't exist — everything
here is typography, color, motion, and the Signal Ring, not illustrated
artwork.

## Integrated Layer 4 / frontend flow (this build)

Layer 4 is now wired into the combined FastAPI process. It owns live-trip supervision and an OSM/OSRM navigation endpoint at `/layer4/navigation/route`; Layer 3 remains the durable session authority. Active sessions start the Layer 4 supervisor, while paused/completed/ended sessions stop it. The navigation route preserves HIVE queue priority (first slot, then next), uses a depth-first priority traversal plus OSM/OSRM's shortest road-network path for each ordered leg, and has a straight-line fallback if both free routing endpoints are unavailable. The frontend's Route Map (`ItineraryMapScreen`) uses this endpoint only for its in-app live overview leg/ETA banner; the **Navigate** button hands off to the phone's own Maps app for the actual turn-by-turn (see "OSM navigation flow (updated)" above) — no new package required, `Linking` is core React Native.

The companion UI no longer exposes the free-text Ask Engine. A place can show one `Tell me more` action, and that action returns exactly one stored Wikipedia/Wikidata sentence. No Groq call is used for that interaction. The existing Groq/Ask backend is left intact but is not part of the user flow.

Notifications now request OS notification permission at trip start. Place notifications include a `Read aloud` action. The SOS flow pauses the trip, records the Layer 3 SOS signal, and opens the device phone dialer for emergency number `112`; returning to the app exposes Resume Trip / Exit Trip.

### VS Code / local run

```bash
# Terminal 1 — infrastructure
docker compose up -d

# Terminal 2 — backend
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3 — Expo frontend
cd frontend
npm install
# Web / local simulator:
npx expo start
# Physical phone: set EXPO_PUBLIC_API_BASE_URL in frontend/.env to the
# computer's LAN IP first, then clear the Metro cache:
npx expo start -c
```

`expo-notifications` is now a frontend dependency. If you already have an older `node_modules`, run `npm install` once so Expo installs it. Native notification permission behavior is provided by the Expo Notifications config plugin in `frontend/app.json`.

### Navigation fallback / API knobs

```bash
# Optional: change the OSM routing endpoint/profile used by Layer 4
export LAYER4_OSRM_BASE_URL=https://router.project-osrm.org/route/v1/driving
export LAYER4_OSRM_FALLBACK_URL=https://routing.openstreetmap.de/routed-car/route/v1/driving
export LAYER4_ROUTING_TIMEOUT_S=8
```

The map is intentionally keyless: OpenStreetMap tiles + public OSRM endpoints are used. For production/high traffic, point `LAYER4_OSRM_BASE_URL` at your own OSM routing service.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt --break-system-packages
cd frontend && npm install && cd ..

# 2. Start Postgres+PostGIS and Redis
docker compose up -d

# 3. Configure environment
cp .env.example .env
# fill in OPENWEATHERMAP_API_KEY and TIDE_API_KEY at minimum

# 4. Run migrations
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

# 5. Run the backend
uvicorn main:app --reload
# -> http://localhost:8000/docs for interactive API docs

# 6. Run the frontend (separate terminal)
cd frontend && npm start

# 7. Run tests
pytest -v

# 8. Spot-check the personality fix (Ask Engine tone + Tell Me More lead-in)
cd layer3 && python -m pytest -q -k "tell_more or ask" && cd ..
```

## Troubleshooting: "Couldn't start your companion"

Two real bugs caused this and are fixed in this build:

1. **`API 404: profile_not_found` for every profile.** Layer 1's router is
   `/survey`-prefixed and has no plain `GET /profile/{id}`, so Layer 3's old
   HTTP-only profile lookup 404'd unconditionally. Fixed: `ProfileStore` now
   reads `tourist_profiles` directly and read-only from Postgres first (see
   `layer3/layer3_bridge.py::ProfileStore._from_postgres`), bridged via
   `LAYER3_POSTGRES_DSN` (set automatically in `main.py` from `DATABASE_URL`
   — nothing to configure by hand).
2. **`Failed to fetch`.** `frontend/src/api/client*.js` had a stale
   hardcoded LAN IP (`192.168.176.1`) as their fallback `BASE_URL`, used
   whenever `EXPO_PUBLIC_API_BASE_URL` isn't actually baked into the bundle.
   Fixed to fall back to `http://localhost:8000`, matching `frontend/.env`.
   **`EXPO_PUBLIC_*` vars are read once at bundle time** — after editing
   `frontend/.env`, a hot reload is not enough:
   ```bash
   cd frontend && npx expo start -c   # -c = clear the Metro bundler cache
   ```
   On a physical phone (Expo Go) or most Android emulators, `localhost`
   means the device itself, not your PC — set `EXPO_PUBLIC_API_BASE_URL` in
   `frontend/.env` to your computer's actual LAN IP instead (`ipconfig` on
   Windows), then run the command above.

**Layer 4 is now mounted and runnable.** The new `layer4/` package owns the
in-process active-trip supervisor and the OSM/OSRM navigation API. Layer 3
remains the durable session authority, so pausing or ending a trip stops the
Layer 4 loop immediately.

## This pass — what changed, and one architecture flag

**Real changes:**
- The mobile/web companion no longer exposes a free-text Ask box. `Tell me
  more` is the only place-information expansion control and returns exactly
  one sentence from the stored Wikipedia/Wikidata record; the existing Ask/Groq
  backend is not called by the frontend flow.
- Minimal Wallet Tracker: `record_visit` subtracts a place's
  `estimated_cost` from `wallet_remaining` on first arrival (once per
  place); every session snapshot now also surfaces `wallet_remaining`,
  `voice`, and `language`.
- Voice Personality is now actually spoken: the Companion screen uses
  `expo-speech` to read companion messages and the single Tell Me More sentence
  aloud, rate/pitch tuned per `warm` / `historian` / `witty`. The Tell Me More
  control has its own 🔊/🔇 toggle. Free, no API key, works on web and native.
- New live "🗺️ Route map" button: tracks a separate You-Are-Here pin,
  follows HIVE priority order, requests the shortest OSM/OSRM road path to
  the next stop, shows distance/ETA/turn information, and reroutes as the
  user's GPS position changes; it falls back to a transparent offline estimate.
- The itinerary save-on-confirm now retries twice with backoff before
  giving up, and never shows the backend URL or "check the backend"
  wording to the tourist — a failed online backup never blocks the trip.

**Architecture flag, not silently worked around:** `layer5/` implements
its *own* geofencing, narration, translation, and chat engines, parallel
to and overlapping with what Layer 3 already does natively (proximity and companion voice). The frontend was never
wired to `layer5`'s `/companion/*` routes, and this pass deliberately
didn't wire them either — running both engines side by side would mean
two independent, possibly-conflicting notification systems, not one.
Decide whether `layer5` replaces, specialises, or should be retired in
favour of Layer 3's already-tested version before integrating it.

**Validation:** backend Python modules are syntax-checked locally, Layer 4 has
unit coverage for its routing fallback/priority traversal, and the frontend
can be syntax-checked with Expo/Babel after `npm install`. Full device GPS,
phone-dialer, notification-permission, and OSRM behavior still depend on the
VS Code machine/network/device where the project is run.

## Populating real data (Layer 0 ETL)

Once your `.env` is filled in and you have real network access:

```bash
curl -X POST http://localhost:8000/admin/pipeline/run
```

This runs the real 10-step ETL (OSM -> Wikidata -> Wikipedia -> Bias Index
-> tags -> freshness -> accessibility -> dedup -> Postgres -> JSON export).
Expect it to take a while for a full Mangaluru bounding box — Overpass in
particular can be slow under load. Check `sources_skipped` in the response
if a step didn't run.

## Architecture

```
layer0/  Background Engine — Master Data Core ingestion, bias audit,
         freshness, accessibility, dedup, community submissions
layer1/  Soul Survey — 9-question state machine -> TouristProfile,
         curiosity vector extraction
layer2/  HIVE Engine — Hard Filters -> Personal Fit Score -> Slot
         Assembly -> Weather Scheduling -> Transport Tagging
shared/  Config (env-driven, fails loudly on missing required values)
frontend/  React Native (Expo) skeleton wired to the real API
migrations/  Alembic, PostGIS-aware
```

Each layer follows: `domain/` (framework-free entities + repository
interfaces) -> `application/` (business logic, the Repository Pattern
consumer) -> `infrastructure/` (Postgres + real external API clients) ->
`api/` (FastAPI routes + Pydantic schemas + DI wiring).

## What's next (in priority order, per your instruction)

1. Deepen Layer 0: run the real ETL against live network, verify Postgres
   schema against a live PostGIS instance, implement real
   `ListingSource`s for Karnataka Tourism / local listings, add an
   admin-facing pipeline status dashboard.
2. Deepen Layer 1: move survey session state to Redis, build the real
   free-text/slider input screens, upgrade curiosity extraction (embedding
   similarity or LLM-based, swappable behind `CuriosityExtractor`).
3. Deepen Layer 2: verify the full HIVE pipeline against real ingested
   data end-to-end, tune Transport Tagger fare constants against real
   Mangaluru auto/cab rates, add Wallet Tracker groundwork.
4. Frontend deepen pass: the actual premium design system (glassmorphism,
   Reanimated micro-animations, custom illustrations, skeleton loaders).
