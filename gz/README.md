## Design system pass (Oct 2026) — Stage 1 of the production-candidate visual plan

A production-candidate review proposed a full 33-phase plan (visual
design system, verified-photography pipeline, object storage, Alembic
migrations, Flutter Android/iOS release signing, multi-device testing)
to take GroundZero from its current baseline toward a release
candidate. Its own first instruction was explicit: **do not touch
everything at once** — it's written as ~10 stages over weeks, not one
pass. Given that, and given real constraints in this environment (no
Flutter/Dart SDK here to run `flutter analyze`/`flutter test`, no real
verified photography, no object storage service, no app-store signing
keys), this pass covers **Stage 1 only: the visual design system
foundation** — not the full visual redesign, not branding/logo work
(Phase 2), not the image/media pipeline (Phase 3), and none of the
backend/ownership/release phases. Those stay exactly as they were,
undecided and undone, until asked for explicitly.

### Added

- **`lib/design/`** — the token layer the brief asked for:
  `gz_colors.dart` (the same light/dark palette `theme.dart` already
  used, now the single source of truth), `gz_typography.dart` (a real
  eight-level hierarchy — display/hero/section/cardTitle/label/body/
  caption/metadata — replacing ad hoc `TextStyle(fontSize: ...)`
  literals with named, reasoned levels), `gz_spacing.dart` (an 8px
  scale), `gz_radii.dart` (names the 12/14/18 radii the app already
  used), `gz_shadows.dart` (soft editorial shadows for use instead of
  Material's default elevation), `gz_motion.dart` (names the existing
  900ms theme-fade duration plus two smaller tiers), and `gz_theme.dart`
  (assembles all of the above into the app's two `ThemeData` objects).
- **`lib/widgets/groundzero/`** — the first tranche of shared
  components: `gz_section_heading.dart`, `gz_primary_button.dart`,
  `gz_secondary_button.dart`, `gz_place_card.dart` (as `GZPlaceCardView`
  — `GZPlaceCard` was already taken by `explore_api_client.dart`'s data
  model, so the widget takes a different name rather than colliding
  with it), `gz_empty_state.dart`. The brief's full component list
  (14 names, including hero/journey-card/mood-selector/why-now/
  verified-badge components) is **not** all built here — those belong
  to the screen-by-screen visual redesign (Phases 4–9), a later stage.

### Changed

- **`lib/core/theme.dart`** is now a thin wrapper: `GZLightPalette`/
  `GZDarkPalette`/`GZThemeMode`/`isDaytimeNow`/`buildGZLightTheme()`/
  `buildGZDarkTheme()` all still exist with the exact same names and
  signatures (so `theme_controller.dart`, `theme_sheet.dart`,
  `settings_screen.dart` needed zero changes), but the actual palette
  values and `ThemeData` assembly now live in `lib/design/`. Pure
  refactor — the rendered theme is unchanged in value, just better
  organized, per the brief: "modify theme.dart, but don't keep
  everything inside that one file."
- **Three screens applied as proof the system works** (not all 20+,
  per the brief's own "apply consistently" instruction being Phase-4-
  onward work): `explore_screen.dart`'s five section headers now use
  the shared `GZSectionHeading` instead of a private `_SectionHeader`
  it had been maintaining on its own; `explore/place_card_tile.dart`'s
  visual chrome (badges, title, shadow, radius) now comes from
  `GZPlaceCardView`, with the file itself reduced to just the explore-
  specific category-icon mapping; `personal/my_trips_screen.dart`'s
  empty state now uses `GZEmptyState`.

### Deliberately NOT changed, and why

- **Every other screen's styling.** Rolling the design system out
  everywhere is explicitly staged work (Phases 4–9 of the review), not
  something to do in the same pass that builds the tokens — doing both
  at once is exactly what "do not touch everything at once" warns
  against.
- **Branding/logo (Phase 2), the verified-image pipeline (Phase 3),**
  and every backend/ownership/database/release/testing phase (13
  onward). Unrelated to a visual-token pass and, in several cases,
  dependent on things this environment doesn't have (real photography,
  object storage, a Dart SDK to verify against, app-store credentials).
- **No new dependencies added to `pubspec.yaml`.** This pass needed
  none — the typography/spacing/shadow tokens are built on Flutter's
  own `TextStyle`/`EdgeInsets`/`BoxShadow`, nothing external.

