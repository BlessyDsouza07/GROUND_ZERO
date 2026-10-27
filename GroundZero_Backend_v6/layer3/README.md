# Ground Zero — Layer 3

**Context Engine + Silence Filter + Ask Engine (Layer 3B), combined into one service.**

This is the layer that decides *when the app is allowed to speak*, what it says, in what
language and voice, and that answers a tourist's questions about a place — grounded only in
what Layer 0 actually recorded. Everything here is read-only towards Layers 0, 1 and 2: this
package never modifies their files, tables, or code.

If you've read the project docs, this implements **Blueprint Section 6 (Context Engine),
Section 6.2–6.5 (Safety Override, Replan Trigger, Etiquette Whisper, "I'm Already Here"), and
Section 7 (Ask Engine)** — plus everything those sections lean on (opening hours, live weather,
tide, crowd, events).

---

## 1. What's in this zip

```
layer3/
├── layer3_config.py            Settings (env-driven), vocabulary, weights, thresholds
├── layer3_utils.py              Geo maths, time helpers, opening-hours parser, TTL cache
├── layer3_models.py             Dataclasses / enums shared across the layer (Decision, CheckResult, ...)
├── layer3_repository.py         Layer 3's OWN database tables (SQLAlchemy) — sessions, pings, notifications...
├── layer3_bridge.py              READ-ONLY bridge to Layer 0 (master_data_core.json), Layer 1 (profiles), Layer 2 (HIVE)
├── layer3_sources.py             Live weather / tide / events / crowd / advisories (Redis -> Layer 0 cache -> free API)
├── layer3_safety.py              Safety override — the 3 defined sources (weather / advisory / SOS)
├── layer3_context_engine.py      Tier A (hard blockers) + Tier B (9 weighted signals)
├── layer3_silence_filter.py      All the ways the app stays quiet (Quiet Hours, geofence lock, group gate...)
├── layer3_geofence.py            300 m proximity matching + the manual "I'm here" trigger
├── layer3_replan.py              Replan Trigger — real-time re-scoring when a place is unavailable
├── layer3_i18n.py                English / Kannada / Konkani / Hindi strings & templates
├── layer3_companion_voice.py     Builds the ONE sentence + etiquette whisper + "Tell me more"
├── layer3_llm.py                 Optional Groq LLM client (Ask Engine phrasing, translation)
├── layer3_ask_engine.py          Ask Engine — grounded Q&A, deterministic swim-safety rules
├── layer3_orchestrator.py        Ties everything together — the class Layer 4 / the API actually calls
├── layer3_api.py                 FastAPI app — the HTTP surface (Swagger at /docs)
├── layer3_client.py              Tiny Python client for Layer 4 to import (no Layer 3 logic duplicated)
├── run_layer3.py                 CLI: --serve / --demo / --status / --healthcheck / --ask / --test-voice
├── requirements.txt               pinned-by->= dependencies
├── .env.example                   every environment variable, documented
├── pytest.ini
├── Dockerfile / docker-compose.yml
├── scripts/make_sample_data.py    regenerates sample_data/
├── sample_data/                   16-place mini master_data_core.json + a sample profile + itinerary
└── tests/test_layer3.py           56 tests, fully offline (mock network + temp SQLite)
```

Nothing else is needed to run this layer on its own. When it's dropped next to Layers 0/1/2 on
a teammate's machine, it auto-discovers them (see §3).

---

## 2. Install & first run (5 minutes)

```bash
cd layer3
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. See it work completely offline, on bundled sample data, no other layer required:
python run_layer3.py --demo

# 2. Run the test suite (56 tests, all offline):
python -m pytest -q

# 3. Start the real HTTP service:
cp .env.example .env        # edit paths if your layout differs from §3
python run_layer3.py --serve
# -> http://localhost:8004/docs  (interactive Swagger UI — try every endpoint from the browser)
```

`--demo` and the test suite need **no internet, no Layer 0/1/2, no API keys** — they mock the
weather/tide network calls and use the bundled `sample_data/`. This is the fastest way to
convince yourself (or a reviewer) that the whole decision pipeline works end to end.

---

## 3. Wiring it to Layers 0, 1, 2 (what your teammate needs to do)

Layer 3 **auto-discovers** Layer 0's export by looking for one of these relative to wherever
`layer3/` sits, in this order:

```
../layer0_fixed/data_output/master_data_core.json
../layer0/data_output/master_data_core.json
../data/master_data_core.json
../data_output/master_data_core.json
```

