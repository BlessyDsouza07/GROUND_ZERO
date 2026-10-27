import json
from pathlib import Path
from .config import SOURCES_FILE
from .models import Source, SourceSnapshot, now
from .adapters.st_aloysius import StAloysiusAdapter
import hashlib

def load_registry():
    return json.loads(Path(SOURCES_FILE).read_text(encoding="utf-8"))

def adapter_for(source):
    if "events.staloysius.edu.in" in source.base_url:
        return StAloysiusAdapter(source.base_url)
    raise ValueError(f"No adapter registered for {source.base_url}")

def sync_sources(db):
    for item in load_registry():
        s = db.query(Source).filter_by(name=item["name"]).one_or_none()
        if not s:
            s = Source(name=item["name"], base_url=item["base_url"], source_type=item["source_type"], enabled=item["enabled"])
            db.add(s)
        else:
            s.base_url = item["base_url"]; s.enabled = item["enabled"]; s.source_type = item["source_type"]
    db.commit()

def collect_all(db):
    sync_sources(db)
    results = []
    for source in db.query(Source).filter_by(enabled=True).all():
        try:
            events = adapter_for(source).collect()
            source.last_success_at = now()
            source.last_error = None
            source.last_count = len(events)
            db.add(SourceSnapshot(source_id=source.id, url=source.base_url, http_status=200,
                                  content_hash=hashlib.sha256(str(len(events)).encode()).hexdigest(), event_count=len(events)))
            results.append((source, events, None))
        except Exception as exc:
            source.last_error_at = now()
            source.last_error = str(exc)[:2000]
            results.append((source, [], str(exc)))
    db.commit()
    return results
