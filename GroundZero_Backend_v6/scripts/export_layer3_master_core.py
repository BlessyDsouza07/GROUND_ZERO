#!/usr/bin/env python3
"""
Ground Zero — Layer 0 -> Layer 3 master-data adapter.

Layer 3 (layer3/layer3_bridge.py) is a READ-ONLY consumer of Layer 0's
`master_data_core.json` export. Its field-reading helpers
(`layer3_utils.pget`, `place_latlng`, ...) look for a set of TOP-LEVEL
keys (flat `lat`/`lng`, flat `local_percentage`, flat `accessibility_tags`,
...) — see layer3/README.md §7 for the exact list.

Layer 0's actual export (`data/master_data_core.json`) nests some of that
same information one level down (`coordinates.latitude`, `bias_signals
.local_percentage`, `accessibility.tags`, ...) and names a couple of
fields differently (`dwell_time_typical_minutes` vs `dwell_time_typical`,
`wiki_summary` vs `wikipedia_extract`). Both shapes are legitimate — they
were designed independently, exactly the situation layer3_bridge.py's
own docstring anticipates ("Layers 0-2 are owned by other people and
evolve independently").

This script is the bridge's missing half: it reads Layer 0's real export
and writes a Layer-3-flavoured copy — same data, nothing invented, just
flattened/aliased/renamed so every field layer3_bridge.py already knows
how to read is where it expects to find it. It never modifies
`data/master_data_core.json` itself, and it never touches any Layer 0/1/2
file, table or code.

Output path defaults to `layer0/data_output/master_data_core.json`, which
is exactly layer3_config.py's #2 auto-discovery candidate
(`../layer0/data_output/master_data_core.json` relative to `layer3/`) —
so once this has been run, Layer 3 finds it with zero configuration.

Run standalone:
    python scripts/export_layer3_master_core.py

Or import and call `export_layer3_master_core()` (main.py calls this once
at startup so the copy Layer 3 reads is always fresh — see main.py).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "data" / "master_data_core.json"
DEFAULT_DEST = REPO_ROOT / "layer0" / "data_output" / "master_data_core.json"

# Ground Zero's canonical place-category vocabulary (shared/place_taxonomy.py)
# -> the coarser Tier-B "purpose" buckets layer3_config.TIME_SUITABILITY and
# layer3_context_engine.outdoor_factor() key off (SPIRITUAL / NATURE /
# EXPLORE / SHOPPING / LOCAL_LIFE / EVENTS / FOOD / DEFAULT). Unmapped
# categories fall through to DEFAULT — never dropped, never guessed at
# beyond this explicit table. The original category is preserved verbatim
# in `subcategory` so nothing is lost and Layer 3's own name/tag keyword
# fallbacks (outdoor_factor, is_coastal) still see it.
_CATEGORY_TO_L3_BUCKET: Dict[str, str] = {
    # spiritual / heritage
    "heritage_site": "SPIRITUAL", "temple": "SPIRITUAL", "church": "SPIRITUAL",
    "mosque": "SPIRITUAL", "shrine": "SPIRITUAL", "basadi": "SPIRITUAL",
    "gurudwara": "SPIRITUAL", "place_of_worship": "SPIRITUAL",
    # culture / sights (indoor-ish browsing)
    "museum": "EXPLORE", "art_gallery": "EXPLORE", "library": "EXPLORE",
    "theatre": "EXPLORE", "craft_centre": "EXPLORE", "tourist_attraction": "EXPLORE",
    "attraction": "EXPLORE", "hidden_gem": "EXPLORE", "landmark_infrastructure": "EXPLORE",
    "monument": "EXPLORE", "fort": "EXPLORE",
    # outdoors / nature
    "beach": "NATURE", "viewpoint": "NATURE", "park": "NATURE", "garden": "NATURE",
    "lake": "NATURE", "nature_spot": "NATURE", "waterfall": "NATURE", "trail": "NATURE",
    "wildlife_area": "NATURE", "boat_ride": "NATURE", "adventure": "NATURE",
    # food
    "restaurant": "FOOD", "cafe": "FOOD", "street_food": "FOOD", "local_kitchen": "FOOD",
    "food_court": "FOOD", "bakery": "FOOD", "dessert_shop": "FOOD",
    # shopping
    "market": "SHOPPING", "shopping_mall": "SHOPPING", "local_shop": "SHOPPING",
    # local life
    "locality": "LOCAL_LIFE", "neighbourhood": "LOCAL_LIFE",
}

_TRUE_STRINGS = {"true", "1", "yes", "y"}
_FALSE_STRINGS = {"false", "0", "no", "n"}


def _as_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _TRUE_STRINGS:
            return True
        if s in _FALSE_STRINGS:
            return False
    return None


def _l3_category_bucket(raw_category: Optional[str]) -> str:
    key = (raw_category or "").strip().lower()
    return _CATEGORY_TO_L3_BUCKET.get(key, "DEFAULT")


def _transform_opening_hours(oh: Any) -> Any:
    """Layer 0 stores {raw, days_open, opens_at, closes_at}. Layer 3's
    parse_opening_hours() understands either a raw OSM string (preferred —
    it's the richer grammar) or a dict with {open, close, days, always}
    keys. Prefer the raw string when present; fall back to the structured
    fields; leave it out entirely (never fabricate) when neither exists."""
    if not isinstance(oh, dict):
        return None
    raw = oh.get("raw")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    opens_at, closes_at = oh.get("opens_at"), oh.get("closes_at")
    if opens_at and closes_at:
        out: Dict[str, Any] = {"open": opens_at, "close": closes_at}
        days = oh.get("days_open")
        if isinstance(days, list) and days:
            out["days"] = days
        return out
    return None


def transform_place(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a NEW dict: every original key preserved, plus the flattened
    / renamed aliases layer3_bridge.py's field readers look for. Additive
    only — nothing from the original record is deleted, except that
    `opening_hours` and `category` are REPLACED (not merely aliased)
    because layer3_utils.pget() picks the first key it finds by name, so
    a stale/incompatible value under the same key name would silently
    win over a same-named alias. Their originals are kept under
    `opening_hours_source` / `subcategory` so nothing is lost."""
    out: Dict[str, Any] = dict(record)

    coords = record.get("coordinates") or {}
    lat, lng = coords.get("latitude"), coords.get("longitude")
    if lat is not None and lng is not None:
        out["lat"] = lat
        out["lng"] = lng

    bias = record.get("bias_signals") or {}
    if "local_percentage" in bias:
        out["local_percentage"] = bias.get("local_percentage")
    if "media_mentions" in bias:
        out["media_mentions"] = bias.get("media_mentions")
    if "commercial_flags" in bias:
        out["commercial_flags"] = bias.get("commercial_flags")
    if "tourist_popularity" in bias:
        out["tourist_popularity"] = bias.get("tourist_popularity")
    if "sponsored_indicator" in bias:
        out["sponsored_indicator"] = bias.get("sponsored_indicator")

    access = record.get("accessibility") or {}
    tags = access.get("tags")
    if isinstance(tags, list):
        out["accessibility_tags"] = tags
    if access.get("wheelchair") is not None:
        out["wheelchair_accessible"] = _as_bool(access.get("wheelchair"))

    if "dwell_time_typical_minutes" in record:
        out["dwell_time_typical"] = record.get("dwell_time_typical_minutes")

    if record.get("wiki_summary"):
        out["wikipedia_extract"] = record.get("wiki_summary")

    price_band = str(record.get("price_band") or "").strip().lower()
    cost = record.get("estimated_cost")
    out["is_free_entry"] = (price_band == "free") or (isinstance(cost, (int, float)) and cost == 0)

    out["opening_hours_source"] = record.get("opening_hours")
    transformed_hours = _transform_opening_hours(record.get("opening_hours"))
    if transformed_hours is not None:
        out["opening_hours"] = transformed_hours
    else:
        out.pop("opening_hours", None)

    out["subcategory"] = record.get("category")
    out["category"] = _l3_category_bucket(record.get("category"))

    return out


def _extract_places(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("places", "data", "items", "records", "master_data_core"):
            v = payload.get(key)
            if isinstance(v, list):
                return [p for p in v if isinstance(p, dict)]
    return []


def export_layer3_master_core(
    source_path: Path = DEFAULT_SOURCE, dest_path: Path = DEFAULT_DEST
) -> Dict[str, Any]:
    """Read Layer 0's export, write the Layer-3-flavoured copy. Returns a
    small stats dict. Raises FileNotFoundError if the source doesn't
    exist yet (e.g. before the ETL / import_master_data.py has ever run) —
    callers (main.py) catch this and just skip, since Layer 3 already
    degrades gracefully with zero places (README §7)."""
    source_path = Path(source_path)
    dest_path = Path(dest_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Layer 0 master data core not found at {source_path}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    places = _extract_places(payload)
    transformed = [transform_place(p) for p in places]

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(transformed, ensure_ascii=False, indent=2), encoding="utf-8")

    with_latlng = sum(1 for p in transformed if p.get("lat") is not None and p.get("lng") is not None)
    with_hours = sum(1 for p in transformed if p.get("opening_hours"))
    return {
        "source": str(source_path),
        "dest": str(dest_path),
        "total_places": len(transformed),
        "with_lat_lng": with_latlng,
        "with_opening_hours": with_hours,
    }


if __name__ == "__main__":
    stats = export_layer3_master_core()
    print(f"Layer 3 master data export written: {stats['dest']}")
    print(
        f"  {stats['total_places']} places | "
        f"{stats['with_lat_lng']} with lat/lng | "
        f"{stats['with_opening_hours']} with parsable opening hours"
    )