So the simplest integration is: put `layer3/` in the same parent folder as `layer0_fixed/`,
`layer1/`, `layer2/` (exactly how the technical explainer describes the project layout), and it
just works:

```
GroundZero/
├── layer0_fixed/
│   └── data_output/master_data_core.json   <- Layer 3 reads this
├── layer1/
│   └── data_output/profiles/<id>.json      <- Layer 3 reads this (or calls Layer 1's API)
├── layer2/                                  <- Layer 3 calls POST /hive/generate on this
└── layer3/                                  <- you are here
```

If your folder layout differs, set the paths explicitly in `.env` — nothing needs auto-discovery:

```bash
LAYER0_MASTER_CORE_PATH=/absolute/or/relative/path/to/master_data_core.json
LAYER0_DATA_DIR=/path/to/layer0_fixed/data_output      # for live_tide_cache.json / live_events_cache.json
LAYER0_DB_PATH=/path/to/layer0_fixed/data_output/ground_zero.db
LAYER1_PROFILES_DIR=/path/to/layer1/data_output/profiles
LAYER1_BASE_URL=http://localhost:8002
LAYER2_BASE_URL=http://localhost:8003
```

**Nothing in Layers 0/1/2 needs to change.** Layer 3 reads:
- Layer 0's `master_data_core.json` (the only thing it strictly requires — see §7),
- optionally Layer 0's live caches (`live_tide_cache.json`, `live_events_cache.json`) if they exist,
- optionally Layer 0's `ground_zero.db` `places.temporarily_unavailable` column directly, read-only,
  for real-time closures reported between export runs (`LAYER3_USE_LAYER0_DB_FLAGS=true`, the default),
- Layer 1's saved profile JSON files, or its `/profile/{id}` endpoint as a fallback,
- Layer 2's `/hive/generate` endpoint, **only when you start a session by `profile_id`** (see §4).

Layer 3 **never** writes into any of their files or tables. Its own state lives in its own
tables (prefixed `l3_`) in its own SQLite file by default (`data_output/layer3.db`), or inside
`ground_zero.db` as separate tables if you set `LAYER3_SHARE_GROUND_ZERO_DB=true` — either way,
Layer 0/1/2's own tables are never touched.

### Layer 4 integration

Layer 4 doesn't exist yet in this codebase, but Layer 3 is built specifically so it slots in
cleanly: `layer3_client.py` is a small dependency-free wrapper around the HTTP API. Layer 4
would import it like this:

```python
from layer3_client import Layer3Client
l3 = Layer3Client("http://localhost:8004")

sid = l3.start_session(profile_id="abc123")["session_id"]

# every ~30-60s while the trip is active, or on every GPS update:
decision = l3.evaluate(sid, lat, lng, accuracy_m=12)
if decision["decision"] in ("speak", "safety_alert"):
    push_notification(decision["message"])      # hand off to FCM / whatever Layer 4 uses
# else: do nothing until decision["retry_after_seconds"] has passed
```

The full Layer 4 -> Layer 3 event map (Stop/Pause, mood check-in, wallet, Pace Coach, Quiet
Hours, SOS...) is documented as a comment at the top of `layer3_client.py`.

---

## 4. The core workflow, end to end

```
Layer 1 profile_id  ──┐
                       ├──► POST /l3/session/start ──► Layer 3 queue (flattened slot list)
Layer 2 itinerary  ────┘         (calls Layer 2's /hive/generate for you if you only give profile_id)

                     Layer 4 sends a GPS ping every ~10-30s while the trip is active
                                        │
                                        ▼
                         POST /l3/location/ping   (stored — needed for the "stopped" check)

                     Layer 4 calls this on every ping (or on a timer):
                                        │
                                        ▼
                       POST /l3/context/evaluate  ◄── THE decision (see §5)
                                        │
                        ┌───────────────┼────────────────┐
                        ▼               ▼                ▼
                  decision: silent  decision: speak  decision: safety_alert
                  (retry_after_s)  (companion_voice)  (bypasses everything)

                     Tourist taps "Tell me more"  ──► POST /l3/notify/tell-more
                     Tourist asks a question       ──► POST /l3/ask
                     Tourist dismisses / engages    ──► POST /l3/notify/dismiss | /engage
                     Tourist leaves the place        ──► POST /l3/visit
```

A session can also be started directly with an already-flattened `queue` (useful for testing,
or if Layer 4 keeps the authoritative queue itself and just wants Layer 3's decision engine —
see `PUT /l3/session/{id}/queue`).