### Verified this pass

No Dart/Flutter SDK is available in this environment to run
`flutter analyze` or `flutter test` (same limitation noted in every
prior backend pass's README) — every new and edited file was instead
checked by hand for balanced braces/parens, and every existing call
site of a symbol this pass kept (`GZLightPalette`, `GZThemeMode`,
`buildGZLightTheme()`, `PlaceCardTile`, `AsymmetricCardGrid`) was
grepped across the codebase to confirm nothing else needed to change.

---

# GroundZero — Flutter frontend (chunks 1 + 2 + 3 + 4, final)

## Chunk 1 — home, auth, start page

Home/landing page, About, How it Works, Sign up/Login (wired to the backend's
`/auth/*` endpoints), light/dark/automatic theme, and the post-login start
page with the left sidebar.

## Chunk 2 — New Trip

Tapping "New Trip" in the sidebar now pushes the real flow:

1. **`lib/screens/new_trip/survey_screen.dart`** — the 9-question survey.
   The step order comes from the backend's `next_step` field
   (`trips/service.py`), not hardcoded here, so if the backend decides a
   question isn't needed (e.g. it inferred your energy level from your
   opening sentence), it simply never shows up.
2. **`itinerary_screen.dart`** — the generated itinerary: an editable list
   on the left (drag to reorder, swipe to remove, "+" to add a place —
   search the existing catalog or add your own), a live map on the right
   (`flutter_map` + OpenStreetMap tiles, same free-tooling philosophy as
   the backend's own OSRM/Overpass choices). Rate it, then confirm —
   confirming asks for two independent toggles (notifications, tour-guide
   voice) and whether to start now or schedule for later.
3. **`active_trip_screen.dart`** — the live trip: current stop, "I'm here"
   / "check out" (spend + energy + rating) / "skip", a running budget and
   energy readout, pause/resume, exit-with-a-reason, and a camera button
   that adds to the journal.
4. **`journal_screen.dart`** — everything captured during the trip, in
   order, as a scrollable timeline.

Explore, Talk to Guide, Trips (past trips), Notifications, and
Contributions are still "coming soon" — you said those are later chunks.

## Chunk 3 — Explore

A mood-first, context-aware discovery page, per your attached spec.
Reachable two ways:

- **Signed out**, from the public landing page's top bar/menu ("Explore") —
  the spec explicitly requires browsing before sign-up.
- **Signed in**, from the sidebar's "Explore" entry (previously "coming
  soon", now the real thing).

Both open `lib/screens/explore/explore_screen.dart`, which assembles:

1. **Hero + search** — "EXPLORE — MANGALURU, DIFFERENTLY" with a search
   icon that opens `explore_search_screen.dart` (recent/suggested
   searches, then results; an "open now" filter toggle rather than
   filters-before-discovery).
2. **"RIGHT NOW IN MANGALURU"** — weather/tide/sunset-countdown/events,
   with `weather_note`/`tide_note` turning the data into an actual
   recommendation ("Rain moving in — maybe skip the exposed coast...")
   rather than just displaying numbers.
3. **"WHAT ARE YOU IN THE MOOD FOR?"** — 9 large mood choices. Picking
   one genuinely changes the page: a **"GROUNDZERO PICKS"** section
   appears (never labeled "Recommended places"), each card showing a
   fit percentage, a "WHY THIS PICK?" checklist, and a "WHY NOW?"
   headline+reasons.
4. **"HAPPENING TODAY"** — live events, inline in Explore (not a
   separate page).
5. **"BEYOND THE OBVIOUS"** — the lowest-media-mention, verified-authentic
   places, each with one honest sentence on why it's there (never an
   invented "local legend").
6. **"EXPLORE BY EXPERIENCE"** — the 7 category sections (Coast, Food &
   Flavours, Culture & Heritage, Nature, Local Life, Faith &
   Architecture, Quiet Places), positioned below mood/context discovery
   as the spec asks, not as primary navigation.

