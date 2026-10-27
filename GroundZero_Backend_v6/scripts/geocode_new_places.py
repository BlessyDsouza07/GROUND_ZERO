"""
Fills in real coordinates for data/new_places_to_geocode.csv using OSM's
Nominatim (https://nominatim.openstreetmap.org) — free, legal, no API key,
the same map data your OSM bulk extract already uses. Deliberately NOT run
against my sandbox in this session (it has no general internet egress) —
run this on your own machine, which does.

Why this exists instead of me just writing coordinates directly: the
addresses in new_places_to_geocode.csv came from blog/listing sites during
a web search, which are good enough to confirm a place is real and named
correctly, but not reliable enough to trust for exact lat/lon — making up
coordinates would violate the one rule that matters most for this dataset
(nothing fabricated). Nominatim geocodes the REAL address string against
real OSM data, so what lands in your CSV is a genuine coordinate, not a
guess.

Usage:
    python scripts/geocode_new_places.py

Respects Nominatim's usage policy: max 1 request/second, a real
identifying User-Agent (required, requests without one get blocked), and
this is a one-off manual tool, not a background service polling
continuously — safe for a handful of new places at a time.

Rows that fail to geocode confidently are printed for you to fix by hand
(a name search on Google/OSM directly) rather than silently guessed or
dropped.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "GroundZero-Mangaluru-DatasetEnrichment/1.0 (academic project; contact via project owner)"

SEED_PATH = Path("data/new_places_to_geocode.csv")
TARGET_PATH = Path("data/community_places.csv")

# Bounding box sanity check — same box your ETL pipeline already uses
# (shared/config.py BBOX_*). A geocode result outside this is almost
# certainly the wrong match (a same-named place elsewhere in India) and
# gets flagged rather than silently accepted.
BBOX = {"south": 12.75, "west": 74.78, "north": 13.05, "east": 75.05}


MAX_RETRIES = 3


def geocode(address: str) -> tuple[float, float] | None:
    """Retries transient network failures (timeouts, connection resets —
    Nominatim's free endpoint does occasionally hiccup) up to MAX_RETRIES
    times with a growing backoff, so one flaky request doesn't need to
    kill an hours-long run. A real 'no result' or 'outside Mangaluru' is
    NOT retried — that's a confident answer, not a network problem."""
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = httpx.get(
                NOMINATIM_URL,
                params={"q": f"{address}, Mangaluru, Karnataka, India", "format": "json", "limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=10.0,
            )
            response.raise_for_status()
            results = response.json()
            if not results:
                return None
            lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
            if not (BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]):
                return None  # outside Mangaluru — likely wrong match, don't accept it
            return lat, lon
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                wait = 2 * attempt
                print(f"  (network hiccup on attempt {attempt}/{MAX_RETRIES}, retrying in {wait}s: {exc})")
                time.sleep(wait)
    print(f"  (gave up after {MAX_RETRIES} attempts — network issue, not a bad address: {last_error})")
    return None


def main() -> None:
    with open(SEED_PATH, newline="", encoding="utf-8") as f:
        seed_rows = list(csv.DictReader(f))

    with open(TARGET_PATH, newline="", encoding="utf-8") as f:
        target_reader = csv.reader(f)
        header = next(target_reader)
        existing_rows = [row for row in target_reader if row]  # skip blank trailing lines
        existing_names = {row[0] for row in existing_rows}

    appended_count, failed = 0, []
    # Opened once, flushed after every single row — a script running for
    # ~8 minutes over a live external API WILL occasionally hit a network
    # blip, and a crash must not throw away everything geocoded so far
    # (the previous version held every result in memory and only wrote
    # once at the very end, so a mid-run crash silently lost every "OK"
    # already printed to the terminal — nothing in community_places.csv
    # despite the success messages).
    with open(TARGET_PATH, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        for row in seed_rows:
            if row["name"] in existing_names:
                print(f"SKIP (already in dataset): {row['name']}")
                continue

            coords = geocode(row["address"])
            time.sleep(1.1)  # Nominatim usage policy: max 1 req/sec

            if coords is None:
                failed.append(row["name"])
                print(f"COULD NOT GEOCODE (add by hand): {row['name']} — {row['address']}")
                continue

            lat, lon = coords
            print(f"OK: {row['name']} -> {lat}, {lon}")

            # Conservative category-typical defaults for fields Nominatim
            # can't supply — same honest-defaults convention already used
            # for other cafe rows in this file (see e.g. Diesel Cafe).
            # Nothing here is claimed as verified beyond
            # name/category/address/coordinates; edit opening_hours/
            # estimated_cost by hand once you've confirmed them, same as
            # you would for any other manual addition.
            new_row = [
                row["name"], row["category"], str(lat), str(lon),
                f"{row['address']} (geocoded via Nominatim — verify)",
                f"Recently opened {row['category']} — {row['source_note']}",
                "seed_research_geocoded", "", "", f"{row['category']};local",
                "budget", "200", "low", "moderate", "40", "false", "all",
                "", "", "evening", "", "", "true", "true", "true", "false", "",
                "0.5", "0",
            ]
            assert len(new_row) == len(header), f"column count mismatch for {row['name']}"
            writer.writerow(new_row)
            out_f.flush()  # on disk immediately, survives a crash on the next row
            appended_count += 1
            existing_names.add(row["name"])  # so a re-run after a crash won't re-geocode it

    print(f"\nDone. appended={appended_count} failed={len(failed)} "
          f"skipped_duplicates={len(seed_rows) - appended_count - len(failed)}")
    if failed:
        print("Add these by hand after a manual address lookup:", failed)


if __name__ == "__main__":
    main()
