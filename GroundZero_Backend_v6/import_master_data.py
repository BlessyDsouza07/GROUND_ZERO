"""
One-off script: import data/master_data_core.json directly into Postgres.

Why this exists: master_data_core.json is a full export from a previous
successful pipeline run (688 real, fully-enriched Mangaluru places — bias
index, grade, accessibility, etc. already computed). Rather than re-running
the live/offline collection steps, this loads that export straight into
the `places` table via the app's own PostgresPlaceRepository.bulk_upsert(),
so every downstream consumer (HIVE slot assembly, bias audit, API routes)
sees exactly the same shape of data it would from a live pipeline run.

Run from the groundzero project root, with the venv active and Postgres
up (docker compose up -d):

    python import_master_data.py
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from layer0.domain.entities import (
    AccessibilityInfo,
    BiasSignals,
    Coordinates,
    CrowdLevel,
    DataSource,
    EnergyRequirement,
    Grade,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository
from layer0.infrastructure.db.session import get_session

EXPORT_PATH = Path("data/master_data_core.json")


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _dict_to_place(d: dict) -> Place:
    return Place(
        id=d["id"],
        name=d["name"],
        category=d["category"],
        coordinates=Coordinates(**d["coordinates"]),
        opening_hours=OpeningHours(**d["opening_hours"]),
        price_band=PriceBand(d["price_band"]),
        estimated_cost=d["estimated_cost"],
        tags=d.get("tags", []),
        bias_signals=BiasSignals(**d.get("bias_signals", {})),
        bias_index=d.get("bias_index"),
        grade=Grade(d["grade"]) if d.get("grade") else None,
        energy_requirement=EnergyRequirement(d["energy_requirement"]),
        crowd_level=CrowdLevel(d["crowd_level"]),
        season_suitability=d.get("season_suitability", []),
        tide_dependency=d.get("tide_dependency", False),
        dwell_time_typical_minutes=d.get("dwell_time_typical_minutes", 45),
        accessibility=AccessibilityInfo(**d.get("accessibility", {})),
        parking=d.get("parking"),
        washrooms=d.get("washrooms"),
        food_available=d.get("food_available"),
        pet_friendly=d.get("pet_friendly"),
        family_friendly=d.get("family_friendly"),
        kid_friendly=d.get("kid_friendly"),
        photography_allowed=d.get("photography_allowed"),
        best_time=d.get("best_time"),
        freshness_score=d.get("freshness_score", 0.0),
        last_verified_at=_parse_dt(d.get("last_verified_at")),
        temporarily_unavailable=d.get("temporarily_unavailable", False),
        etiquette_tag=d.get("etiquette_tag"),
        source=[DataSource(s) for s in d.get("source", [])],
        description=d.get("description"),
        wiki_summary=d.get("wiki_summary"),
        transport_access=d.get("transport_access"),
        created_at=_parse_dt(d.get("created_at")),
        updated_at=_parse_dt(d.get("updated_at")),
    )


async def main() -> None:
    if not EXPORT_PATH.exists():
        raise SystemExit(f"Not found: {EXPORT_PATH} — run this from the groundzero project root.")

    raw = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    places = [_dict_to_place(d) for d in raw]
    print(f"Parsed {len(places)} places from {EXPORT_PATH}")

    async with get_session() as session:
        repo = PostgresPlaceRepository(session)
        stored = await repo.bulk_upsert(places)
        print(f"Stored {len(stored)} places in Postgres.")


if __name__ == "__main__":
    asyncio.run(main())