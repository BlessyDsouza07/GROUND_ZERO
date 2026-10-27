# Chunk 4 (backend) — Contributions + Notifications

## Why this module exists, and why it's small

Carol's chunk-4 spec needed two new user-facing things that didn't exist
yet (Contributions, Notifications) and one small addition to an existing
module (My Trips / Journey Story, added directly to `trips/` — see
`trips/schemas.py::TripSummaryOut/TripStoryOut`, `trips/service.py`,
`trips/routes.py` `GET /trips` and `GET /trips/{id}/story`; no new table,
every number computed from `Trip`/`TripPlace`/`JournalEntry` rows that
chunk 2 already writes).

This module (`personal/`) holds only what genuinely couldn't go anywhere
else:

### Contributions

The spec is explicit that community data must NOT enter Master Data
directly: `User -> Submission -> Community Data -> Validation -> Review
-> Approved -> Master Data`. That pipeline **already existed**, fully
correct, in `layer0/application/community_workflow.py`
(`CommunitySubmissionService`) and `layer0/api/admin.py` (the admin
approve/reject endpoints). This module does not touch or duplicate any
of it.

What was actually missing: `POST /places/submissions` has no auth and no
submitter field, so there was no way to know which signed-in user made
a submission, show them its status, or give them credit. `personal/`
adds exactly one table, `contribution_records` (user_id, submission_id,
kind, created_at — see `models.py`), and wraps the existing service:

- `POST /personal/contributions` — the one contribution action fully
  wired end to end ("+ ADD A PLACE"). It builds the same `Place` draft
  `layer0/api/routes.py::submit_place` builds, calls the real
  `CommunitySubmissionService.submit`, and records who submitted it.
- `GET /personal/contributions` — the signed-in user's own submissions,
  with status framed the way the spec asked: impact message first
  ("✓ VERIFIED — your contribution helped improve GroundZero for future
  explorers"), Explorer Points shown small and only once approved
  (`+30`, a flat placeholder value — Carol's spec doesn't specify a
  points formula, and this chunk doesn't invent one beyond a flat
  number). `explorer_level` is a quiet label (Explorer / Pathfinder /
  Local Guide / Insider / Pioneer) computed from the approved count —
  **never shown as a leaderboard**, and the thresholds in
  `service.py::_LEVEL_THRESHOLDS` are a provisional, undocumented-in-spec
  guess (0/3/8/16/31 approved contributions), flagged here as something
  to tune once there's real usage data, not a blueprint number.

### Update (Oct 2026 audit-response pass): the other four kinds are now wired

All five contribution actions from the spec now have a real endpoint:

- `POST /personal/contributions/suggest-update` — `{place_id, field,
  current_value?, suggested_value, reason?}`
- `POST /personal/contributions/local-tip` — `{place_id, tip, best_time?,
  context?}`
- `POST /personal/contributions/report-incorrect` — `{place_id,
  issue_type, description, evidence?}`
- `POST /personal/contributions/add-media` — `{place_id, media_url,
  caption?, source?}` — `media_url` is a placeholder the same way
  Journal's is; no object-storage upload pipeline exists yet (see the
  top-level README's roadmap section).

Each validates the `place_id` is real (404 if not), logs a
`ContributionRecord` with `kind` set accordingly, `status="pending"`,
and the kind-specific payload in `metadata_json`, and returns it via
`GET /personal/contributions` alongside `add_place` ones.

**What's honestly still NOT wired**: there is no admin review action for
these four kinds yet — nothing ever moves their `status` off `"pending"`.
`add_place`'s status is the only one that's live, because it mirrors a
real layer0 `CommunitySubmission`. Building that review queue (same
`kind`-switch shape, `review_actions` history, no new architecture) is
the next real step, and `explorer_points`/`total_approved` deliberately
stay `None`/unaffected for these four until that queue exists — never
fabricated as approved just because they were submitted.

### Notifications

Four categories (NOW / YOUR_JOURNEY / AROUND_YOU / GROUNDZERO), computed
fresh on every `GET /personal/notifications` call — **no table, nothing
stored, nothing scheduled**. Sources, all real:

- the user's active/paused trip's next unvisited `TripPlace` (distance
  via the same haversine helper `trips/service.py` uses for trip
  stories; a flat ~0.8 km/min pace assumption for the "N minutes away"
  line — the same kind of estimate layer2/layer4 already use elsewhere,
  not a new invented number)
- sunset proximity via `astral`, same offline calculation
  `explore/context_service.py` already uses for "RIGHT NOW IN
  MANGALURU" (not a new dependency)
- `budget_remaining` vs `budget_total` (a simple <15%-left threshold)
- recent (within 7 days) contribution status changes, read straight off
  `ContributionRecord` + the submission's own `reviewed_at`

Per the spec's explicit "not a notification dump" instruction, the
journey-related lines are bundled into one `YOUR_JOURNEY` notification
("Your afternoon update") rather than emitted as separate pings, and a
trip with nothing noteworthy returns fewer notifications rather than
padding the list. `AROUND_YOU` (nearby new places/events) has no source
in this chunk's build — Explore already has "nearby" logic
(`explore/service.py`) but wiring it into notifications specifically
was judged lower priority than Contributions/My Trips/Journal for the
time available; the category exists in the schema and is simply empty
for now, which is honest, not silently dropped.

### Saved Places (final-release-hardening pass, Oct 2026)

A plain, persistent bookmark — "save this place" — independent of any
trip. This didn't exist anywhere in the backend before this pass; a
review flagged it as a basic expected feature that was simply missing.

- `POST /personal/saved-places/{place_id}` — save a place. 404 if the
  place doesn't exist. Idempotent: saving an already-saved place just
  returns the existing bookmark (201, not a duplicate row or an error) —
  the DB also enforces this with a `UniqueConstraint` on
  `(user_id, place_id)`, so even a race between two requests can't create
  a duplicate.
- `DELETE /personal/saved-places/{place_id}` — unsave. 204 whether or not
  it was saved — unsaving something already unsaved is a no-op, not an
  error.
- `GET /personal/saved-places` — the signed-in user's saved places,
  newest first, each with the place's current name/category (read live
  from `PlaceRepository`, not duplicated onto the bookmark row — if a
  place is ever removed, its stale bookmark is silently skipped rather
  than crashing the list).

