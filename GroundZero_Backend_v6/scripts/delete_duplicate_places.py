"""
Deletes from Postgres the duplicate place rows listed in
data/duplicate_cleanup_ids.txt (written by clean_dataset_duplicates.py).

Why this is needed: import_master_data.py and the pipeline UPSERT — they never
remove rows — so cleaning the JSON/CSV alone leaves the old duplicate rows in
the `places` table.

    python scripts/delete_duplicate_places.py            # dry run: shows what would go
    python scripts/delete_duplicate_places.py --apply    # deletes (one commit per id)

Run it AFTER re-importing the cleaned master file (python import_master_data.py)
so the surviving OSM records already carry the merged description/tags.
Needs Postgres up (docker compose up -d). Uses the app's own
PostgresPlaceRepository.delete, which cascades to the place's bias_signals.
NOTE: written and unit-checked offline only — run the dry run first.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

IDS = ROOT / "data" / "duplicate_cleanup_ids.txt"


def read_ids(path: Path = IDS) -> list[str]:
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            uuid.UUID(line)  # fail loudly on a malformed id instead of skipping it
            ids.append(line)
    return ids


async def main(apply: bool) -> None:
    from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository
    from layer0.infrastructure.db.session import get_session

    ids = read_ids()
    print(f"{len(ids)} id(s) in {IDS.name}")
    async with get_session() as session:
        repo = PostgresPlaceRepository(session)
        for pid in ids:
            place = await repo.get_by_id(pid)
            if place is None:
                print(f"  already gone: {pid}")
                continue
            print(f"  {'DELETE' if apply else 'would delete'}: {place.name} [{place.category}] {pid}")
            if apply:
                await repo.delete(pid)
    if not apply:
        print("dry run only — re-run with --apply to delete.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    asyncio.run(main(ap.parse_args().apply))
