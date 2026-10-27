"""Load the master-data JSON into Place entities (used by tests and the
offline evaluation script; production reads through PlaceRepository)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from layer0.domain.entities import (AccessibilityInfo, BiasSignals, Coordinates, CrowdLevel, DataSource,
                                    EnergyRequirement, Grade, OpeningHours, Place, PriceBand)


def _dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def _enum(cls, v, default=None):
    try:
        return cls(v)
    except Exception:
        return default


def place_from_dict(d: dict) -> Place:
    oh = d.get("opening_hours") or {}
    acc = d.get("accessibility") or {}
    bs = d.get("bias_signals") or {}
    return Place(
        id=d["id"], name=d["name"], category=d.get("category") or "uncategorized",
        coordinates=Coordinates(d["coordinates"]["latitude"], d["coordinates"]["longitude"]),
        opening_hours=OpeningHours(raw=oh.get("raw") or "", days_open=oh.get("days_open") or [],
                                   opens_at=oh.get("opens_at"), closes_at=oh.get("closes_at")),
        price_band=_enum(PriceBand, d.get("price_band"), PriceBand.MODERATE),
        estimated_cost=d.get("estimated_cost") or 0.0, tags=d.get("tags") or [],
        bias_signals=BiasSignals(media_mentions=bs.get("media_mentions", 0), local_percentage=bs.get("local_percentage", 0.0),
                                 commercial_flags=bs.get("commercial_flags", 0), tourist_popularity=bs.get("tourist_popularity", 0.0),
                                 sponsored_indicator=bs.get("sponsored_indicator", False)),
        bias_index=d.get("bias_index"), grade=_enum(Grade, d.get("grade")),
        energy_requirement=_enum(EnergyRequirement, d.get("energy_requirement"), EnergyRequirement.MODERATE),
        crowd_level=_enum(CrowdLevel, d.get("crowd_level"), CrowdLevel.MODERATE),
        season_suitability=d.get("season_suitability") or [], tide_dependency=bool(d.get("tide_dependency")),
        dwell_time_typical_minutes=d.get("dwell_time_typical_minutes") or 45,
        accessibility=AccessibilityInfo(tags=acc.get("tags") or [], wheelchair=acc.get("wheelchair"),
                                        stairs=acc.get("stairs"), sensory_notes=acc.get("sensory_notes")),
        parking=d.get("parking"), washrooms=d.get("washrooms"), food_available=d.get("food_available"),
        pet_friendly=d.get("pet_friendly"), family_friendly=d.get("family_friendly"), kid_friendly=d.get("kid_friendly"),
        photography_allowed=d.get("photography_allowed"), best_time=d.get("best_time"),
        freshness_score=d.get("freshness_score") or 0.0, last_verified_at=_dt(d.get("last_verified_at")),
        temporarily_unavailable=bool(d.get("temporarily_unavailable")), etiquette_tag=d.get("etiquette_tag"),
        source=[s for s in (_enum(DataSource, x) for x in d.get("source") or []) if s],
        description=d.get("description"), wiki_summary=d.get("wiki_summary"), transport_access=d.get("transport_access"),
    )


def load_places(path: str | Path = "data/master_data_core.json") -> list[Place]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data = data if isinstance(data, list) else data.get("places", [])
    return [place_from_dict(d) for d in data]
