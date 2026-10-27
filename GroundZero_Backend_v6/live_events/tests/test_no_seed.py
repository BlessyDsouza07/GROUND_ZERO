from pathlib import Path
import json

def test_no_seed_event_file():
    root = Path(__file__).parents[1]
    assert not (root / "data" / "verified_seed.json").exists()

def test_source_registry_contains_no_events():
    root = Path(__file__).parents[1]
    data = json.loads((root / "data" / "sources.json").read_text(encoding="utf-8"))
    assert all("events" not in x for x in data)
