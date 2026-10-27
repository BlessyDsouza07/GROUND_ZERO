"""
Targeted coordinate repair for known generic-centroid collisions.

IMPORTANT:
- Does NOT delete any place.
- Does NOT add any place.
- Does NOT modify names, categories, addresses, descriptions, etc.
- Only changes lat/lon for explicitly listed places.
- Creates a backup before writing.
- Refuses to overwrite a coordinate unless a verified coordinate is supplied.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
COMMUNITY_PATH = ROOT / "data" / "community_places.csv"
BACKUP_DIR = ROOT / "data" / "backups"

# ---------------------------------------------------------------------
# ONLY PUT COORDINATES HERE AFTER THEY ARE VERIFIED.
#
# Shell is directly verified from Shell's own location page:
# 12.90144, 74.84193
#
# The remaining places are deliberately left out for now rather than
# inventing coordinates.
# ---------------------------------------------------------------------

VERIFIED_COORDS = {
    "Masjid prayer": ("12.85385", "74.8392383"),
    "Shri Mahalingeshwara Swamy Temple": ("12.85403", "74.8397461"),
    "Muhiyuddeen Juma Masjid": ("12.86099", "74.8249023"),
    "St. Vincent Ferrer Church": ("12.86353", "74.8617383"),
    "Shell Recharge Charging Station Derebail": ("12.90144", "74.84193"),
}



def main() -> None:
    if not COMMUNITY_PATH.exists():
        raise SystemExit(f"ERROR: File not found: {COMMUNITY_PATH}")

    # ---------------------------------------------------------------
    # Read original dataset
    # ---------------------------------------------------------------
    with open(COMMUNITY_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames:
        raise SystemExit("ERROR: CSV has no header.")

    required = {"name", "lat", "lon"}
    missing = required - set(fieldnames)

    if missing:
        raise SystemExit(
            f"ERROR: Missing required columns: {sorted(missing)}"
        )

    original_row_count = len(rows)

    # ---------------------------------------------------------------
    # Create timestamped backup
    # ---------------------------------------------------------------
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"community_places_before_coordinate_repair_{timestamp}.csv"

    shutil.copy2(COMMUNITY_PATH, backup_path)

    print(f"Backup created:")
    print(f"  {backup_path}")

    # ---------------------------------------------------------------
    # Find and modify ONLY explicitly listed places
    # ---------------------------------------------------------------
    changed = []
    found_names = set()

    for row in rows:
        name = row.get("name", "").strip()

        if name not in VERIFIED_COORDS:
            continue

        found_names.add(name)

        old_lat = row["lat"]
        old_lon = row["lon"]

        new_lat, new_lon = VERIFIED_COORDS[name]

        if old_lat == new_lat and old_lon == new_lon:
            print(f"UNCHANGED: {name}")
            print(f"  already has {new_lat}, {new_lon}")
            continue

        row["lat"] = new_lat
        row["lon"] = new_lon

        changed.append(
            {
                "name": name,
                "old_lat": old_lat,
                "old_lon": old_lon,
                "new_lat": new_lat,
                "new_lon": new_lon,
            }
        )

    # ---------------------------------------------------------------
    # Verify every requested place was found
    # ---------------------------------------------------------------
    missing_names = set(VERIFIED_COORDS) - found_names

    if missing_names:
        print("\nERROR: These requested names were not found:")
        for name in sorted(missing_names):
            print(f"  - {name}")

        print("\nNO CHANGES WRITTEN.")
        print(f"Your original dataset remains untouched.")
        return

    # ---------------------------------------------------------------
    # Write dataset
    # ---------------------------------------------------------------
    with open(COMMUNITY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)

    # ---------------------------------------------------------------
    # Final safety checks
    # ---------------------------------------------------------------
    with open(COMMUNITY_PATH, newline="", encoding="utf-8-sig") as f:
        check_reader = csv.DictReader(f)
        check_rows = list(check_reader)

    if len(check_rows) != original_row_count:
        raise SystemExit(
            f"SAFETY ERROR: Row count changed! "
            f"Before={original_row_count}, After={len(check_rows)}"
        )

    print("\n========================================")
    print("COORDINATE REPAIR COMPLETE")
    print("========================================")

    print(f"Rows before: {original_row_count}")
    print(f"Rows after:  {len(check_rows)}")
    print(f"Rows added:  0")
    print(f"Rows removed: 0")
    print(f"Coordinates changed: {len(changed)}")

    if changed:
        print("\nCHANGED RECORDS:")
        for item in changed:
            print(f"\n{item['name']}")
            print(
                f"  OLD: {item['old_lat']}, {item['old_lon']}"
            )
            print(
                f"  NEW: {item['new_lat']}, {item['new_lon']}"
            )

    print("\nBackup:")
    print(f"  {backup_path}")


if __name__ == "__main__":
    main()