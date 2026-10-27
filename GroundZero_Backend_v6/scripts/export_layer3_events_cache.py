#!/usr/bin/env python3
"""
Live Events module -> Layer 3 `nearby_events` signal bridge.

Layer 3's SignalSources._all_events() (layer3/layer3_sources.py) already
reads a `live_events_cache.json` file from Layer 0's data directory as one
of its live-signal sources (Blueprint §8.1's Tier B "nearby_events" signal,
weight 0.09, and its crowd-estimation bump for big/festival-type events —
see BIG_EVENT_KEYWORDS in layer3/layer3_config.py). That file simply didn't
exist before (Layer 0's own event_rss_collector left `data/events_cache.json`
empty), so the signal was always a silent `SourceUnavailable`.

This script closes that gap using the `live_events/` module (GroundZero
Live Mangaluru Events) as the source of truth: it reads that module's own
live-collected-events database directly (same process, no HTTP
round-trip) and writes the exact flat-list shape layer3_sources.py's
_all_events()/events_near() already knows how to parse (see its docstring
and pget() key lists: title/name/summary, start/start_date/..., lat/lng,
venue, place_id, ...).

2026-09-24: the events module was replaced with a NO-SEED version (every
Event row comes only from a live adapter fetch — see live_events/app/seed.py
and live_events/tests/test_no_seed.py) and its schema changed: there is no
longer a per-event `verification_status`/`category`/`organizer` field.
Freshness is judged the same way the module's own /events endpoint judges
it (live_events/app/service.py::freshness_status) — an event whose
last_verified_at is older than MAX_EVENT_AGE_HOURS is STALE and excluded
here, since a stale row is one the live refresh loop couldn't re-confirm,
not a currently-real one.

Deliberately includes every fresh, ACTIVE event regardless of
`itinerary_eligible` — Layer 3 only uses this feed for situational
awareness (crowding near a place, "there's a festival on") and NEVER
inserts events into a tourist's itinerary itself, so the same
itinerary_eligible=false academic/student events this module's own
parser correctly marks non-eligible for trip-planning are still fair,
honest signal for "expect a bit more foot traffic here".

Output: layer0/data_output/live_events_cache.json — the exact filename
layer3_config.py's `live_events_cache_file` default already expects,
alongside the master_data_core.json export in the same directory (see
export_layer3_master_core.py), so Layer 3 finds both with zero
configuration.

Run standalone:
    python scripts/export_layer3_events_cache.py

Or import and call `export_layer3_events_cache()` (main.py calls this once
at startup and then periodically via the events module's own scheduler —
see main.py's lifespan).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "layer0" / "data_output" / "live_events_cache.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _event_to_l3_dict(row: Any, source_name: str) -> Dict[str, Any]:
    """One live_events.app.models.Event row -> the flat dict shape
    layer3_sources.py's pget()-based readers expect. Every value here maps
    to a key layer3_sources.events_near()/_all_events() already reads by
    name — see its `pget(e, "title", "name", "summary", ...)` etc. chains.
    The new (no-seed) Event model has no `category`/`organizer`/
    `verification_status` fields, and `source_name` now lives on the
    joined Source row rather than denormalized onto Event -- see
    export_layer3_events_cache() below, which passes it in."""
    return {
        "title": row.title,
        "name": row.title,
        "description": row.description,
        "start": row.start_at.isoformat() if row.start_at else None,
        "end": (row.end_at.isoformat() if row.end_at else None),
        "venue": row.venue,
        "place": row.venue,
        "location": row.address or row.venue,
        "mode": row.mode,
        "audience": row.audience,
        "itinerary_eligible": bool(row.itinerary_eligible),
        "source_name": source_name,
        "source_url": row.source_url,
        # No geocoding is performed on venue/address (never invent
        # coordinates for a source we haven't verified) — Layer 3's
        # events_near() already has a documented fallback for events with
        # no lat/lng: substring-matching the place name against this
        # event's combined title/description/location/place/venue text.
        "lat": None,
        "lng": None,
    }


def export_layer3_events_cache(dest_path: Path = DEFAULT_DEST) -> Dict[str, Any]:
    """Read the Live Events module's DB, write Layer 3's events cache.
    Returns a small stats dict. Never raises for "no events yet" or "DB
    not initialized yet" — Layer 3 already treats a present-but-empty
    cache file as a legitimate zero-events answer (not a data gap), and an
    events DB that hasn't been created yet (very first boot, before the
    events module's own init_db() has run) just means zero events so far."""
    from datetime import datetime, timezone, timedelta

    from sqlalchemy import select

    from live_events.app.config import MAX_EVENT_AGE_HOURS
    from live_events.app.db import SessionLocal
    from live_events.app.models import Event, Source

    dest_path = Path(dest_path)
    events: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_EVENT_AGE_HOURS)
        sources_by_id = {s.id: s.name for s in db.scalars(select(Source)).all()}
        rows = db.scalars(
            select(Event).where(
                Event.status == "ACTIVE",
                Event.start_at.is_not(None),
                Event.last_verified_at >= freshness_cutoff,
            )
        ).all()
        events = [_event_to_l3_dict(r, sources_by_id.get(r.source_id, "unknown")) for r in rows]
    finally:
        db.close()

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    return {"dest": str(dest_path), "total_events": len(events)}


if __name__ == "__main__":
    from live_events.app.db import init_db

    init_db()  # safe / idempotent if the events DB doesn't exist yet
    stats = export_layer3_events_cache()
    print(f"Layer 3 events cache written: {stats['dest']} ({stats['total_events']} events)")
