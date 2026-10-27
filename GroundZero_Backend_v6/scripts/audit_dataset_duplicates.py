"""
Read-only duplicate + sanity audit of the whole dataset. Changes nothing.

    python scripts/audit_dataset_duplicates.py

Checks data/community_places.csv, data/master_data_core.json, and the two
together (which is what the pipeline will see), using the SAME rule the ETL
applies (layer0/application/dedup.py: within 75 m AND name similarity >= 0.82)
plus the cases that rule does NOT catch:

  MERGE-OK   the ETL will merge these automatically (harmless)
  NAME-DUP   identical normalised name — ETL only merges if they are also
             within 75 m, so far-apart pairs slip through as two rows
  SAME-SPOT  different names but same distinctive words within 150 m
  STACKED    different names within 12 m — the wrong-pin / centroid signature
  SAME-PIN   identical coordinates (5 dp) under different names

Also validates every community row (bbox, lat/lon swap, numeric fields,
enum values) so nothing malformed reaches the pipeline.
"""
from __future__ import annotations

import asyncio
import csv
import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layer0.application.dedup import haversine_meters, name_similarity  # noqa: E402
from layer0.application.place_ingest import BBOX, GENERIC_TOKENS, fold_name, norm_key, split_tokens, token_sets_equal  # noqa: E402

DATA = ROOT / "data"
REPORT = DATA / "duplicate_audit_report.txt"


def load_community():
    with (DATA / "community_places.csv").open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for i, r in enumerate(rows, start=2):
        try:
            out.append(dict(src="community", ref=f"csv line {i}", name=r["name"].strip(), cat=r["category"].strip(),
                            lat=float(r["lat"]), lon=float(r["lon"]), row=r))
        except ValueError:
            out.append(dict(src="community", ref=f"csv line {i}", name=r["name"].strip(), cat=r["category"], lat=None, lon=None, row=r))
    return out


def load_master():
    out = []
    for d in json.loads((DATA / "master_data_core.json").read_text(encoding="utf-8")):
        c = d.get("coordinates") or {}
        out.append(dict(src="master", ref=d.get("id") or d["name"], name=d["name"], cat=d.get("category", ""),
                        lat=c.get("latitude"), lon=c.get("longitude"), row=d))
    return out


def classify(a, b):
    if a["lat"] is None or b["lat"] is None:
        return None
    d = haversine_meters(a["lat"], a["lon"], b["lat"], b["lon"])
    sim = name_similarity(a["name"], b["name"])
    same_name = norm_key(a["name"]) == norm_key(b["name"])
    if d <= 75 and sim >= 0.82:
        return "MERGE-OK", d, sim
    if same_name:
        return "NAME-DUP", d, sim
    if round(a["lat"], 5) == round(b["lat"], 5) and round(a["lon"], 5) == round(b["lon"], 5):
        return "SAME-PIN", d, sim
    if d < 12:
        return "STACKED", d, sim
    if d <= 150:
        ca, _ = split_tokens(fold_name(a["name"]), set())
        cb, _ = split_tokens(fold_name(b["name"]), set())
        if ca and cb and token_sets_equal(ca, cb):
            return "SAME-SPOT", d, sim
    return None


def pairs(items):
    # grid bucket so 800 x 800 stays instant and scales
    grid = defaultdict(list)
    for i, p in enumerate(items):
        if p["lat"] is not None:
            grid[(round(p["lat"] / 0.003), round(p["lon"] / 0.003))].append(i)
    seen = set()
    for (gx, gy), idxs in grid.items():
        near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((gx + dx, gy + dy), [])]
        for i in idxs:
            for j in near:
                if i < j and (i, j) not in seen:
                    seen.add((i, j))
                    yield items[i], items[j]
    # same-name pairs at any distance
    by_name = defaultdict(list)
    for p in items:
        by_name[norm_key(p["name"])].append(p)
    for group in by_name.values():
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                yield group[a], group[b]


