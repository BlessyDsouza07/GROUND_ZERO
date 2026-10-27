"""Finds places in data/community_places.csv that share an identical
(or near-identical) lat/lon with a DIFFERENT named place.

Why this happens: Nominatim sometimes can't resolve a vague street
address to an exact building and silently falls back to a locality or
area centroid instead. Two unrelated places (a bookshop and a hospital
ambulance service, say) can then both land on that same centroid point.
The name-level dedup in geocode_new_places.py can't catch this — the
rows have different names, so they're not "duplicates" by name, but
they ARE duplicates by location, and that breaks anything relying on
real distinctness between places (the 300m proximity/geofence trigger
in Layer 3, distance-based transport tagging in Layer 2).

This script does NOT guess better coordinates — per this project's own
no-fake-data policy, a wrong guess is worse than no data. Instead, for
each collision group with 3+ genuinely unrelated places (a near-certain
generic-centroid fallback), it strips the coordinates back out and
re-queues those rows in new_places_to_geocode.csv with a note asking
for a more specific address (landmark, building name, or a pasted
Google Maps pin) next time. 2-place collisions are printed for you to
eyeball by hand — some (e.g. a bus stop right outside a station) are
legitimately at the same point and should be left alone; this script
won't guess which.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMUNITY_PATH = ROOT / "data" / "community_places.csv"
QUEUE_PATH = ROOT / "data" / "new_places_to_geocode.csv"

# Collision groups at/above this size are treated as an almost-certain
# generic-centroid fallback and auto-fixed. Below it, printed for a human
# decision instead (adjacent real places can legitimately share a point).
AUTO_FIX_THRESHOLD = 3


def main() -> None:
    with open(COMMUNITY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]

    lat_idx, lon_idx, name_idx = header.index("lat"), header.index("lon"), header.index("name")
    addr_idx = header.index("address") if "address" in header else None

    groups: dict[tuple[str, str], list[list[str]]] = {}
    for row in rows:
        if not row[lat_idx] or not row[lon_idx]:
            continue
        key = (row[lat_idx], row[lon_idx])
        groups.setdefault(key, []).append(row)

    collisions = {k: v for k, v in groups.items() if len(v) > 1}
    if not collisions:
        print("No coordinate collisions found. Nothing to do.")
        return

    auto_fixed, needs_review = [], []
    kept_rows = []
    removed_names = set()

    for (lat, lon), group_rows in collisions.items():
        names = [r[name_idx] for r in group_rows]
        if len(group_rows) >= AUTO_FIX_THRESHOLD:
            auto_fixed.append((lat, lon, names))
            removed_names.update(names)
        else:
            needs_review.append((lat, lon, names))

    for row in rows:
        if row[name_idx] in removed_names:
            continue
        kept_rows.append(row)

    with open(COMMUNITY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(kept_rows)

    if auto_fixed:
        # Read the queue fresh (not just what we're about to append) and
        # dedupe it by name first — repeated runs against places that
        # keep re-colliding (because they still haven't been fixed) were
        # appending the same name over and over, tripling rows and
        # wasting geocoding attempts each time this script ran.
        with open(QUEUE_PATH, newline="", encoding="utf-8") as f:
            queue_reader = csv.DictReader(f)
            queue_fieldnames = queue_reader.fieldnames or ["name", "category", "address", "source_note"]
            queue_rows = list(queue_reader)
        seen_names = {}
        for row in queue_rows:
            seen_names.setdefault(row["name"], row)  # first occurrence wins
        deduped_count = len(queue_rows) - len(seen_names)

        original_by_name = {r[name_idx]: r for group in collisions.values() for r in group}
        for lat, lon, names in auto_fixed:
            for name in names:
                if name in seen_names:
                    continue  # already queued from an earlier run — don't add again
                orig_row = original_by_name[name]
                address = orig_row[addr_idx] if addr_idx is not None else ""
                seen_names[name] = {
                    "name": name, "category": "unknown",
                    "address": f"{address} (previous geocode landed on a shared generic point — "
                               f"needs a more specific address: exact building/landmark, or a "
                               f"Google Maps pin)",
                    "source_note": "Re-queued by audit_duplicate_coordinates.py — generic-centroid collision",
                }

        with open(QUEUE_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=queue_fieldnames)
            writer.writeheader()
            writer.writerows(seen_names.values())

        if deduped_count:
            print(f"\nAlso cleaned up {deduped_count} duplicate row(s) already sitting in the "
                  f"queue from earlier runs.")

    print(f"Removed {len(removed_names)} places whose coordinates collided in groups of "
          f"{AUTO_FIX_THRESHOLD}+ (near-certain generic-centroid fallback):")
    for lat, lon, names in auto_fixed:
        print(f"  {lat},{lon} was shared by: {names}")
    print(f"\nThose {len(removed_names)} were re-added to new_places_to_geocode.csv for "
          f"re-geocoding with a better address.")

    if needs_review:
        print(f"\n{len(needs_review)} pairs share a point but weren't touched — decide by hand "
              f"(some are legitimately adjacent, e.g. a bus stop right outside a station):")
        for lat, lon, names in needs_review:
            print(f"  {lat},{lon}: {names}")


if __name__ == "__main__":
    main()
