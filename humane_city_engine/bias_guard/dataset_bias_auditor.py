"""
bias_guard/dataset_bias_auditor.py

DATASET BIAS AUDITOR  — v2 (structure-corrected)
─────────────────────────────────────────────────────────────
Runs the full bias guard pipeline over your collected datasets.

Supports both output file formats:
  data_core/mangalore_rare_enriched.json
    places = LIST of {name, sources:[str], data:{osm:{lat,lon,tags}, ...}}

  data_storage/mangalore_deep_intel.json
    records = LIST of {name, geo_data:{latitude,longitude}, sources:[str], ...}

Usage:
  python -m bias_guard.dataset_bias_auditor --all
  python -m bias_guard.dataset_bias_auditor --input data_core/mangalore_rare_enriched.json
  python -m bias_guard.dataset_bias_auditor --input data_storage/mangalore_deep_intel.json
  python -m bias_guard.dataset_bias_auditor --all --no-save
"""

import argparse
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from bias_guard.bias_auditor       import audit_place
from bias_guard.promo_filter       import contains_promotional_bias
from bias_guard.consensus_engine   import has_consensus
from bias_guard.authenticity_score import calculate_authenticity_score
from bias_guard.source_registry    import ALLOWED_SOURCE_TYPES


# ════════════════════════════════════════════════════════════
# SOURCE MAPPING
# Maps your collector source strings → bias_guard allowed types
# ════════════════════════════════════════════════════════════

SOURCE_MAP = {
    # Collector labels → bias_guard source types
    "osm":                   "community_map",
    "OSM":                   "community_map",
    "wikidata":              "public_media",
    "wikipedia":             "public_media",
    "wikipedia_geo":         "public_media",
    "asi":                   "government",
    "ASI":                   "government",
    "open_meteo":            "government",
    "GBIF":                  "government",
    "GBIF / OBIS":           "government",
    "commons":               "public_media",
    "Wikimedia Commons":     "public_media",
    "OpenStreetMap":         "community_map",
    "Wikidata":              "public_media",
    "Wikipedia":             "public_media",
    "curated_model":         "field_observation",
    "synthetic_time_model":  "field_observation",
    "ASI Heritage List (curated seed)": "government",
    "GBIF marine occurrence data":      "government",
}

def _map_sources(raw_sources: List[str]) -> List[str]:
    """Convert collector source strings → bias_guard allowed source types."""
    mapped = set()
    for s in raw_sources:
        if not s:           # skip empty strings
            continue
        if s in SOURCE_MAP:
            mapped.add(SOURCE_MAP[s])
        elif s in ALLOWED_SOURCE_TYPES:
            mapped.add(s)
        # Partial matches for long source strings
        elif "osm" in s.lower() or "openstreet" in s.lower():
            mapped.add("community_map")
        elif "wiki" in s.lower() or "wikipedia" in s.lower():
            mapped.add("public_media")
        elif "gov" in s.lower() or "gbif" in s.lower() or "asi" in s.lower():
            mapped.add("government")
    return list(mapped)


# ════════════════════════════════════════════════════════════
# RECORD ADAPTERS
# Convert each file's format → what audit_place() expects:
# {"name":str, "description":str, "latitude":float,
#  "longitude":float, "sources":[allowed_type_strings]}
# ════════════════════════════════════════════════════════════

def _adapt_rare_enriched(record: Dict) -> Dict:
    """
    rare_enriched format:
    {
      "name":    "Panambur Beach",
      "sources": ["osm", "wikidata"],
      "data": {
        "osm":     {"lat":12.95, "lon":74.80, "tags":{...}},
        "wikidata": {...}
      }
    }
    """
    name    = record.get("name", "")
    sources = _map_sources(record.get("sources", []))

    # Extract lat/lon — try osm first, then any sub-source
    lat, lon = None, None
    data = record.get("data", {})
    for src_key in ["osm", "wikidata", "wikipedia_geo", "asi"]:
        sub = data.get(src_key, {})
        if sub.get("lat") and sub.get("lon"):
            lat = sub["lat"]
            lon = sub["lon"]
            break

    # Extract description from tags or wikidata
    desc = ""
    osm_tags = data.get("osm", {}).get("tags", {})
    desc = (osm_tags.get("description") or
            osm_tags.get("note") or
            data.get("wikidata", {}).get("description", "") or
            "")

    return {
        "name":        name,
        "description": str(desc),
        "latitude":    lat,
        "longitude":   lon,
        "sources":     sources,
    }


