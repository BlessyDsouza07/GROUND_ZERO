"""For the handful of places Nominatim genuinely can't resolve (too small
or too new to be in OpenStreetMap's data) — add real coordinates you
found yourself by pinning the exact spot on Google Maps, then this
script inserts them directly into community_places.csv, removes them
from new_places_to_geocode.csv, and runs the same duplicate-coordinate
check as audit_duplicate_coordinates.py so you can't accidentally
re-create the collision you just fixed.

How to get a coordinate: open Google Maps, find the exact place, right-
click the spot (or long-press on mobile) -> the lat,lon shown at the top
of the menu is what you paste below. Takes about 30 seconds per place.

Fill in PINS below, then run:  python scripts/add_manual_pins.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMUNITY_PATH = ROOT / "data" / "community_places.csv"
QUEUE_PATH = ROOT / "data" / "new_places_to_geocode.csv"

# Fill in real coordinates from Google Maps for each name below.
# Leave a value as None to skip it (still pending).
PINS: dict[str, tuple[float, float] | None] = {
    "Itsy Bitsy": (12.8815125, 74.846390625),
    "Kalpana Medical Book Shop": None,
    "St Joseph Ambulance Mangalore": None,
    "HPCL Charging Station Bejai": (12.8960625, 74.846203125),
    "Kohinoor Computer Zone": (12.8694625, 74.844859375),
    "Kriti Book Store": (12.8700174, 74.8436043),
    "Shree Mukyaprana Temple": (12.8904875, 74.850953125),
}


def main() -> None:
    ready = {name: coords for name, coords in PINS.items() if coords is not None}
    if not ready:
        print("No coordinates filled in yet — edit PINS at the top of this script first.")
        return

    with open(COMMUNITY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]

    name_idx, lat_idx, lon_idx = header.index("name"), header.index("lat"), header.index("lon")
    addr_idx = header.index("address") if "address" in header else None
    existing_names = {row[name_idx] for row in rows}

    # Refuse to introduce a NEW collision — if your pin happens to land on
    # an existing place's exact coordinates, that's worth a second look,
    # not a silent duplicate.
    existing_coords = {(row[lat_idx], row[lon_idx]) for row in rows}

    added, blocked = [], []
    for name, (lat, lon) in ready.items():
        if name in existing_names:
            continue
        key = (str(lat), str(lon))
        if key in existing_coords:
            blocked.append(name)
            continue
        new_row = [""] * len(header)
        new_row[name_idx] = name
        new_row[lat_idx] = str(lat)
        new_row[lon_idx] = str(lon)
        if addr_idx is not None:
            new_row[addr_idx] = "Coordinates added manually via Google Maps pin"
        rows.append(new_row)
        existing_coords.add(key)
        added.append(name)

    if added:
        with open(COMMUNITY_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    if blocked:
        print(f"NOT added — this pin lands on the exact same spot as an existing place, "
              f"double-check it: {blocked}")

    if added:
        with open(QUEUE_PATH, newline="", encoding="utf-8") as f:
            queue_reader = csv.DictReader(f)
            queue_fieldnames = queue_reader.fieldnames or ["name", "category", "address", "source_note"]
            queue_rows = [r for r in queue_reader if r["name"] not in added]
        with open(QUEUE_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=queue_fieldnames)
            writer.writeheader()
            writer.writerows(queue_rows)
        print(f"Added {len(added)} place(s) with manually-pinned coordinates: {added}")
        print("Removed them from the geocoding queue. Now run the pipeline to store them.")


if __name__ == "__main__":
    main()
