"""
Spreadsheet-based ListingSource (blueprint 3.1 sources #3/#4/#7 — the
practical implementation, not a stub).

Why this exists: OSM/Wikidata/Wikipedia cover a lot of Mangaluru, but by
definition they will never cover everything — a family-run kitchen with
two plastic tables, a neighbourhood shrine, a fisherman's shortcut to a
beach. Those places rarely have any online footprint at all, which is
exactly the "hidden gem" the blueprint's Local Secret slot exists for
(Section 3.1, source #7 — Community Submissions). There is also no
public, free, unlimited-rate API for "every place in a city" — nobody
has one, including Google.

The realistic, free, and *legal* way to close that gap is what this file
implements: a CSV file — maintained in Google Sheets or Excel and
exported/saved as CSV — that Carol, her team, or trusted local
contributors fill in directly. It has:

  - zero API rate limits (it's a local file read)
  - zero cost
  - zero licensing concerns (it's Carol's own team's data entry, not
    scraped from anyone else's copyrighted listing)
  - a natural place for hyperlocal knowledge (exact etiquette notes,
    real local_percentage/media_mentions estimates) that no API will
    ever have

It plugs into the exact same `ListingSource` seam the local_listings
collector already defines for a future Karnataka Tourism API — nothing
in the ETL orchestrator, dedup, bias audit, or storage layers needed to
change to support this.

This is a bootstrap/completeness mechanism, not a claim that it captures
"every place in Mangaluru." No data source can honestly claim that. What
it does is give you an unlimited, ever-growing channel to add real,
verified places faster than any single API could — see
docs/GROWING_THE_DATABASE.md for the full explanation and workflow.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from layer0.infrastructure.collectors.local_listings_collector import ListingRecord, ListingSource

logger = logging.getLogger("groundzero.layer0.collectors.spreadsheet")

SOURCE_NAME = "community_spreadsheet"

# Columns a curator can fill in. Only name/category/lat/lon are required;
# everything else is optional and simply left unset (None) if the column
# is missing or the cell is blank — never guessed.
_REQUIRED_COLUMNS = {"name", "category", "lat", "lon"}

_BOOL_TRUE = {"true", "yes", "y", "1"}
_BOOL_FALSE = {"false", "no", "n", "0"}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_bool(value: str | None) -> bool | None:
    value = _clean(value)
    if value is None:
        return None
    lowered = value.lower()
    if lowered in _BOOL_TRUE:
        return True
    if lowered in _BOOL_FALSE:
        return False
    return None


def _parse_float(value: str | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_list(value: str | None) -> tuple[str, ...]:
    value = _clean(value)
    if value is None:
        return ()
    # Accept either ";" or "|" as a separator — whichever the curator's
    # spreadsheet tool didn't already use for something else in the row.
    separator = ";" if ";" in value else "|"
    return tuple(part.strip() for part in value.split(separator) if part.strip())


def _parse_local_percentage(value: str | None) -> float | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    # Accept either "0.8" or "80" (percent) — whichever a curator typed.
    return parsed / 100.0 if parsed > 1.0 else parsed


class SpreadsheetListingSource(ListingSource):
    """Reads `ListingRecord`s from a CSV file at `csv_path`.

    Missing file: logged once and treated as "no listings this run" — the
    same graceful-skip behavior every other collector in this system
    already uses for a source that isn't configured yet. It never crashes
    the ETL run.
    """

    name = SOURCE_NAME

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)

    async def fetch(self) -> list[ListingRecord]:
        if not self.csv_path.exists():
            logger.info(
                "%s: no file at %s — skipping (this is optional; see "
                "docs/GROWING_THE_DATABASE.md to start filling it in)",
                SOURCE_NAME, self.csv_path,
            )
            return []

        records: list[ListingRecord] = []
        skipped = 0

        with self.csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                logger.warning("%s: %s has no header row, skipping entirely", SOURCE_NAME, self.csv_path)
                return []

            normalized_fields = {(fn or "").strip().lower(): fn for fn in reader.fieldnames}
            missing_required = _REQUIRED_COLUMNS - set(normalized_fields)
            if missing_required:
                logger.warning(
                    "%s: %s is missing required column(s) %s — skipping entirely",
                    SOURCE_NAME, self.csv_path, sorted(missing_required),
                )
                return []

            def col(row: dict, key: str) -> str | None:
                actual = normalized_fields.get(key)
                return row.get(actual) if actual else None

            for line_number, row in enumerate(reader, start=2):  # header is line 1
                name = _clean(col(row, "name"))
                lat = _parse_float(col(row, "lat"))
                lon = _parse_float(col(row, "lon"))
                category = _clean(col(row, "category")) or "uncategorized"

                if not name or lat is None or lon is None:
                    skipped += 1
                    logger.warning(
                        "%s: %s line %d skipped (needs name + numeric lat/lon)",
                        SOURCE_NAME, self.csv_path, line_number,
                    )
                    continue

                records.append(
                    ListingRecord(
                        name=name,
                        category=category,
                        lat=lat,
                        lon=lon,
                        address=_clean(col(row, "address")),
                        description=_clean(col(row, "description")),
                        source_url=_clean(col(row, "source_url")) or "",
                        source_name=_clean(col(row, "curator")) or SOURCE_NAME,
                        opening_hours_raw=_clean(col(row, "opening_hours")),
                        tags=_parse_list(col(row, "tags")),
                        price_band=_clean(col(row, "price_band")),
                        estimated_cost=_parse_float(col(row, "estimated_cost")),
                        energy_requirement=_clean(col(row, "energy_requirement")),
                        crowd_level=_clean(col(row, "crowd_level")),
                        dwell_time_typical_minutes=_parse_int(col(row, "dwell_time_typical_minutes")),
                        tide_dependency=_parse_bool(col(row, "tide_dependency")),
                        season_suitability=_parse_list(col(row, "season_suitability")),
                        accessibility_tags=_parse_list(col(row, "accessibility_tags")),
                        etiquette_tag=_clean(col(row, "etiquette_tag")),
                        best_time=_clean(col(row, "best_time")),
                        parking=_parse_bool(col(row, "parking")),
                        washrooms=_parse_bool(col(row, "washrooms")),
                        food_available=_parse_bool(col(row, "food_available")),
                        family_friendly=_parse_bool(col(row, "family_friendly")),
                        kid_friendly=_parse_bool(col(row, "kid_friendly")),
                        photography_allowed=_parse_bool(col(row, "photography_allowed")),
                        contact_phone=_clean(col(row, "contact_phone")),
                        local_percentage_hint=_parse_local_percentage(col(row, "local_percentage_hint")),
                        media_mentions_hint=_parse_int(col(row, "media_mentions_hint")),
                    )
                )

        logger.info(
            "%s: loaded %d place(s) from %s (%d row(s) skipped)",
            SOURCE_NAME, len(records), self.csv_path, skipped,
        )
        return records
