"""One-off patch for the specific 8 places that collided on a generic
locality centroid (see audit_duplicate_coordinates.py). Real, sourced
addresses/coordinates for 4 of the 8 were found via web search — this
applies them. The remaining 4 had nothing more precise findable
publicly; those are left in new_places_to_geocode.csv for you to pin
manually from Google Maps (right-click the exact spot -> copy
coordinates -> paste into community_places.csv yourself), since
guessing would violate the no-fake-data policy this project already
follows.

Run this AFTER audit_duplicate_coordinates.py (so these names are back
in the geocode queue) and BEFORE geocode_new_places.py.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "data" / "new_places_to_geocode.csv"
COMMUNITY_PATH = ROOT / "data" / "community_places.csv"

# Better, source-backed addresses (found via business-directory listings,
# not guessed) — these should let Nominatim resolve a distinct point
# instead of falling back to the Hampankatta/Bejai locality centroid.
BETTER_ADDRESSES = {
    "Kohinoor Computer Zone": "Alfa Towers, Balmatta Road, Opp. Mandovi Motors, Hampankatta, Mangalore, Karnataka 575001",
    "Kriti Book Store": "Crystal Arc Complex, Balmatta Road, near Roopa Hotel, Hampankatta, Mangalore, Karnataka 575001",
    "Shree Mukyaprana Temple": "Nodu Lane, Bejai, Mangalore, Karnataka 575004",
}

# Verified directly from Wikipedia's infobox coordinates for this
# specific institution — no geocoding needed, this IS the source.
VERIFIED_COORDS = {
    "University College, Mangalore": ("12.8659", "74.8412"),
}

# Confirmed via search: no publicly listed street-level address exists
# for these (small shops/services not in major directories) — left in
# the queue for a manual Google Maps pin.
STILL_NEEDS_MANUAL_PIN = [
    "Kalpana Medical Book Shop", "St Joseph Ambulance Mangalore",
    "HPCL Charging Station Bejai", "Itsy Bitsy",
]


def patch_queue() -> None:
    with open(QUEUE_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else ["name", "category", "address", "source_note"]

    patched, removed = 0, 0
    kept_rows = []
    for row in rows:
        name = row["name"]
        if name in VERIFIED_COORDS:
            removed += 1  # going straight into community_places.csv instead
            continue
        if name in BETTER_ADDRESSES:
            row["address"] = BETTER_ADDRESSES[name]
            row["source_note"] = "Address corrected from business directory listing (was locality-only)"
            patched += 1
        kept_rows.append(row)

    with open(QUEUE_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)

    print(f"Patched {patched} addresses in new_places_to_geocode.csv.")
    print(f"Removed {removed} (going straight into community_places.csv with verified coordinates instead).")
    still_in_queue = [r["name"] for r in kept_rows if r["name"] in STILL_NEEDS_MANUAL_PIN]
    if still_in_queue:
        print(f"\nStill in the queue with no better address found — these will keep failing until "
              f"you add a real one (or drop a Google Maps pin directly into community_places.csv):")
        for n in still_in_queue:
            print(f"  - {n}")


def add_verified_places() -> None:
    with open(COMMUNITY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]

    name_idx, lat_idx, lon_idx = header.index("name"), header.index("lat"), header.index("lon")
    addr_idx = header.index("address") if "address" in header else None
    existing_names = {row[name_idx] for row in rows}

    added = []
    for name, (lat, lon) in VERIFIED_COORDS.items():
        if name in existing_names:
            continue
        new_row = [""] * len(header)
        new_row[name_idx] = name
        new_row[lat_idx] = lat
        new_row[lon_idx] = lon
        if addr_idx is not None:
            new_row[addr_idx] = "Hampankatta, Mangaluru, Karnataka 575001 (coordinates verified via Wikipedia infobox)"
        rows.append(new_row)
        added.append(name)

    if added:
        with open(COMMUNITY_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print(f"\nAdded {len(added)} place(s) directly with verified coordinates: {added}")


if __name__ == "__main__":
    patch_queue()
    add_verified_places()
