"""
Fixes the duplicate problems scripts/audit_dataset_duplicates.py finds — only
the ones that are unambiguous. Backs everything up first.

    python scripts/clean_dataset_duplicates.py --dry-run   # show the plan
    python scripts/clean_dataset_duplicates.py             # apply

Root cause it fixes: hand-seeded "local_listing" rows carry approximate
coordinates (often 0.5-1.7 km off). Their OpenStreetMap twins have real ones,
so the ETL's "within 75 m AND similar name" rule can never merge them and the
same place (Rosario Cathedral, Panambur Beach, ...) exists twice — HIVE could
recommend it twice in one day.

What it does
------------
master_data_core.json
  1. SEED-OSM      a seed record with exactly ONE same-name OSM twin within 4 km
                   is merged into the twin (twin's id + real coordinates win;
                   only the seed's description and clean tags are added). The
                   seed id is dropped.
  2. OSM-OSM       two OSM records, same name+category, < 50 m apart -> merged.
  3. STACKED-SEED  a seed record whose pin is IDENTICAL (2 m) to a different
                   place's is a centroid fallback, not a location -> dropped
                   (and re-queued in the community file for a verified pin).
  4. NAMES         stray quotes / trailing spaces stripped.
community_places.csv
  5. Seed rows that had an OSM twin get the twin's coordinates (address notes
     it), so the next pipeline run merges them instead of duplicating.
  6. Stacked-pin rows are removed and re-queued in new_places_to_geocode.csv.
  7. Blank categories are filled from the name (Temple -> temple, ...).

Everything else it finds is only REPORTED (chains such as Domino's/KFC/Cafe
Coffee Day are legitimately many places).

It also writes data/duplicate_cleanup_ids.txt: the database ids that must be
deleted, because re-importing the JSON only upserts and never removes rows.
Run scripts/delete_duplicate_places.py against Postgres for that.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layer0.application.place_ingest import fold_name, google_maps_search_url, haversine_m  # noqa: E402
from shared.place_taxonomy import canonical_category, is_itinerary_eligible  # noqa: E402

DATA = ROOT / "data"
MASTER = DATA / "master_data_core.json"
COMMUNITY = DATA / "community_places.csv"
QUEUE = DATA / "new_places_to_geocode.csv"
IDS_OUT = DATA / "duplicate_cleanup_ids.txt"
REPORT = DATA / "duplicate_cleanup_report.txt"
BACKUPS = DATA / "backups"
QUEUE_COLUMNS = ["priority", "name", "category", "address", "source_note", "reason", "maps_link",
                 "pin_lat", "pin_lon", "osm_ref", "pin_source", "pin_note"]

SEED_MAX_KM = 4.0
OSM_TWIN_MAX_M = 50.0
SAME_PIN_M = 2.0
_SANE_TAG = re.compile(r"^[a-z][a-z _-]{1,30}$")


def key(name: str) -> tuple[str, ...]:
    return tuple(sorted(set(fold_name(name))))


def dist(a: dict, b: dict) -> float:
    return haversine_m(a["coordinates"]["latitude"], a["coordinates"]["longitude"],
                       b["coordinates"]["latitude"], b["coordinates"]["longitude"])


def is_seed(p: dict) -> bool:
    return p.get("source") == ["local_listing"]


def is_osm(p: dict) -> bool:
    return p.get("source") == ["openstreetmap"]


def merge_seed_into_osm(osm: dict, seed: dict) -> None:
    if not osm.get("description") and seed.get("description"):
        osm["description"] = seed["description"]
    good = [t for t in seed.get("tags", []) if _SANE_TAG.match(t)]
    osm["tags"] = sorted(set(osm.get("tags", [])) | set(good))
    osm["source"] = sorted(set(osm.get("source", [])) | set(seed.get("source", [])))


def plan_master(master: list[dict]):
    dropped: dict[str, str] = {}          # id -> reason
    merged_into: dict[str, str] = {}      # dropped id -> survivor id
    log: list[str] = []
    by_id = {p["id"]: p for p in master}

    # 3) stacked seeds (identical pin, different name)
    pins = defaultdict(list)
    for p in master:
        pins[(round(p["coordinates"]["latitude"], 5), round(p["coordinates"]["longitude"], 5))].append(p)
    for group in pins.values():
        names = {key(p["name"]) for p in group}
        if len(group) > 1 and len(names) > 1:
            for p in group:
                if is_seed(p):
                    others = ", ".join(f"'{o['name']}'" for o in group if o is not p)
                    dropped[p["id"]] = f"STACKED-SEED: identical pin to {others}"
                    log.append(f"DROP  '{p['name']}' ({p['id'][:8]}) — identical pin to {others}")

    # 1) seed -> single OSM twin
    osm_by_key = defaultdict(list)
    for p in master:
        if is_osm(p):
            osm_by_key[key(p["name"])].append(p)
    for p in master:
        if not is_seed(p) or p["id"] in dropped:
            continue
        twins = [o for o in osm_by_key.get(key(p["name"]), []) if dist(p, o) <= SEED_MAX_KM * 1000]
        if len(twins) == 1:
            o = twins[0]
            dropped[p["id"]] = f"SEED-OSM: merged into {o['id'][:8]}"
            merged_into[p["id"]] = o["id"]
            log.append(f"MERGE '{p['name']}' seed ({p['id'][:8]}, {dist(p, o):.0f} m off) -> OSM '{o['name']}' ({o['id'][:8]})")
        elif len(twins) > 1:
            log.append(f"SKIP  '{p['name']}' seed has {len(twins)} OSM candidates — ambiguous, left alone")

    # 2) OSM twin records < 50 m, same name + category
    osm = [p for p in master if is_osm(p) and p["id"] not in dropped]
    for i, a in enumerate(osm):
        for b in osm[i + 1:]:
            if b["id"] in dropped or a["id"] in dropped:
                continue
            if key(a["name"]) == key(b["name"]) and canonical_category(a["category"]) == canonical_category(b["category"]) \
                    and dist(a, b) < OSM_TWIN_MAX_M:
                dropped[b["id"]] = f"OSM-OSM: merged into {a['id'][:8]}"
                merged_into[b["id"]] = a["id"]
                log.append(f"MERGE '{b['name']}' ({b['id'][:8]}) -> '{a['name']}' ({a['id'][:8]}), {dist(a, b):.0f} m apart")
    return dropped, merged_into, log, by_id


def review_only(master: list[dict], dropped: dict) -> list[str]:
    """Same name, same category, < 4 km — possible duplicates we will NOT touch."""
    out, live = [], [p for p in master if p["id"] not in dropped]
    by = defaultdict(list)
    for p in live:
        by[(key(p["name"]), canonical_category(p["category"]))].append(p)
    for (k, c), g in by.items():
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                d = dist(a, b)
                if d < 1000:
                    out.append(f"REVIEW '{a['name']}' <-> '{b['name']}' [{c}] {d:.0f} m — same place or two branches? (ids {a['id'][:8]}, {b['id'][:8]})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    master = json.loads(MASTER.read_text(encoding="utf-8"))
    dropped, merged_into, log, by_id = plan_master(master)
    for sid, oid in merged_into.items():
        merge_seed_into_osm(by_id[oid], by_id[sid])

    # names
    cleaned_names = 0
    for p in master:
        n = p["name"].strip().strip("'\"").strip()
        if n != p["name"]:
            log.append(f"NAME  {p['name']!r} -> {n!r}")
            p["name"] = n
            cleaned_names += 1
    survivors = [p for p in master if p["id"] not in dropped]

    # ---- community csv
    with COMMUNITY.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        rows = [r for r in reader if any(c.strip() for c in r)]
    col = {h: i for i, h in enumerate(header)}
    dropped_seed = [by_id[i] for i in dropped]
    requeue, keep_rows, aligned = [], [], 0
    CATEGORY_BY_NAME = [(r"\btemple\b|\bmandir\b|\bkshetra\b", "temple"), (r"\bcollege\b|\buniversity\b", "university"),
                        (r"\bbook\b|\bcomputer\b|\bstore\b|\bshop\b", "local_shop")]
    for r in rows:
        name = r[col["name"]].strip()
        try:
            lat, lon = float(r[col["lat"]]), float(r[col["lon"]])
        except ValueError:
            keep_rows.append(r); continue
        # 6) stacked-pin rows (same coordinates as a dropped stacked seed)
        stacked = next((s for s in dropped_seed if dropped[s["id"]].startswith("STACKED") and key(s["name"]) == key(name)
                        and haversine_m(lat, lon, s["coordinates"]["latitude"], s["coordinates"]["longitude"]) < 5), None)
        if stacked:
            requeue.append((r, dropped[stacked["id"]]))
            log.append(f"CSV   re-queue '{name}' — {dropped[stacked['id']]}")
            continue
        # 5) align approximate seed coordinates to the OSM twin
        twin_id = next((merged_into[s["id"]] for s in dropped_seed if s["id"] in merged_into and key(s["name"]) == key(name)
                        and haversine_m(lat, lon, s["coordinates"]["latitude"], s["coordinates"]["longitude"]) < 5
                        and by_id[merged_into[s["id"]]] in survivors), None)
        if twin_id:
            t = by_id[twin_id]
            r[col["lat"]], r[col["lon"]] = f"{t['coordinates']['latitude']:.7f}".rstrip("0"), f"{t['coordinates']['longitude']:.7f}".rstrip("0")
            note = f"coordinates aligned to OpenStreetMap '{t['name']}' on {datetime.now():%Y-%m-%d}; was approximate"
            r[col["address"]] = f"{r[col['address']].rstrip()} ({note})"
            aligned += 1
            log.append(f"CSV   '{name}' coordinates -> OSM twin {t['coordinates']['latitude']}, {t['coordinates']['longitude']}")
        # 7) blank category
        if not r[col["category"]].strip():
            for pat, cat in CATEGORY_BY_NAME:
                if re.search(pat, name, re.I):
                    r[col["category"]] = cat
                    log.append(f"CSV   '{name}' category '' -> '{cat}' (from its name)")
                    break
        keep_rows.append(r)

    report = [f"GroundZero duplicate cleanup {stamp}", f"master: {len(master)} -> {len(survivors)} records "
              f"({len(dropped)} dropped, {cleaned_names} names cleaned)",
              f"community csv: {len(rows)} -> {len(keep_rows)} rows ({aligned} coordinates aligned, {len(requeue)} re-queued)", ""]
    report += log + [""] + review_only(master, dropped)
    text = "\n".join(report)
    print(text)
    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    BACKUPS.mkdir(exist_ok=True)
    for p in (MASTER, COMMUNITY, QUEUE):
        if p.exists():
            shutil.copy2(p, BACKUPS / f"{p.stem}_before_dupclean_{stamp}{p.suffix}")

    MASTER.write_text(json.dumps(survivors, indent=2, ensure_ascii=False).replace("\n", "\r\n"), encoding="utf-8", newline="")
    with COMMUNITY.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(keep_rows)
    if requeue:
        existing = []
        if QUEUE.exists():
            with QUEUE.open(newline="", encoding="utf-8-sig") as f:
                existing = list(csv.DictReader(f))
        for r, why in requeue:
            cat = r[col["category"]]
            existing.append({
                "priority": "A - recommendable stop" if is_itinerary_eligible(cat) else "B - reference only (never scheduled in an itinerary)",
                "name": r[col["name"]], "category": cat, "address": r[col["address"]],
                "source_note": "Removed by clean_dataset_duplicates.py", "reason": f"unverified pin — {why}",
                "maps_link": google_maps_search_url(r[col["name"]], r[col["address"]]),
            })
        with QUEUE.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=QUEUE_COLUMNS, lineterminator="\r\n", extrasaction="ignore", restval="")
            w.writeheader()
            w.writerows(existing)
    IDS_OUT.write_text("\n".join(sorted(dropped)) + "\n", encoding="utf-8")
    REPORT.write_text(text, encoding="utf-8")
    print(f"\nWrote cleaned files. {len(dropped)} database id(s) listed in {IDS_OUT.name} — delete them from Postgres "
          "with scripts/delete_duplicate_places.py (re-importing only upserts).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
