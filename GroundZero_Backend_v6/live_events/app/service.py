import json
from datetime import datetime, timezone
from sqlalchemy import select
from .models import Event, EventUpdate
from .collector import collect_all

FIELDS = ["title","description","start_at","end_at","venue","address","city","mode","audience","itinerary_eligible","status","source_url","raw_hash"]

def refresh(db):
    results = collect_all(db)
    inserted = updated = 0
    for source, items, error in results:
        for item in items:
            existing = db.query(Event).filter_by(source_id=source.id, source_event_key=item["source_event_key"]).one_or_none()
            if existing is None:
                db.add(Event(source_id=source.id, first_seen_at=datetime.now(timezone.utc), last_verified_at=datetime.now(timezone.utc), **item))
                inserted += 1
            else:
                changes = {}
                for f in FIELDS:
                    old = getattr(existing, f)
                    new = item[f]
                    if old != new:
                        changes[f] = {"old": str(old), "new": str(new)}
                        setattr(existing, f, new)
                existing.last_verified_at = datetime.now(timezone.utc)
                if changes:
                    db.add(EventUpdate(event_id=existing.id, change_type="FIELDS_CHANGED", details=json.dumps(changes, ensure_ascii=False)))
                    updated += 1
    db.commit()
    return {"inserted": inserted, "updated": updated, "sources": [{"name": s.name, "count": len(items), "error": err} for s, items, err in results]}

def freshness_status(event, max_age_hours):
    age = datetime.now(timezone.utc) - event.last_verified_at
    return "STALE" if age.total_seconds() > max_age_hours * 3600 else event.status