---

## 5. How the decision to notify is actually made

This is the heart of the layer (`layer3_orchestrator.py::evaluate`, blueprint §6 / §12.2).
**First "stay silent" wins** — the checks run in this exact order:

| # | Gate | What it checks | On failure |
|---|------|-----------------|------------|
| 0 | **Safety override** | weather API severe alert, authority advisory, or manual SOS | `safety_alert` — breaks through *everything*, including Quiet Hours |
| 1 | Session active? | `status == "active"` (not `paused`/`ended_early`/`completed`) | silent, no retry |
| 2 | Quiet Hours | tourist muted the app | silent until `quiet_until` |
| 3 | Find a target slot | 300 m geofence (or manual "I'm here", which only skips this one check) | silent if nothing pending in range |
| 4 | **Replan Trigger** | is the target place `temporarily_unavailable`? | swaps in the next-best place of the *same role*, keeps going with the substitute |
| 5 | Geofence silence | already notified about this place / still standing in its ~120 m boundary | silent — "once inside a place's boundary, the app sends nothing" |
| 6 | Group gate | an `ANCHOR` (meal) slot waits for every active group member to be nearby | silent, lists who it's waiting for |
| 7 | **Tier A** (hard blockers, ALL must pass) | fatigue gap (8 min, 15 after 2 dismissals); movement < 1 km/h for 2 min | silent, retry in ~90s (or the remaining fatigue gap) |
| 8 | **Tier B** (weighted signals, avg ≥ 0.75) | 9 signals — see below | silent if below threshold or too much missing data |
| — | **SPEAK** | exactly one companion_voice sentence (+ optional etiquette whisper) | notification recorded, geofence lock set |

### Tier B — the 9 weighted signals

| Signal | What decides the score | Data source |
|---|---|---|
| `time_of_day` | is this category sensible at this hour? (also checks `opening_hours` if present) | place record + local clock |
| `weather` | outdoor vs indoor place vs current rain/storm/heat | Open-Meteo (free, no key) |
| `crowd_level` | tourist's stated tolerance vs current crowd | Redis → place record → 5-signal estimate (time/weekday/weather/season/events) |
| `energy_compatibility` | tourist's energy_band vs the place's energy_requirement | Layer 1 profile / mid-trip mood update |
| `mood_compatibility` | recent dismissal streak; recent "tired" mood update | Layer 3's own session state |
| `season_day_type` | monsoon-unfriendly outdoor spots score lower in monsoon; weekend crowding | place record + calendar |
| `tide_state` | wave height / sea state — **only for coastal places** | Layer 0's `live_tide_cache.json` → Open-Meteo Marine |
| `nearby_events` | is a big local event about to swamp this place? | Layer 0's `live_events_cache.json` |
| `dwell_history` | already visited, or a near-duplicate already visited today | Layer 3's visit log |

A signal that doesn't apply (tide for an inland temple) or whose source is unreadable right now
is **dropped and the remaining weights re-normalise** — a single flaky API (e.g. the tide feed
returning null) never silences the whole app the way one all-or-nothing AND would. Every dropped
signal is still listed honestly in the response's `tier_b.data_gaps`, and the safety check
reports `checked: false` rather than a fake "all clear" when a source is down. If fewer than 5
signals are available at all, Layer 3 stays silent (`insufficient_signal_data`) rather than guess.

---

## 6. The companion voice, "Tell me more", and Ask Engine — in detail

### Companion voice (exactly one sentence)

Pre-templated per **language × voice personality**, deterministic and free — no internet or API
key needed. The hook it picks is chosen only from the stored record:

- **`age`** — if a build/founding year can be found in `wikidata_facts` or the Wikipedia extract
  ("Milagres Church is a 346-year-old church right ahead of you...")
- **`hidden`** — if the place has very few media mentions / mostly local visitors / a very low
  `bias_index` ("...is a market most visitors walk straight past...")
- **`generic`** — otherwise

If `etiquette_tag` is set on the place, one extra sentence is appended in the *same* delivery
(never a second notification), translated into the tourist's language:
`"Milagres Church is a 346-year-old church... Quick note: shoulders should be covered before entering."`

Languages: **English, Kannada, Konkani (Devanagari script), Hindi.** Voices: **warm / historian /
witty.** Set `LAYER3_VOICE_USE_LLM=true` (needs `GROQ_API_KEY`) to let the LLM polish the line
further — it still only sees the place's own record, and any output that looks unsafe (too long,
contains a newline) is discarded in favour of the template.