def _adapt_deep_intel(record: Dict) -> Dict:
    """
    deep_intel format:
    {
      "name":       "Panambur Beach",
      "sources":    ["osm", "wikipedia", "open_meteo"],
      "geo_data":   {"latitude":12.95, "longitude":74.80, ...},
      "review_data":{"wiki_description":"...", ...},
      ...
    }
    """
    name    = record.get("name", "")
    sources = _map_sources(record.get("sources", []))

    geo     = record.get("geo_data", {})
    lat     = geo.get("latitude")
    lon     = geo.get("longitude")

    review  = record.get("review_data", {})
    desc    = review.get("wiki_description", "")

    return {
        "name":        name,
        "description": str(desc),
        "latitude":    lat,
        "longitude":   lon,
        "sources":     sources,
    }


# ════════════════════════════════════════════════════════════
# CORE AUDIT ENGINE
# ════════════════════════════════════════════════════════════

def audit_dataset(records: List[Dict],
                  adapter_fn,
                  dataset_label: str) -> Dict:
    """
    Run full bias audit over a list of records.
    Attaches bias_guard result to each record in-place.
    Returns full audit report.
    """
    print(f"\n  Auditing: {dataset_label}")
    print(f"  Records:  {len(records)}")
    print(f"  {'─'*50}")

    approved            = []
    rejected            = []
    rejection_reasons:  Dict[str, int] = {}
    score_buckets       = {"0.0-0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}

    for record in records:
        adapted = adapter_fn(record)
        result  = audit_place(adapted)

        ts = datetime.now(timezone.utc).isoformat()

        if result["approved"]:
            score = result.get("authenticity_score", 0)
            # Track score distribution
            if   score < 0.3: score_buckets["0.0-0.3"] += 1
            elif score < 0.6: score_buckets["0.3-0.6"] += 1
            elif score < 0.8: score_buckets["0.6-0.8"] += 1
            else:             score_buckets["0.8-1.0"] += 1

            record["bias_guard"] = {
                "approved":          True,
                "authenticity_score": round(score, 3),
                "audited_at":        ts,
            }
            approved.append(record)
        else:
            reason = result.get("reason", "Unknown")
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            record["bias_guard"] = {
                "approved":   False,
                "reason":     reason,
                "audited_at": ts,
            }
            rejected.append(record)

    total        = len(records)
    approval_pct = round(len(approved) / total * 100, 1) if total else 0

    # Print summary
    print(f"  ✓ Approved:  {len(approved):>5}  ({approval_pct}%)")
    print(f"  ✗ Rejected:  {len(rejected):>5}  ({100-approval_pct}%)")

    if rejection_reasons:
        print(f"\n  Rejection breakdown:")
        for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
            pct = round(count / total * 100, 1)
            print(f"    {reason:<45} {count:>5}  ({pct}%)")

    if approved:
        print(f"\n  Authenticity score distribution (approved records):")
        for bucket, count in score_buckets.items():
            bar = "█" * min(40, int(count / max(1,len(approved)) * 40))
            print(f"    {bucket}  {bar} {count}")

    return {
        "dataset":           dataset_label,
        "total":             total,
        "approved":          len(approved),
        "rejected":          len(rejected),
        "approval_rate_pct": approval_pct,
        "rejection_reasons": rejection_reasons,
        "score_distribution":score_buckets,
        "approved_records":  approved,
        "rejected_records":  rejected,
    }


# ════════════════════════════════════════════════════════════
# ANALYSIS MODULES
# ════════════════════════════════════════════════════════════

def analyse_source_distribution(records: List[Dict],
                                 adapter_fn) -> Dict:
    """Show source coverage across dataset."""
    source_counts:    Dict[str, int] = {}
    mapped_counts:    Dict[str, int] = {}
    single_source  = 0
    multi_source   = 0

    for r in records:
        adapted  = adapter_fn(r)
        raw_srcs = r.get("sources", [])
        mapped   = adapted["sources"]

        for s in raw_srcs:
            if s: source_counts[s] = source_counts.get(s, 0) + 1
        for s in mapped:
            if s: mapped_counts[s] = mapped_counts.get(s, 0) + 1

        if len(mapped) <= 1:  single_source += 1
        else:                  multi_source  += 1

    return {
        "raw_source_counts":    dict(sorted(source_counts.items(), key=lambda x: -x[1])),
        "mapped_source_counts": dict(sorted(mapped_counts.items(), key=lambda x: -x[1])),
        "single_source_places": single_source,
        "multi_source_places":  multi_source,
        "multi_source_pct":     round(multi_source / len(records) * 100, 1) if records else 0,
    }


def check_geo_bias(records: List[Dict], adapter_fn) -> Dict:
    """Check geographic distribution of records."""
    CENTRE_LAT, CENTRE_LON = 12.9141, 74.8560

    def dist(lat, lon):
        R, p = 6371, math.pi / 180
        a = (math.sin((lat - CENTRE_LAT) * p / 2) ** 2 +
             math.cos(CENTRE_LAT * p) * math.cos(lat * p) *
             math.sin((lon - CENTRE_LON) * p / 2) ** 2)
        return 2 * R * math.asin(math.sqrt(a))

    inner, mid, outer, no_geo = 0, 0, 0, 0

    for r in records:
        adapted = adapter_fn(r)
        lat = adapted.get("latitude")
        lon = adapted.get("longitude")
        if not lat or not lon:
            no_geo += 1
            continue
        try:
            d = dist(float(lat), float(lon))
            if d < 2:    inner += 1
            elif d < 6:  mid   += 1
            else:        outer += 1
        except:
            no_geo += 1

    total = inner + mid + outer or 1
    return {
        "inner_ring_lt_2km":   inner,
        "mid_ring_2_6km":      mid,
        "outer_ring_gt_6km":   outer,
        "no_geo_data":         no_geo,
        "centre_bias_pct":     round(inner / total * 100, 1),
        "bias_warning":        (inner / total) > 0.5,
        "note": ("⚠ OSM data naturally over-represents city centre — expected"
                 if (inner / total) > 0.5 else
                 "✓ Geographic distribution looks balanced"),
    }


def scan_promo_bias(records: List[Dict], adapter_fn) -> List[Dict]:
    """Find records with promotional language in descriptions."""
    flagged = []
    for r in records:
        adapted = adapter_fn(r)
        desc = adapted.get("description", "")
        if desc and contains_promotional_bias(desc):
            flagged.append({
                "name":    adapted.get("name", ""),
                "excerpt": desc[:120],
            })
    return flagged


# ════════════════════════════════════════════════════════════
# MAIN RUNNER
# ════════════════════════════════════════════════════════════

def run_all(save_cleaned: bool = True):
    """Audit all datasets and optionally save cleaned versions."""

    os.makedirs("data_core",    exist_ok=True)
    os.makedirs("data_storage", exist_ok=True)

    full_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets":     [],
    }

    print(f"\n{'═'*55}")
    print(f"  DATASET BIAS AUDITOR")
    print(f"  Using bias_guard: promo_filter + consensus + authenticity")
    print(f"{'═'*55}")

    # ── Dataset 1: rare_enriched ────────────────────────────
    path1 = "data_core/mangalore_rare_enriched.json"
    if os.path.exists(path1):
        print(f"\n  Loading {path1}...")
        data   = json.load(open(path1, encoding="utf-8"))
        places = data.get("places", [])

        # rare_enriched places is a LIST (sorted by orchestrator)
        if isinstance(places, dict):
            places = list(places.values())

        print(f"  Loaded {len(places)} place records")

        result = audit_dataset(places, _adapt_rare_enriched, "mangalore_rare_enriched")

        # Source + geo analysis
        src_dist  = analyse_source_distribution(places, _adapt_rare_enriched)
        geo_bias  = check_geo_bias(result["approved_records"], _adapt_rare_enriched)
        promo     = scan_promo_bias(places, _adapt_rare_enriched)

        print(f"\n  Source distribution:")
        for src, cnt in src_dist["raw_source_counts"].items():
            print(f"    {src:<30} {cnt:>5}")
        print(f"  Multi-source verified: {src_dist['multi_source_pct']}%")

        print(f"\n  Geographic distribution:")
        print(f"    Inner ring <2km:  {geo_bias['inner_ring_lt_2km']}")
        print(f"    Mid ring 2-6km:   {geo_bias['mid_ring_2_6km']}")
        print(f"    Outer ring >6km:  {geo_bias['outer_ring_gt_6km']}")
        print(f"    {geo_bias['note']}")

        if promo:
            print(f"\n  ⚠ Promotional language detected in {len(promo)} records")

        full_report["datasets"].append({
            **{k: v for k, v in result.items()
               if k not in ("approved_records", "rejected_records")},
            "source_distribution": src_dist,
            "geo_bias":            geo_bias,
            "promo_flagged":       len(promo),
        })

        if save_cleaned:
            data["places"] = result["approved_records"]
            data["bias_audit"] = {
                "approved":          result["approved"],
                "rejected":          result["rejected"],
                "approval_rate_pct": result["approval_rate_pct"],
                "audited_at":        full_report["generated_at"],
            }
            out = "data_core/mangalore_rare_enriched_clean.json"
            json.dump(data, open(out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            size = os.path.getsize(out) / 1024
            print(f"\n  ✓ Saved cleaned → {out}  ({size:.0f} KB)")

    else:
        print(f"\n  ⚠ Not found: {path1} — run rare_data_orchestrator first")

    # ── Dataset 2: deep_intel ───────────────────────────────
    path2 = "data_storage/mangalore_deep_intel.json"
    if os.path.exists(path2):
        print(f"\n  {'─'*50}")
        print(f"  Loading {path2}...")
        data    = json.load(open(path2, encoding="utf-8"))
        records = data.get("records", [])
        print(f"  Loaded {len(records)} place records")

        result  = audit_dataset(records, _adapt_deep_intel, "mangalore_deep_intel")

        geo_bias = check_geo_bias(result["approved_records"], _adapt_deep_intel)
        src_dist = analyse_source_distribution(records, _adapt_deep_intel)

        print(f"\n  Source distribution:")
        for src, cnt in src_dist["raw_source_counts"].items():
            if src: print(f"    {src:<30} {cnt:>5}")

        print(f"\n  Geographic distribution:")
        print(f"    Inner ring <2km:  {geo_bias['inner_ring_lt_2km']}")
        print(f"    Mid ring 2-6km:   {geo_bias['mid_ring_2_6km']}")
        print(f"    Outer ring >6km:  {geo_bias['outer_ring_gt_6km']}")
        print(f"    {geo_bias['note']}")

        full_report["datasets"].append({
            **{k: v for k, v in result.items()
               if k not in ("approved_records", "rejected_records")},
            "source_distribution": src_dist,
            "geo_bias":            geo_bias,
        })

        if save_cleaned:
            data["records"] = result["approved_records"]
            data["meta"]["bias_audited"]  = True
            data["meta"]["bias_approved"] = result["approved"]
            data["meta"]["bias_rejected"] = result["rejected"]
            out = "data_storage/mangalore_deep_intel_clean.json"
            json.dump(data, open(out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            size = os.path.getsize(out) / (1024 * 1024)
            print(f"\n  ✓ Saved cleaned → {out}  ({size:.1f} MB)")

    else:
        print(f"\n  ⚠ Not found: {path2} — run deep_intelligence_collector first")

    # ── Final report ────────────────────────────────────────
    rpath = "data_core/bias_audit_report.json"
    json.dump(full_report,
              open(rpath, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"\n{'═'*55}")
    print(f"  AUDIT COMPLETE")
    for ds in full_report["datasets"]:
        print(f"  {ds['dataset']:<35} "
              f"{ds['approved']:>5} approved / "
              f"{ds['rejected']:>5} rejected  "
              f"({ds['approval_rate_pct']}%)")
    print(f"  Full report → {rpath}")
    print(f"{'═'*55}\n")

    return full_report


# ════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Bias Guard — audit collected place datasets"
    )
    parser.add_argument("--input",    help="Path to a single JSON dataset file")
    parser.add_argument("--all",      action="store_true",
                        help="Audit all datasets (rare_enriched + deep_intel)")
    parser.add_argument("--no-save",  action="store_true",
                        help="Skip saving cleaned output files")
    args = parser.parse_args()

    if args.all or not args.input:
        run_all(save_cleaned=not args.no_save)

    elif args.input:
        if not os.path.exists(args.input):
            print(f"ERROR: File not found: {args.input}")
            return

        print(f"\n  Loading {args.input}...")
        data = json.load(open(args.input, encoding="utf-8"))

        # Auto-detect format
        if "records" in data:
            records    = data["records"]
            adapter_fn = _adapt_deep_intel
            print(f"  Detected format: deep_intel ({len(records)} records)")
        elif "places" in data:
            records = data["places"]
            if isinstance(records, dict):
                records = list(records.values())
            adapter_fn = _adapt_rare_enriched
            print(f"  Detected format: rare_enriched ({len(records)} records)")
        else:
            print("  ERROR: Unrecognised file format "
                  "(expected 'records' or 'places' key)")
            return

        result = audit_dataset(records, adapter_fn,
                               os.path.basename(args.input))

        src_dist = analyse_source_distribution(records, adapter_fn)
        geo_bias = check_geo_bias(result["approved_records"], adapter_fn)

        print(f"\n  Source distribution:")
        for src, cnt in src_dist["raw_source_counts"].items():
            if src: print(f"    {src:<30} {cnt:>5}")
        print(f"\n  Geographic distribution:")
        print(f"    Inner <2km: {geo_bias['inner_ring_lt_2km']}  "
              f"Mid 2-6km: {geo_bias['mid_ring_2_6km']}  "
              f"Outer >6km: {geo_bias['outer_ring_gt_6km']}")
        print(f"    {geo_bias['note']}")

        if not args.no_save:
            out = args.input.replace(".json", "_clean.json")
            if "records" in data:
                data["records"] = result["approved_records"]
            else:
                data["places"]  = result["approved_records"]
            json.dump(data, open(out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            print(f"\n  ✓ Saved cleaned → {out}")


if __name__ == "__main__":
    main()