"""
Adds the places in data/new_places_to_geocode.csv to the dataset — cleanly,
in the exact community_places.csv schema, with real coordinates only.

    python scripts/ingest_new_places.py            # apply (backs everything up first)
    python scripts/ingest_new_places.py --dry-run  # report only, write nothing
    python scripts/ingest_new_places.py --online   # ALSO try live Nominatim for the rest
                                                   #   (needs internet; ~1 request/sec)

What it does, in order
----------------------
1. Cleans the queue (stray empty column, whitespace, duplicate rows, rows
   that are the same place under two names).
2. Skips anything already in data/community_places.csv or in
   data/master_data_core.json (same name, or same spot + similar name).
3. Finds a REAL coordinate for each remaining row, first match wins:
     a. a hand-checked pin you typed into the queue's `pin_lat` / `pin_lon`
        columns (paste "12.8815, 74.8464" straight from Google Maps);
     b. a confirmed feature in your offline OSM extract (data/mangaluru.osm.pbf)
        — zero network, zero rate limit. Matching is deliberately strict; see
        layer0/application/place_ingest.py for the exact rules;
     c. (only with --online) a validated Nominatim result restricted to the
        Mangaluru bounding box.
4. Writes the resolved rows to data/community_places.csv (full schema,
   category normalised to the shared vocabulary, blanks left blank so the
   ETL applies its documented category priors), neighbourhood names to
   data/mangaluru_localities.csv (reference only — an area is not a stop),
   and everything it could NOT verify back to the queue with a plain-English
   reason and a ready-made Google Maps link.

Nothing is ever guessed. A row that cannot be verified stays in the queue —
that is the whole point (see scripts/audit_duplicate_coordinates.py for why).
Every file it changes is copied to data/backups/ first.

After it finishes, run the pipeline (POST /admin/pipeline/run or
scripts/run_periodic_pipeline.py) so the new rows get enriched, bias-scored
and stored in Postgres.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layer0.application.place_ingest import (  # noqa: E402
    BBOX, KnownPlace, OsmFeature, Resolution, build_community_row, build_locality_index,
    collides_with_other_place, find_existing, fold_name, google_maps_search_url, in_bbox,
    norm_key, osm_confirms_category, resolve_from_osm, split_tokens, token_sets_equal,
)
from shared.place_taxonomy import canonical_category, is_itinerary_eligible  # noqa: E402

DATA = ROOT / "data"
COMMUNITY_PATH = DATA / "community_places.csv"
QUEUE_PATH = DATA / "new_places_to_geocode.csv"
MASTER_PATH = DATA / "master_data_core.json"
PBF_PATH = DATA / "mangaluru.osm.pbf"
LOCALITIES_PATH = DATA / "mangaluru_localities.csv"
BACKUP_DIR = DATA / "backups"
REPORT_PATH = DATA / "ingest_last_report.txt"

QUEUE_COLUMNS = ["priority", "name", "category", "address", "source_note", "reason", "maps_link",
                 "pin_lat", "pin_lon", "osm_ref", "pin_source", "pin_note"]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "GroundZero-Mangaluru-DatasetEnrichment/2.0 (academic project; contact via project owner)"


# ----------------------------------------------------------------------- IO
def read_queue(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for raw in reader:
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None and (k or "").strip()}
            if row.get("name"):
                rows.append(row)
        return rows


def read_community(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        return header, [r for r in reader if any(c.strip() for c in r)]


def load_known(header: list[str], rows: list[list[str]]) -> list[KnownPlace]:
    ni, ci, la, lo = (header.index(c) for c in ("name", "category", "lat", "lon"))
    known: list[KnownPlace] = []
    for r in rows:
        try:
            known.append(KnownPlace(r[ni], r[ci], float(r[la]), float(r[lo])))
        except (ValueError, IndexError):
            continue
    if MASTER_PATH.exists():
        for p in json.loads(MASTER_PATH.read_text(encoding="utf-8")):
            c = p.get("coordinates") or {}
            if c.get("latitude") is not None:
                known.append(KnownPlace(p["name"], p.get("category", ""), c["latitude"], c["longitude"]))
    return known


def load_osm_features(pbf: Path) -> list[OsmFeature]:
    try:
        import osmium  # type: ignore
    except ImportError:
        print("  (osmium not installed -> offline OSM matching skipped; `pip install osmium`)")
        return []
    if not pbf.exists():
        print(f"  (no extract at {pbf} -> offline OSM matching skipped)")
        return []

    name_keys = ("name", "name:en", "alt_name", "official_name", "short_name", "old_name", "loc_name")
    keep = ("amenity", "shop", "tourism", "historic", "leisure", "natural", "religion", "denomination", "building",
            "man_made", "public_transport", "railway", "highway", "aeroway", "healthcare", "cuisine", "place",
            "waterway", "opening_hours", "phone", "brand")

    class Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.out: list[OsmFeature] = []

        def _add(self, kind, oid, tags, lat, lon):
            names: list[str] = []
            for k in name_keys:
                v = tags.get(k)
                if v:
                    names.extend(x.strip() for x in v.split(";") if x.strip())
            if not names:
                return
            uniq = tuple(dict.fromkeys(names))
            primary = len(dict.fromkeys(
                x.strip() for k in ("name", "name:en") for x in (tags.get(k) or "").split(";") if x.strip()))
            self.out.append(OsmFeature(kind, oid, uniq, lat, lon,
                                       {k: tags[k] for k in keep if k in tags}, primary_count=primary))

        def node(self, n):
            if n.location.valid():
                self._add("n", n.id, n.tags, n.location.lat, n.location.lon)

        def way(self, w):
            if not len(w.tags):
                return
            try:
                pts = [(x.lat, x.lon) for x in w.nodes if x.location.valid()]
            except Exception:  # noqa: BLE001 - a broken way must never abort the run
                return
            if pts:
                self._add("w", w.id, w.tags, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    h = Handler()
    h.apply_file(str(pbf), locations=True)
    return h.out


def backup(path: Path, stamp: str) -> None:
    if path.exists():
        BACKUP_DIR.mkdir(exist_ok=True)
        shutil.copy2(path, BACKUP_DIR / f"{path.stem}_before_ingest_{stamp}{path.suffix}")


# --------------------------------------------------------------- pins / online
def parse_pin(row: dict) -> tuple[float, float] | None:
    a, b = row.get("pin_lat", "").strip(), row.get("pin_lon", "").strip()
    try:
        if a and not b and "," in a:
            a, b = [x.strip() for x in a.split(",", 1)]
        return (float(a), float(b)) if a and b else None
    except ValueError:
        return None


def nominatim_resolve(name: str, category: str, localities: dict) -> Resolution:
    """Live Nominatim, restricted to the Mangaluru box, accepted only when the
    returned feature's own name matches and its OSM class/type confirms the
    category. Area-level results (suburb/city/boundary) are exactly the
    centroid fallback that caused the earlier collisions — always rejected."""
    import httpx

    cat = canonical_category(category)
    core, _ = split_tokens(fold_name(name), set(localities))
    if not core:
        return Resolution("unresolved", "name too generic for a safe online lookup")
    params = {
        "q": f"{name}, Mangaluru", "format": "jsonv2", "limit": 5, "extratags": 1, "namedetails": 1,
        "viewbox": f"{BBOX['west']},{BBOX['north']},{BBOX['east']},{BBOX['south']}", "bounded": 1,
    }
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = httpx.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=12.0)
            resp.raise_for_status()
            results = resp.json()
            break
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_err = exc
            time.sleep(2 * attempt)
    else:
        return Resolution("unresolved", f"online lookup failed (network): {last_err}")

    good = []
    for r in results:
        lat, lon = float(r["lat"]), float(r["lon"])
        if not in_bbox(lat, lon) or r.get("category") in {"boundary", "place"}:
            continue
        tags = {r.get("category", ""): r.get("type", ""), **(r.get("extratags") or {})}
        if not osm_confirms_category(cat, tags):
            continue
        names = list((r.get("namedetails") or {}).values()) or [r.get("name") or r.get("display_name", "").split(",")[0]]
        if any(token_sets_equal(core, split_tokens(fold_name(n), set(localities))[0]) for n in names):
            good.append((lat, lon, r))
    if not good:
        return Resolution("unresolved", "no validated online match")
    from layer0.application.place_ingest import CLUSTER_METERS, haversine_m
    if any(haversine_m(good[0][0], good[0][1], g[0], g[1]) > CLUSTER_METERS for g in good[1:]):
        return Resolution("unresolved", "ambiguous online match")
    lat, lon, r = good[0]
    time.sleep(1.1)  # Nominatim usage policy
    return Resolution("resolved", lat=round(lat, 7), lon=round(lon, 7), method="nominatim")


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--online", action="store_true", help="also query live Nominatim for rows the extract can't confirm")
    ap.add_argument("--pbf", type=Path, default=PBF_PATH)
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    header, community_rows = read_community(COMMUNITY_PATH)
    queue = read_queue(QUEUE_PATH)
    known = load_known(header, community_rows)
    print(f"queue rows: {len(queue)} | already known places: {len(known)}")

    features = load_osm_features(args.pbf)
    localities = build_locality_index(features)
    # queue's own locality names ("Kadri", "Bejai"...) count as localities too
    print(f"osm features: {len(features)} | locality names indexed: {len(localities)}")

    added_rows: list[list[str]] = []
    locality_rows: list[list[str]] = []
    remaining: list[dict] = []
    stats: Counter = Counter()
    log: list[str] = []
    seen_core: dict[tuple, str] = {}

    for q in queue:
        name = " ".join(q["name"].split())
        q["name"] = name
        cat = canonical_category(q.get("category", ""))
        core, _ = split_tokens(fold_name(name), set(localities))

        # 1) same place typed twice inside the queue
        key = (cat, frozenset(core)) if core else None
        if key and key in seen_core:
            stats["duplicate inside queue"] += 1
            log.append(f"DUP-IN-QUEUE   {name}  (same as '{seen_core[key]}')")
            continue

        # 2) already in the dataset (by name)
        hit = find_existing(name, cat, None, None, known, set(localities))
        if hit:
            stats["already in dataset"] += 1
            log.append(f"ALREADY-HAVE   {name}  (= '{hit.name}')")
            continue

        # 3) resolve a real coordinate
        pin = parse_pin(q)
        ref = q.get("osm_ref", "").strip()
        if ref:
            # A researched alias: the row IS this exact OSM feature (identity
            # checked against web sources; see pin_source / pin_note). The
            # coordinate is copied from the extract, never typed by hand.
            kind, _, oid = ref.partition("/")
            feat = next((f for f in features if f.kind == kind[:1] and str(f.osm_id) == oid), None)
            res = (Resolution("resolved", lat=round(feat.lat, 7), lon=round(feat.lon, 7), feature=feat, method="osm_alias")
                   if feat else Resolution("unresolved", f"osm_ref {ref} not found in the extract"))
        elif pin:
            res = (Resolution("resolved", lat=pin[0], lon=pin[1], method="manual_pin")
                   if in_bbox(*pin) else Resolution("unresolved", "pinned coordinate is outside Mangaluru"))
        else:
            res = resolve_from_osm(name, cat, q.get("address", ""), features, localities)
            if res.status != "resolved" and args.online and cat != "locality":
                online = nominatim_resolve(name, cat, localities)
                res = online if online.status == "resolved" else res

        if res.status != "resolved":
            q["reason"] = res.reason
            remaining.append(q)
            stats["needs a verified pin"] += 1
            continue

        # 4) safety checks on the coordinate itself
        if cat != "locality":
            dup = find_existing(name, cat, res.lat, res.lon, known, set(localities))
            if dup:
                stats["already in dataset"] += 1
                log.append(f"ALREADY-HAVE   {name}  (same spot as '{dup.name}')")
                continue
            clash = collides_with_other_place(res.lat, res.lon, name, known)
            if clash:
                q["reason"] = f"coordinate lands on top of a different place ('{clash.name}') — likely a wrong pin"
                remaining.append(q)
                stats["needs a verified pin"] += 1
                continue

        if key:
            seen_core[key] = name

        if cat == "locality":
            locality_rows.append([name, res.lat, res.lon, res.feature.url if res.feature else ""])
            stats["localities (reference file)"] += 1
            log.append(f"LOCALITY       {name} -> {res.lat}, {res.lon}")
            continue

        curator = {"manual_pin": "ingest_manual_pin", "nominatim": "ingest_nominatim",
                   "osm_alias": "ingest_osm_alias"}.get(res.method, "ingest_osm_extract")
        added_rows.append(build_community_row(header, q, res, curator))
        known.append(KnownPlace(name, cat, res.lat, res.lon))
        stats[f"added via {res.method}"] += 1
        log.append(f"ADDED          {name} [{cat}] -> {res.lat}, {res.lon}  ({res.method})")

    # 5) queue write-back: leftover rows get a reason + maps link + empty pin cells
    # Pin the recommendable stops first: only itinerary-eligible categories
    # can ever appear in a tourist's day, so those are worth the 30 seconds
    # a Google Maps pin takes. Everything else is reference data.
    for q in remaining:
        q["maps_link"] = google_maps_search_url(q["name"], q.get("address", ""))
        q.setdefault("pin_lat", "")
        q.setdefault("pin_lon", "")
        specific = "," in q.get("address", "") and q.get("address", "").strip().lower() not in {
            "mangaluru, karnataka, india", "mangaluru, karnataka", "mangaluru"}
        if is_itinerary_eligible(q.get("category")):
            q["priority"] = "A - recommendable stop" if specific else "A - recommendable stop (address is vague: search by name)"
        else:
            q["priority"] = "B - reference only (never scheduled in an itinerary)"
    # Within a priority, mosques go last: most are "<area> Juma Masjid" rows
    # that a tourist itinerary rarely wants, and they take the longest to pin.
    remaining.sort(key=lambda r: (r["priority"][0], canonical_category(r.get("category")) != "heritage_site" and False,
                                  (r.get("category") or "").lower() == "mosque", r.get("category", ""), r["name"].lower()))

    lines = [
        f"GroundZero ingest report {stamp}",
        f"  queue rows read ........... {len(queue)}",
        *[f"  {k:<28} {v}" for k, v in sorted(stats.items())],
        "", *log,
    ]
    report = "\n".join(lines)
    print("\n" + "\n".join(lines[:12]))

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    for p in (COMMUNITY_PATH, QUEUE_PATH, LOCALITIES_PATH):
        backup(p, stamp)

    if added_rows:
        tmp = COMMUNITY_PATH.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\r\n")
            w.writerow(header)
            w.writerows(community_rows)
            w.writerows(added_rows)
        tmp.replace(COMMUNITY_PATH)

    if locality_rows:
        existing = set()
        if LOCALITIES_PATH.exists():
            with LOCALITIES_PATH.open(newline="", encoding="utf-8") as f:
                existing = {r["name"] for r in csv.DictReader(f)}
        new_loc = [r for r in locality_rows if r[0] not in existing]
        write_header = not LOCALITIES_PATH.exists()
        with LOCALITIES_PATH.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\r\n")
            if write_header:
                w.writerow(["name", "lat", "lon", "osm_url"])
            w.writerows(new_loc)

    with QUEUE_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=QUEUE_COLUMNS, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(remaining)

    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nWrote: {len(added_rows)} place(s) -> {COMMUNITY_PATH.name}, "
          f"{len(locality_rows)} locality(ies) -> {LOCALITIES_PATH.name}, "
          f"{len(remaining)} still queued -> {QUEUE_PATH.name}")
    print(f"Full per-row report: {REPORT_PATH.relative_to(ROOT)} | backups in data/backups/")
    print("Next: run the pipeline (POST /admin/pipeline/run) to enrich and store the new rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
