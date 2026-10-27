import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMUNITY_PATH = ROOT / "data" / "community_places.csv"

REMOVE_NAMES = {
    "Itsy Bitsy",
    "HPCL Charging Station Bejai",
    "Kalpana Medical Book Shop",
    "St Joseph Ambulance Mangalore",
}


def main() -> None:
    with open(COMMUNITY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]

    name_idx = header.index("name")

    kept = []
    removed = []

    for row in rows:
        name = row[name_idx].strip()

        if name in REMOVE_NAMES:
            removed.append(name)
        else:
            kept.append(row)

    with open(COMMUNITY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(kept)

    print()
    print("REMOVAL COMPLETE")
    print("================")
    print(f"Removed: {len(removed)} place(s)")
    
    for name in removed:
        print(f"  - {name}")

    missing = REMOVE_NAMES - set(removed)

    if missing:
        print()
        print("Not found:")
        for name in sorted(missing):
            print(f"  - {name}")

    print()
    print(f"Places remaining: {len(kept)}")
    print("Backup remains untouched:")
    print("  data/community_places_backup_before_removing_4.csv")


if __name__ == "__main__":
    main()