Deliberately minimal, matching what was actually asked for: no notes, no
folders/collections, no sharing. New table `saved_places` (`id, user_id,
place_id, created_at` — see `models.py::SavedPlace`), `user_id` with a
real FK + `ondelete="CASCADE"` to `users.id` (unlike layer0/layer1's
nullable, FK-less ownership columns added this same pass — `personal/`
only ever runs inside this combined app, so there's no standalone
deployment missing a `users` table to stay compatible with).

## Account deletion

`DELETE /auth/me` was added to `auth/routes.py` (not this module, since
it's about the account, not personal/contributions). It deletes the
user's `TripEvent`, `ContributionRecord`, and `SavedPlace` rows
explicitly (defensive — `SavedPlace.user_id` and `ContributionRecord
.user_id` already have `ondelete="CASCADE"`, `TripEvent` doesn't have an
ORM cascade relationship to `Trip`/`User` at all), then deletes each
`Trip` through the ORM (which cascades to its `TripPlace`/`JournalEntry`
rows via the `cascade="all, delete-orphan"` already declared in
`trips/models.py`), then deletes the user. Verified live against a real
account that had a real trip with checked-out places and a journal
entry — see the top-level README's "What was verified live" section.

## Migrations

`migrations/versions/d1e2f3a4b5c6_contribution_records.py` created the
`contribution_records` table; `migrations/versions/
e2f3a4b5c6d7_contribution_kinds.py` (Oct 2026 audit-response pass) added
`status`, `place_id`, `metadata_json`, `reviewed_at`, and made
`submission_id` nullable (it's only set for `add_place`);
`migrations/versions/c6d7e8f9a0b1_saved_places.py` (final-release-
hardening pass, Oct 2026) created `saved_places` — the current head. Run
`alembic upgrade head` before starting the server.
