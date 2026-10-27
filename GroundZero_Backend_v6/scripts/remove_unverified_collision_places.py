import csv
from pathlib import Path
from datetime import datetime

DATASET = Path("data/community_places.csv")
BACKUP_DIR = Path("data/backups")

REMOVE_NAMES = {
    "Thannirbhavi Boat Jetty",
    "Apollo Pharmacy Valencia",
    "Tenet Diagnostics Center- Mangalore",
    "Wellness Forever Pharmacy - Falnir Road",
}

# ---------------------------------------------------------
# SAFETY CHECKS
# ---------------------------------------------------------

if not DATASET.exists():
    raise FileNotFoundError(f"Dataset not found: {DATASET}")

BACKUP_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = BACKUP_DIR / f"community_places_before_unverified_removal_{timestamp}.csv"

# Read the complete dataset
with DATASET.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

if not fieldnames:
    raise RuntimeError("CSV has no header.")

if "name" not in fieldnames:
    raise RuntimeError("CSV does not contain the required 'name' column.")

before_count = len(rows)

# Find exact matches BEFORE changing anything
found_names = {row["name"] for row in rows if row["name"] in REMOVE_NAMES}
missing_names = REMOVE_NAMES - found_names

print("Records requested for removal:")
for name in sorted(REMOVE_NAMES):
    if name in found_names:
        print(f"  FOUND    : {name}")
    else:
        print(f"  NOT FOUND: {name}")

if missing_names:
    raise RuntimeError(
        "STOPPED SAFELY.\n"
        "One or more expected records were not found.\n"
        "Nothing was changed.\n"
        f"Missing: {sorted(missing_names)}"
    )

# Make a backup BEFORE modifying anything
with DATASET.open("rb") as src, backup_path.open("wb") as dst:
    dst.write(src.read())

print(f"\nBackup created:\n{backup_path}")

# Remove ONLY exact name matches
remaining_rows = [
    row for row in rows
    if row["name"] not in REMOVE_NAMES
]

removed_rows = [
    row for row in rows
    if row["name"] in REMOVE_NAMES
]

after_count = len(remaining_rows)

# Safety check: exactly 4 rows must be removed
if before_count - after_count != len(REMOVE_NAMES):
    raise RuntimeError(
        "STOPPED SAFELY.\n"
        f"Expected to remove {len(REMOVE_NAMES)} rows, "
        f"but calculated {before_count - after_count}.\n"
        "The original dataset has NOT been modified."
    )

# Write the filtered dataset
with DATASET.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames,
        extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(remaining_rows)

# Final verification
with DATASET.open("r", encoding="utf-8-sig", newline="") as f:
    verify_reader = csv.DictReader(f)
    verify_rows = list(verify_reader)

verify_count = len(verify_rows)

if verify_count != after_count:
    raise RuntimeError(
        "VERIFICATION FAILED: final row count does not match expected count."
    )

remaining_removed_names = {
    row["name"] for row in verify_rows if row["name"] in REMOVE_NAMES
}

if remaining_removed_names:
    raise RuntimeError(
        "VERIFICATION FAILED: one or more unwanted records still exist."
    )

# Verify every non-removed row is unchanged in content
original_remaining = [
    row for row in rows
    if row["name"] not in REMOVE_NAMES
]

if verify_rows != original_remaining:
    raise RuntimeError(
        "VERIFICATION FAILED: data outside the four requested records changed."
    )

print("\nSUCCESS")
print("--------------------------------------------------")
print(f"Rows before : {before_count}")
print(f"Rows removed: {before_count - after_count}")
print(f"Rows after  : {verify_count}")
print("--------------------------------------------------")

print("\nRemoved ONLY:")
for row in removed_rows:
    print(f"  - {row['name']}")

print("\nAll other dataset rows were verified unchanged.")
print(f"\nBackup: {backup_path}")