Tapping any card opens `place_detail_screen.dart` — full-screen hero,
WHY GO, GOOD FOR, WHY NOW, then three CTAs: **ADD TO MY JOURNEY** (the
strongest one — wires straight into the real `/trips/*` add-place
mechanism from chunk 2), GO THERE, SAVE. Signed-out tourists see
everything up to here freely; tapping ADD TO MY JOURNEY or SAVE is the
one moment a sign-up prompt appears ("This could be part of your
journey..."), per the spec's conversion-funnel requirement.

New backend-facing file: `lib/core/explore_api_client.dart` (mirrors
`trips_api_client.dart`'s style — same base URL, same exception
mapping — but every GET call it makes works with no token).

### What's simplified here, and why

- **No real photography.** The dataset has no image field (see the
  backend's `explore/README_EXPLORE.md`). Cards use an honest
  placeholder (a category icon over a palette color wash), never a
  fabricated stock photo standing in for a real place.
- **The asymmetric card grid is a simplified 3-card repeating pattern**
  (`place_card_tile.dart::AsymmetricCardGrid`), not a true editorial
  layout engine that varies span by image aspect ratio — that needs
  real photography to size against, which doesn't exist yet. It still
  reads as "not a uniform grid," which was the actual requirement.
- **No in-app map view for Explore yet.** The spec is explicit that the
  map is secondary (reached via a CTA, never the primary experience) —
  every place card already carries lat/lng, so wiring the existing
  `flutter_map` setup from `itinerary_screen.dart` in behind a "VIEW ON
  MAP" button is a follow-up, not a redesign.
- **Signing in from inside Explore** (the "Add to My Journey"/"Save"
  prompt) pushes the existing chunk-1 `AuthScreen`. On success,
  `main.dart`'s root listener swaps the whole app over to the signed-in
  dashboard — the same behavior the public landing page's "Sign Up"
  button already has. It does not return the tourist to the place they
  were looking at; they land on their dashboard, signed in, and can
  navigate back. Making sign-in return to exactly where someone was
  would mean reworking chunk 1's root navigation, out of scope here.
- **English-only**, same disclosed reason as chunk 2 (see below).

## Chunk 4 — Your GroundZero, My Trips, Journal, Notifications, Contributions, Settings (final chunk)

The personal-area architecture: the loop Explore -> Plan -> Experience
-> Remember -> Contribute -> improve the next journey, as its own set
of real screens rather than "coming soon" panels. New file:
`lib/core/personal_api_client.dart` (same style as the other two API
clients). New screens, all under `lib/screens/personal/`:

1. **`my_trips_screen.dart`** — "Your journeys." UPCOMING shows the
   active/most-important trip biggest, with "CONTINUE JOURNEY"; this
   screen looks up the trip's actual `status` before continuing it, so
   a still-editable draft itinerary reopens the chunk-2 itinerary
   screen while a confirmed one reopens the live active-trip screen —
   it doesn't guess. COMPLETED trips render as "journey covers" (a
   gradient tile + place count) that open straight into the Journey
   Story.
2. **`journey_story_screen.dart`** — the auto-generated story for a
   completed trip: place count, real distance (haversine between
   visited stops), duration, photo/video counts, and highlights (places
   the tourist rated 4-5). Every number comes from
   `GET /trips/{id}/story`; nothing here is AI-written narrative text,
   per the spec's explicit rule.
3. **`journal_hub_screen.dart`** — the sidebar's top-level "Journal"
   entry: every trip with at least one visited place, newest first,
   each opening into that trip's own journal.
4. **`new_trip/journal_screen.dart`** (enhanced, not replaced) — now
   Timeline / Scrapbook / Map tabs. Entries with the tourist's own
   caption are shown as "Memory Moments" (a highlighted border +
   caption-first layout) — nothing is auto-captioned. Ends with a real
   stats footer (places, km, time, photos, videos — each computed, and
   a stat with no honest number just doesn't appear) plus "What stayed
   with you" and an "ADD TO MY NEXT JOURNEY" button that routes back
   into Explore. The Map tab reuses the exact `flutter_map` setup
   chunk 2's itinerary screen already has.
5. **`notifications_screen.dart`** — four categories (NOW / YOUR
   JOURNEY / AROUND YOU / GROUNDZERO), each already bundled by the
   backend (one "afternoon update" combining sunset + next-stop
   distance + budget, not three separate pings). An empty category is
   simply not shown.
6. **`contributions_screen.dart`** + **`add_place_screen.dart`** —
   "HELP BUILD GROUNDZERO." "+ ADD A PLACE" is the one action wired all
   the way to the real review pipeline; the other four the spec lists
   (suggest an update, share a tip, report an issue, add media) are
   real buttons that honestly say "coming soon" rather than faking a
   submission. Status cards lead with the impact message
   ("✓ VERIFIED — your contribution helped improve GroundZero for
   future explorers"), with Explorer Points shown small underneath and
   only once something's actually approved. `explorerLevel` is a single
   quiet label, never a leaderboard.
7. **`settings_screen.dart`** (reorganized, not rebuilt) — now ACCOUNT /
   TRAVEL / NOTIFICATIONS / PRIVACY / APPEARANCE / DATA / SUPPORT.
   APPEARANCE is the permanent home of chunk 1's light/dark/automatic
   theme picker and language picker — moved here, not rebuilt. DATA
   holds the one thing this chunk could honestly wire end to end
   (**delete account**, with its own confirmation dialog, calling the
   new `DELETE /auth/me`) plus a disclosed "coming soon" for download-
   my-data, rather than inventing an export format the backend doesn't
   support yet.
8. **`start_screen.dart`** (restructured) — the sidebar now has three
   visual tiers: Explore + Plan a Trip on top (bold, colored), My
   Trips + Journal in a clearly secondary group, and Talk to Guide /
   Notifications / Contributions / Settings lower and quieter — not
   eight equally-weighted rows. The old generic dashboard is gone,
   replaced by **"Your GroundZero"**: real stats (journeys, places
   visited, contributions — all from the backend, honest zeros for a
   new account), a "Continue your journey" card when a trip is active,
   and the same "Plan a new trip" CTA chunk 1 had. The sign-out dialog
   now reads "Leaving GroundZero? Your journeys and memories are safe
   in your account." per the spec, and stays clearly separate from
   account deletion (which only lives under Settings -> Data).

### What's simplified here, and why

- **Four of five contribution actions are UI-only.** "+ Add a place" is
  real end to end; "Suggest an update / Share a local tip / Report
  incorrect information / Add useful media" show an honest "coming in
  a future update" snackbar rather than a fabricated success message.
  See `personal/README_PERSONAL.md` on the backend for why — they're
  the same pipeline conceptually, just not built out this chunk.
- **TRAVEL and NOTIFICATIONS in Settings are informational, not
  interactive.** There's no backend concept of account-wide travel
  defaults or a global notification toggle yet (notifications are
  per-trip, set at confirm time in chunk 2) — rather than fake a
  setting that doesn't persist anywhere, these two sections explain
  where the real control already lives.
- **"Download my data" is a disclosed stub.** No export endpoint exists
  on the backend yet; the button says so rather than silently doing
  nothing or downloading something fake.
- **The sign-out dialog's exact new wording is English-only** (same
  reason as chunks 2-3 below) — the other four languages still show
  the chunk-1 wording for that one dialog until someone translates the
  new copy.
- **Explorer Points (+30) and the level thresholds (Explorer /
  Pathfinder / Local Guide / Insider / Pioneer at 0/3/8/16/31 approved
  contributions) are a flat, provisional placeholder**, not a formula
  from the spec (which doesn't give one) — flagged here and in
  `personal/README_PERSONAL.md` as something to tune once there's real
  usage data, not a blueprint number.

## Run it

```
flutter pub get
flutter run --dart-define=GZ_API_BASE_URL=http://<your-backend-host>:8000
```

If you omit `--dart-define`, it defaults to `http://localhost:8000` (or
`http://10.0.2.2:8000` automatically on the Android emulator). Point it at
wherever `uvicorn main:app` from the backend chunk is actually running.

### New permissions chunk 2 needs

This project ships as a `lib/`-only skeleton (no `android/`/`ios/` folders
generated yet — same as chunk 1). Once you run `flutter create .` to
generate those, add:

- **Android** (`android/app/src/main/AndroidManifest.xml`, inside `<manifest>`):
  ```xml
  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
  <uses-permission android:name="android.permission.CAMERA" />
  ```
- **iOS** (`ios/Runner/Info.plist`):
  ```xml
  <key>NSLocationWhenInUseUsageDescription</key>
  <string>GroundZero uses your location to build your itinerary and guide you during your trip.</string>
  <key>NSCameraUsageDescription</key>
  <string>GroundZero uses your camera to add photos to your trip journal.</string>
  ```

## What's real vs. placeholder

- Chunk 1's home/about/how-it-works/auth: fully built, real copy, five
  languages, light/dark/automatic theme.
- Chunk 2's survey → itinerary → live trip → journal: every screen calls
  the real `/trips/*` backend (`trips/routes.py`) — no mock data. This was
  checked against a running backend with real Mangaluru place data (see
  `trips/README_TRIPS.md` on the backend for exactly what was run).
- Chunks 2 and 3 are **English-only**. Chunk 1's public pages are still
  fully translated in all 5 languages; adding their UI text to
  `tools/gen_strings.py`'s 5-language table was cut for time rather than
  half-done — every new user-facing string in `lib/screens/new_trip/`
  and `lib/screens/explore/` is a plain English literal, clearly
  grep-able (`grep -rn "Text('" lib/screens/new_trip/ lib/screens/explore/`)
  if you want to move them into the translation table later.
- Chunk 2's deferred items, and why, are documented in the backend's
  `trips/README_TRIPS.md`. Chunk 3's are documented in the backend's
  `explore/README_EXPLORE.md` and its own "What's simplified here"
  section above. Chunk 4's are documented in the backend's
  `personal/README_PERSONAL.md` and its own "What's simplified here"
  section above.
- Chunk 4's new screens (`lib/screens/personal/`, the enhanced
  `journal_screen.dart`, the rebuilt `start_screen.dart` and
  `settings_screen.dart`) call the real `/trips`, `/trips/{id}/story`,
  `/personal/contributions`, `/personal/notifications`, and
  `DELETE /auth/me` endpoints — no mock data. Verified against a real
  backend with a real trip taken all the way through (survey ->
  itinerary -> confirm -> arrive -> checkout -> journal entry), a real
  community-place submission, and a real admin approval. See the
  backend README's "What was verified live (this chunk)" section for
  the exact sequence run.
- Chunks 2, 3, and 4 are **English-only**, for the same reason: chunk 1's
  public pages are still fully translated in all 5 languages, and
  adding each new chunk's UI text to `tools/gen_strings.py`'s
  5-language table was cut for time rather than half-done. Every new
  user-facing string in `lib/screens/new_trip/`, `lib/screens/explore/`,
  and `lib/screens/personal/` is a plain English literal, clearly
  grep-able (`grep -rn "Text('" lib/screens/new_trip/ lib/screens/explore/ lib/screens/personal/`)
  if you want to move them into the translation table later. The one
  exception is the sign-out dialog's wording, which chunk 4 changed in
  place (see above) — its English value was updated for all 5
  languages' shared key, but the translated text for the other 4
  languages is now one chunk behind English for that one dialog.

## One thing I could not do here

This sandbox has no Flutter/Dart SDK, and the network policy blocks the
Google Cloud Storage host Flutter needs to download the SDK — so across
all four chunks I could not run `flutter pub get`, `flutter analyze`, or
`flutter test` on this code. What I *could* do, and did, every chunk:
balanced every brace/paren/bracket programmatically across every new or
changed file, manually traced every layout for known Flutter crash
patterns, and actually ran the backend each chunk talks to end-to-end
(real Postgres, real place data, real HTTP calls through every screen's
flow) so the contract each screen depends on is verified even though
the screen itself isn't. Please run `flutter pub get && flutter analyze`
first thing on your machine and tell me what, if anything, it flags —
chunk 2 added `flutter_map`, `latlong2`, `geolocator`, and
`image_picker`; chunk 4 adds no new packages (it reuses all of these).

## Structure

```
lib/
  core/        theme, locale, API client, auth session state,
               trips/explore/personal API clients
  widgets/     top bar, language picker, theme picker
  screens/     home, about, how-it-works, auth, start, settings
  screens/new_trip/   survey, itinerary+map, active trip, journal (chunk 2,
                       journal enhanced with tabs+stats in chunk 4)
  screens/explore/    mood-first discovery, search, place detail (chunk 3)
  screens/personal/   my trips, journey story, journal hub, notifications,
                       contributions, add-a-place (chunk 4)
tools/
  gen_strings.py   generates lib/core/strings.dart — edit S{} there, not the .dart file
```