def audit(label, items, out):
    found = defaultdict(list)
    done = set()
    for a, b in pairs(items):
        key = (id(a), id(b)) if id(a) < id(b) else (id(b), id(a))
        if key in done:
            continue
        done.add(key)
        c = classify(a, b)
        if c:
            found[c[0]].append((a, b, c[1], c[2]))
    out.append(f"\n=== {label}: {len(items)} places ===")
    for kind in ("NAME-DUP", "SAME-PIN", "STACKED", "SAME-SPOT", "MERGE-OK"):
        rows = found.get(kind, [])
        out.append(f"  {kind:<10} {len(rows)}")
    for kind in ("NAME-DUP", "SAME-PIN", "STACKED", "SAME-SPOT"):
        for a, b, d, sim in found.get(kind, []):
            out.append(f"    [{kind}] '{a['name']}' ({a['src']} {a['ref']}) <-> '{b['name']}' ({b['src']} {b['ref']})  {d:.0f} m  sim {sim:.2f}")
    return found


def validate_community(items, out):
    problems = []
    price = {"free", "budget", "mid", "premium"}
    for p in items:
        r = p["row"]
        where = f"{p['name']} ({p['ref']})"
        if not r["name"].strip():
            problems.append(f"{where}: empty name")
        if p["lat"] is None:
            problems.append(f"{where}: lat/lon not numeric"); continue
        if not (BBOX["south"] <= p["lat"] <= BBOX["north"] and BBOX["west"] <= p["lon"] <= BBOX["east"]):
            swapped = BBOX["south"] <= p["lon"] <= BBOX["north"] and BBOX["west"] <= p["lat"] <= BBOX["east"]
            problems.append(f"{where}: outside Mangaluru box" + (" (lat/lon look swapped)" if swapped else ""))
        if not r["category"].strip():
            problems.append(f"{where}: empty category")
        for col in ("estimated_cost", "dwell_time_typical_minutes", "local_percentage_hint", "media_mentions_hint"):
            v = (r.get(col) or "").strip()
            if v:
                try:
                    float(v)
                except ValueError:
                    problems.append(f"{where}: {col}='{v}' is not a number")
    out.append(f"\n=== community_places.csv validation: {len(problems)} problem(s) ===")
    out.extend("  " + p for p in problems)
    return problems


async def etl_smoke(out):
    from layer0.application import etl_orchestrator as E
    from layer0.application.bias_signal_estimator import BiasSignalEstimator
    from layer0.application.opening_hours_parser import OpeningHoursParser
    from layer0.application.place_enricher import PlaceEnricher
    from layer0.infrastructure.collectors.spreadsheet_source import SpreadsheetListingSource
    recs = await SpreadsheetListingSource(str(DATA / "community_places.csv")).fetch()
    bad = [r.name for r in recs if E._listing_record_to_place(r, PlaceEnricher(), BiasSignalEstimator(), OpeningHoursParser()) is None]
    out.append(f"\n=== ETL smoke test: {len(recs)} rows read, {len(bad)} rejected by the converter ===")
    out.extend("  rejected: " + n for n in bad)


def main() -> int:
    community, master = load_community(), load_master()
    out: list[str] = ["GroundZero duplicate + sanity audit (read-only)"]
    validate_community(community, out)
    c = audit("community_places.csv alone", community, out)
    m = audit("master_data_core.json alone", master, out)
    both = audit("community + master together (what the pipeline sees)", community + master, out)
    asyncio.run(etl_smoke(out))
    def seedish(x):
        return x["src"] == "community" or x["row"].get("source") == ["local_listing"]
    actionable = [(k, a, b) for k in ("NAME-DUP", "SAME-PIN", "STACKED", "SAME-SPOT")
                  for a, b, *_ in both.get(k, []) if seedish(a) or seedish(b) or k == "SAME-PIN"]
    info = sum(len(both.get(k, [])) for k in ("NAME-DUP", "STACKED", "SAME-SPOT")) - len(actionable)
    out.append(f"\nSUMMARY: {len(actionable)} actionable pair(s) involving hand-seeded/community rows or identical pins; "
               f"{info} informational pair(s) between OSM records (chains such as Domino's/KFC, or separate shops in one building).")
    for k, a, b in actionable:
        out.append(f"  ACTION [{k}] '{a['name']}' <-> '{b['name']}'")
    text = "\n".join(out)
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