> **Text-to-speech**: Layer 3 returns `tts_locale` (`en-IN` / `kn-IN` / `hi-IN`) on every message
> so a mobile client can feed the text straight to the platform TTS engine (Android
> `TextToSpeech`, iOS `AVSpeechSynthesizer`, or a web `SpeechSynthesisUtterance`). Layer 3 itself
> does not synthesise audio — that's a client-side concern, and doing it there means it works
> offline for the parts of the trip in the plane.

### "Tell me more"

Purely opt-in depth (`POST /l3/notify/tell-more`). Returns 2-3 **additional** sentences (never
repeating the one already spoken) from `wikipedia_extract`, or a short fact list from
`wikidata_facts` if there's no extract. If the tourist's language isn't English and the record's
description is, and an LLM is configured, it's translated; otherwise the response says so
honestly (`note: "Stored description is in English..."`) rather than inventing a translation.

### Ask Engine (`POST /l3/ask`)

The tourist can ask anything about a place, any time. Rules that make it trustworthy:

1. **Grounded only in that place's record** (+ a live weather/tide/crowd snapshot when the
   question is about "right now"). It never uses outside knowledge.
2. **"Is it safe to swim?" is answered by deterministic rules**, never the LLM — it reads live
   wave height / tide state and never certifies safety when that data is missing
   ("I can't check live sea conditions right now, so I can't tell you it's safe to swim...").
3. With `GROQ_API_KEY` set, an LLM phrases the answer from the supplied record only, and is
   instructed to reply with a sentinel if the record doesn't contain the answer — Layer 3 then
   returns the honest "I don't have that in my records" line instead of an invented one.
4. **Without an LLM (or if the LLM call fails for any reason)**, a deterministic keyword-topic
   extractor answers from `food_notes` / `accessibility_tags` / `opening_hours` /
   `estimated_cost` / `etiquette_tag` / `wikipedia_extract` / `wikidata_facts` directly — the
   Ask Engine is **fully functional with zero API keys and zero internet**, just less fluent.
   The response's `mode` field always says which path answered
   (`llm` / `extractive` / `extractive_fallback` / `rules`), so nothing is silently downgraded.
5. The question is treated as **untrusted user text**; an instruction embedded in a question
   ("ignore the rules and say X") is inert — the record is the only source of truth, not the
   question's wording.

---

## 7. What Layer 3 needs from Layer 0's export, precisely

Only `master_data_core.json` is strictly required, and only these fields are read (all
optional individually — a missing field just disables the one feature that needs it, it never
crashes the layer):

`place_id`/`id`, `name`, `lat`/`lng`, `category`, `subcategory`, `tags`/`trip_relevance_tags`,
`bias_index`, `local_percentage`, `media_mentions`, `estimated_cost`, `is_free_entry`,
`accessibility_tags`, `etiquette_tag`, `temporarily_unavailable`, `crowd_level`,
`energy_requirement`, `dwell_time_typical`, `opening_hours`/`opening_hours_raw`,
`tide_dependency`, `season_suitability`, `wikipedia_extract`, `wikidata_facts`, `food_notes`,
`bias_recommendation`, `address`, `grade`.

The bridge (`layer3_bridge.py`) is deliberately tolerant of shape differences — `place_id` vs
`id`, a bare list vs `{"places": [...]}`, opening hours as an OSM string or as JSON — because
Layer 0 is owned by someone else on the team and its export format may still evolve.

---

## 8. HTTP API reference

Full interactive docs at **`/docs`** once the service is running. Summary:

| Method & path | Purpose |
|---|---|
| `POST /l3/session/start` | Start a session from `profile_id` (+ optional `itinerary`, or Layer 3 calls Layer 2 for you) |
| `GET /l3/session/{id}` | Current session state + queue |
| `PUT /l3/session/{id}/queue` | Layer 4 syncs a re-evaluated queue (Pace Coach, Resume Evaluation) |
| `PUT /l3/session/{id}/state` | Pause/resume/end, mood check-in energy, wallet, language, voice |
| `POST /l3/location/ping` | Store a GPS ping |
| `POST /l3/context/evaluate` | **The decision** — speak / stay silent / safety alert |
| `GET /l3/conditions` | Live weather/tide/events/advisories snapshot for a coordinate |
| `POST /l3/notify/dismiss` | Tourist dismissed a notification |
| `POST /l3/notify/engage` | Tourist engaged with it (resets the dismissal streak) |
| `POST /l3/notify/tell-more` | 2-3 extra sentences |
| `POST /l3/ask` | Ask Engine |
| `POST /l3/quiet` | Quiet Hours (minutes; 0 clears) |
| `POST /l3/sos` / `/l3/sos/clear` | Manual SOS |
| `POST /l3/visit` | Record arrival/exit/dwell/👍👎 |
| `GET /l3/visits/{device_id}` | For Layer 1's Return Visitor check |
| `POST /l3/place/report-unavailable` | Community "this is closed" report (Layer 3's own overlay) |
| `POST /l3/safety/advisory` [admin] | Publish/mirror a local-authority advisory |
| `GET /l3/health`, `/health`, `/status` | Health checks |

All error responses are `{"error": {"code": "...", "message": "..."}}` with an appropriate HTTP
status (404 for missing sessions/places, 422 for bad input, 409 for illegal state transitions,
503 if `master_data_core.json` can't be found at all).

---

## 9. Configuration

Everything is env-driven (see `.env.example` for the full, documented list) with sensible
defaults — the service runs with **zero configuration** for the demo/test path. Highlights:

- `LAYER3_PORT` (default 8004 — Layer 1 uses 8002, Layer 2 uses 8003)
- `LAYER0_MASTER_CORE_PATH`, `LAYER1_PROFILES_DIR`, `LAYER1_BASE_URL`, `LAYER2_BASE_URL` — see §3
- `REDIS_URL` — optional; if unset, Layer 3 calls the free APIs directly (still fully functional)
- `GROQ_API_KEY` — optional; if unset, the Ask Engine and voice both use their deterministic paths
- `LAYER3_GEOFENCE_RADIUS_M` (300), `LAYER3_TIER_B_THRESHOLD` (0.75), `LAYER3_FATIGUE_GAP_MIN` (8),
  `LAYER3_MOVEMENT_MAX_KMH` (1.0) — the exact blueprint numbers, all overridable
- `LAYER3_API_KEY` / `LAYER3_ADMIN_TOKEN` — optional auth for a shared/demo deployment

---

## 10. Design notes for whoever builds Layer 4 next

- **Idempotent by construction.** Re-sending the same GPS ping, or calling `/evaluate` twice in
  the same second, never double-notifies — a slot moves to `notified` the instant a message is
  sent, and the geofence lock stops the loop from re-triggering while the tourist is still there.
- **`dry_run: true`** on `/context/evaluate` runs the *entire* pipeline (including live API
  calls) without writing anything — perfect for a "what would happen right now?" debug view or
  for Layer 4's own simulation/testing.
- **Time override** (`now` field) is honoured only when `LAYER3_ALLOW_TIME_OVERRIDE=true` — keep
  that off in any shared/demo deployment; it exists for tests and the `--demo` script.
- **The Replan Trigger's re-scoring is self-contained** (`layer3_replan.py`) — it doesn't call
  Layer 2. This is intentional: a real-time swap needs to be fast and can't afford a network
  round-trip to HIVE, so it re-implements the blueprint's 5-component Personal Fit Score
  (§5.2/§12.1) directly. Layer 2's own 16-component scorer is still what builds the *original*
  itinerary; Layer 3 only re-scores the leftover candidate pool when something goes offline.
- **Everything Layer 3 concludes is JSON-serialisable and carries an honest provenance flag**
  (`estimated: true/false`, `mode: "llm"/"extractive"/"rules"`, `data_gaps: [...]`) so Layer 4 or
  a debugging UI never has to guess whether a number came from a live sensor or a heuristic.

---

## 11. Known deliberate simplifications (documented, not hidden)

- Kannada / Konkani / Hindi strings in `layer3_i18n.py` are careful first drafts, not verified by
  a native reviewer yet. Fix any string without touching code via
  `data_output/i18n_overrides.json` (see the module docstring) — useful right before a demo.
- The advisory feed integration parses generic RSS/Atom/CAP XML and filters by keyword; no
  specific Karnataka government feed URL is hard-coded because none with a stable public URL was
  confirmed at the time of writing — set `LAYER3_ADVISORY_FEED_URL` to whichever one your team
  finds, or just use `POST /l3/safety/advisory` to mirror advisories manually for a demo.
- Crowd level falls back to a 5-signal estimate (matching Layer 0's own `crowd_engine.py`
  approach) when no live/place-record value exists — this is clearly flagged as
  `"estimated": true` everywhere it appears, never presented as a live reading.
