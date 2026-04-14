"""
pipeline/engine1_pipeline.py  [v3 — Five-Layer Ground Zero Engine 1]

Master pipeline for Ground Zero Structured Data Layer.

PIPELINE STEPS:
  1. Data Collection    — OSM (14 groups), Wikidata, Wikipedia, OTM, Hidden Gems
  2. Normalisation      — OSM JSON → BaseEntity objects
  3. Cross-enrichment   — Wikidata / Wikipedia / OTM signals added to entities
  4. Hidden Gems merge  — curated local intelligence injected as BaseEntities
  5. Layer Population   — Layers 2–5 computed for every entity (NEW)
  6. Structural Scoring — SAS formula (Layer 1 + enrichment signals)
  7. Domain Scoring     — final_authenticity_score using all 5 layers (NEW)
  8. Data Quality Gate  — validates every entity before storage
  9. Bias Audit         — promotional language, source consensus check
  10. Database Storage   — SQLite with all layer data
  11. Hub Build          — city_store.json for HIVE Engine (Layer 2)

HOW TO RUN:
  python -m pipeline.engine1_pipeline              # full live run
  python -m pipeline.engine1_pipeline --dry-run    # no DB / disk writes
  python -m pipeline.engine1_pipeline --skip-osm  # use cached OSM data
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from data_collector.osm_collector import fetch_osm_places
from data_collector.wikidata_enricher import fetch_wikidata_places, build_wikidata_lookup, enrich_entity_with_wikidata
from data_collector.wikipedia_enricher import enrich_from_osm_raw
from data_collector.opentripmap_collector import fetch_otm_places, build_otm_name_lookup
from data_collector.normalizer import normalize_to_entities
from data_collector.mangalore_hidden_gems import get_hidden_gems
from data_core.layer_populator import LayerPopulator
from data_core.structural_validator import StructuralValidator
from data_core.domain_scorer import DomainScorer
from data_core.data_hub_builder import DataHubBuilder
from bias_guard.bias_auditor import audit_place
from data_storage.city_database import CityDatabase
from core.base_models import BaseEntity, Domain

logger = get_logger("Engine1Pipeline")

RAW_OSM_PATH   = "data_storage/raw/osm_mangalore_raw.json"
CITY_STORE_PATH = "data_storage/output/city_store.json"


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return {"opentripmap_key": os.getenv("OPENTRIPMAP_KEY", "")}


# ============================================================
# STEP 1: DATA COLLECTION
# ============================================================

def run_data_collection(skip_osm: bool, env: dict) -> dict:
    logger.info("━" * 60)
    logger.info("STEP 1 — Data Collection")
    logger.info("━" * 60)

    if skip_osm and os.path.exists(RAW_OSM_PATH):
        logger.info("  OSM: using cached data")
        osm_path = RAW_OSM_PATH
    else:
        logger.info("  OSM: fetching from Overpass API (14 query groups)...")
        osm_path = fetch_osm_places()

    logger.info("  Wikidata: SPARQL query for Mangalore places...")
    wikidata_places = fetch_wikidata_places()

    logger.info("  Wikipedia: enriching entities with descriptions...")
    wikipedia_enrichment = enrich_from_osm_raw(osm_path)

    otm_places = []
    if env.get("opentripmap_key"):
        logger.info("  OpenTripMap: fetching tourism POI data...")
        otm_places = fetch_otm_places(api_key=env["opentripmap_key"])
    else:
        logger.info("  OpenTripMap: skipped (no OPENTRIPMAP_KEY)")

    return {
        "osm_path": osm_path,
        "wikidata_places": wikidata_places,
        "wikipedia_enrichment": wikipedia_enrichment,
        "otm_places": otm_places,
    }


# ============================================================
# STEP 2: NORMALISATION
# ============================================================

def run_normalisation(osm_path: str) -> list:
    logger.info("━" * 60)
    logger.info("STEP 2 — Normalisation (OSM → BaseEntity)")
    logger.info("━" * 60)
    entities = normalize_to_entities(osm_path)
    logger.info(f"  Normalised {len(entities)} entities")
    return entities


# ============================================================
# STEP 3: CROSS-ENRICHMENT
# ============================================================

def run_enrichment(entities: list, collection: dict) -> list:
    logger.info("━" * 60)
    logger.info("STEP 3 — Cross-Source Enrichment")
    logger.info("━" * 60)

    wikidata_lookup  = build_wikidata_lookup(collection["wikidata_places"])
    wiki_enrichment  = collection["wikipedia_enrichment"]
    otm_lookup       = build_otm_name_lookup(collection["otm_places"])

    wd_hits = wp_hits = otm_hits = 0

    for entity in entities:
        wd = enrich_entity_with_wikidata(entity.decision_trace, wikidata_lookup)
        if wd:
            if "community_map" not in entity.sources:
                entity.sources.append("community_map")
            entity.decision_trace.append(
                f"WIKIDATA_ENRICHED:{json.dumps({'id': wd.get('wikidata_id'), 'description': wd.get('description','')[:80]})}"
            )
            wd_hits += 1

        osm_id = next((t.replace("OSM_ID:","").strip() for t in entity.decision_trace if t.startswith("OSM_ID:")), None)
        if osm_id and osm_id in wiki_enrichment:
            wp = wiki_enrichment[osm_id]
            if "public_media" not in entity.sources:
                entity.sources.append("public_media")
            entity.decision_trace.append(
                f"WIKIPEDIA_ENRICHED:{json.dumps({'title': wp.get('wikipedia_title'), 'quality': wp.get('quality_score')})}"
            )
            wp_hits += 1

        name_key = entity.name.lower().strip()
        if name_key in otm_lookup:
            otm = otm_lookup[name_key]
            entity.decision_trace.append(
                f"OTM_ENRICHED:{json.dumps({'xid': otm.get('otm_xid'), 'tourist_importance': otm.get('tourist_importance')})}"
            )
            otm_hits += 1

    logger.info(f"  Wikidata: {wd_hits} | Wikipedia: {wp_hits} | OTM: {otm_hits}")
    return entities


# ============================================================
# STEP 4: HIDDEN GEMS MERGE
# ============================================================

def run_hidden_gems_merge(entities: list) -> list:
    logger.info("━" * 60)
    logger.info("STEP 4 — Hidden Gems Merge (Mangalore Local Intelligence)")
    logger.info("━" * 60)

    gems = get_hidden_gems()
    existing_names = {e.name.lower().strip() for e in entities}
    added = 0

    for gem in gems:
        gem_name = gem.get("name", "").strip()
        if not gem_name or gem_name.lower() in existing_names:
            continue  # skip duplicates

        try:
            domain_str = gem.get("domain", "places")
            domain = Domain(domain_str) if domain_str in [d.value for d in Domain] else Domain.PLACES

            entity = BaseEntity(
                name=gem_name,
                domain=domain,
                category=gem.get("category", "general"),
                subcategory=gem.get("subcategory", "Point of Interest"),
                latitude=gem["latitude"],
                longitude=gem["longitude"],
                sources=["local_knowledge"]
            )

            # Store gem metadata in decision_trace for LayerPopulator to read
            meta = {
                "description":       gem.get("description", ""),
                "opening_hours":     gem.get("opening_hours"),
                "cuisine":           gem.get("cuisine"),
                "wikipedia":         gem.get("wikipedia"),
                "unexplored_flag":   gem.get("unexplored_signal", False),
                "hidden_gem_tier":   gem.get("hidden_gem_tier", 2),
                "best_time":         gem.get("best_time"),
                "feast_season":      gem.get("feast_season"),
                "tulu_cultural_tag": gem.get("tulu_cultural_tag"),
                "local_knowledge":   True,
            }
            entity.decision_trace.append(f"HG_META:{json.dumps(meta, ensure_ascii=False)}")
            entity.decision_trace.append("SOURCE:local_knowledge")

            # OSM structural score from gem data richness
            tag_score = 0.20
            if meta.get("description"): tag_score += 0.15
            if meta.get("opening_hours"): tag_score += 0.15
            if meta.get("cuisine"): tag_score += 0.08
            if meta.get("wikipedia"): tag_score += 0.12
            if meta.get("feast_season"): tag_score += 0.05
            entity.update_structural_score(round(min(tag_score, 1.0), 3))

            entities.append(entity)
            existing_names.add(gem_name.lower())
            added += 1

        except Exception as ex:
            logger.warning(f"  Gem error: {gem_name} — {ex}")
            continue

    logger.info(f"  Added {added} hidden gems ({len(gems) - added} skipped as duplicates)")
    return entities


# ============================================================
# STEP 5: LAYER POPULATION (NEW)
# ============================================================

def run_layer_population(entities: list) -> list:
    logger.info("━" * 60)
    logger.info("STEP 5 — Five-Layer Intelligence Population")
    logger.info("━" * 60)

    populator = LayerPopulator()
    errors = 0
    for entity in entities:
        try:
            populator.populate(entity)
        except Exception as e:
            logger.warning(f"  Layer error for '{entity.name}': {e}")
            errors += 1

    logger.info(f"  Layers populated: {len(entities) - errors} | Errors: {errors}")
    return entities


# ============================================================
# STEP 6: STRUCTURAL SCORING
# ============================================================

def run_scoring(entities: list) -> list:
    logger.info("━" * 60)
    logger.info("STEP 6 — Structural Scoring + Domain Scoring")
    logger.info("━" * 60)

    validator = StructuralValidator()
    scorer    = DomainScorer()
    grade_counts = {}

    for entity in entities:
        try:
            validator.compute(entity)
            scorer.compute(entity)
        except Exception as e:
            logger.warning(f"  Scoring error for '{entity.name}': {e}")

    for e in entities:
        g = e.grade.value
        grade_counts[g] = grade_counts.get(g, 0) + 1

    logger.info(f"  Grade breakdown: {grade_counts}")
    return entities


# ============================================================
# STEP 7: DATA QUALITY GATE
# ============================================================

def run_data_quality_gate(entities: list) -> tuple:
    """
    Hard quality validation before storage.
    Returns (valid_entities, rejected_count).
    """
    logger.info("━" * 60)
    logger.info("STEP 7 — Data Quality Gate")
    logger.info("━" * 60)

    valid, rejected, reasons = [], 0, {}

    for entity in entities:
        fail_reason = None

        if not entity.name or not entity.name.strip():
            fail_reason = "no_name"
        elif entity.latitude is None or entity.longitude is None:
            fail_reason = "no_coords"
        elif not (-90 <= entity.latitude <= 90) or not (-180 <= entity.longitude <= 180):
            fail_reason = "invalid_coords"
        elif not entity.sources:
            fail_reason = "no_sources"
        elif len(entity.name.strip()) < 2:
            fail_reason = "name_too_short"

        if fail_reason:
            rejected += 1
            reasons[fail_reason] = reasons.get(fail_reason, 0) + 1
        else:
            valid.append(entity)

    logger.info(f"  Valid: {len(valid)} | Rejected: {rejected}")
    if reasons:
        logger.info(f"  Rejection reasons: {reasons}")
    return valid, rejected


# ============================================================
# STEP 8: BIAS AUDIT
# ============================================================

def run_bias_audit(entities: list) -> tuple:
    logger.info("━" * 60)
    logger.info("STEP 8 — Bias Audit")
    logger.info("━" * 60)

    approved, rejected = [], 0

    for entity in entities:
        desc = _extract_description(entity)
        audit_payload = {
            "name":             entity.name,
            "description":      desc,
            "sources":          _map_sources(entity.sources),
            "structural_score": entity.structural_score
        }
        result = audit_place(audit_payload)
        if result["approved"]:
            approved.append(entity)
        else:
            rejected += 1
            entity.decision_trace.append(f"BIAS_AUDIT_REJECTED:{result['reason']}")

    logger.info(f"  Approved: {len(approved)} | Rejected: {rejected}")
    return approved, rejected


def _extract_description(entity: BaseEntity) -> str:
    for t in entity.decision_trace:
        for prefix in ("OSM_EXTRA:", "HG_META:"):
            if t.startswith(prefix):
                try:
                    return json.loads(t[len(prefix):]).get("description", "")
                except Exception:
                    pass
    return ""


def _map_sources(raw_sources: list) -> list:
    mapping = {
        "OSM": "community_map", "community_map": "community_map",
        "public_media": "public_media", "Government": "government",
        "TourismBoard": "government", "FieldSurvey": "field_observation",
        "local_knowledge": "field_observation", "user_behavior": "user_behavior"
    }
    return list(set(mapping.get(s, "community_map") for s in raw_sources))


# ============================================================
# STEP 9: DATABASE STORAGE
# ============================================================

def run_storage(entities: list, dry_run: bool) -> int:
    logger.info("━" * 60)
    logger.info("STEP 9 — Database Storage")
    logger.info("━" * 60)
    if dry_run:
        logger.info("  DRY RUN — skipping")
        return 0
    db = CityDatabase()
    count = db.upsert_entities(entities)
    logger.info(f"  Stored {count} entities | DB stats: {db.stats()}")
    return count


# ============================================================
# STEP 10: HUB BUILD
# ============================================================

def run_hub_build(entities: list, dry_run: bool) -> dict:
    logger.info("━" * 60)
    logger.info("STEP 10 — Data Hub Build (city_store.json)")
    logger.info("━" * 60)
    builder = DataHubBuilder()
    hub = builder.build(entities)
    if not dry_run:
        builder.save(hub, CITY_STORE_PATH)
    meta = hub.get("_meta", {})
    logger.info(f"  Hub entities: {meta.get('total_in_hub', 0)} across {meta.get('domains', [])}")
    return hub


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_engine1(skip_osm: bool = False, dry_run: bool = False):
    start = datetime.now(timezone.utc)

    logger.info("=" * 60)
    logger.info("GROUND ZERO — ENGINE 1: Structured Data Layer v3")
    logger.info(f"Started: {start.isoformat()} | Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info("=" * 60)

    env = load_env()

    collection     = run_data_collection(skip_osm=skip_osm, env=env)
    entities       = run_normalisation(collection["osm_path"])
    if not entities:
        logger.error("No entities normalised. Check OSM data.")
        return

    entities       = run_enrichment(entities, collection)
    entities       = run_hidden_gems_merge(entities)
    entities       = run_layer_population(entities)
    entities       = run_scoring(entities)
    valid_entities, dq_rejected = run_data_quality_gate(entities)
    approved, bias_rejected = run_bias_audit(valid_entities)
    stored         = run_storage(approved, dry_run)
    hub            = run_hub_build(approved, dry_run)

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    osm_count = _count_osm_elements(collection["osm_path"])

    logger.info("=" * 60)
    logger.info("ENGINE 1 — COMPLETE")
    logger.info(f"  OSM elements:          {osm_count}")
    logger.info(f"  Wikidata places:       {len(collection['wikidata_places'])}")
    logger.info(f"  Wikipedia enrichments: {len(collection['wikipedia_enrichment'])}")
    logger.info(f"  OTM places:            {len(collection['otm_places'])}")
    logger.info(f"  Hidden gems added:     {sum(1 for e in entities if 'local_knowledge' in e.sources)}")
    logger.info(f"  Entities normalised:   {len(entities)}")
    logger.info(f"  DQ gate rejected:      {dq_rejected}")
    logger.info(f"  Bias audit rejected:   {bias_rejected}")
    logger.info(f"  Approved + stored:     {len(approved)}")
    logger.info(f"  Duration:              {duration:.1f}s")
    logger.info("=" * 60)

    return hub


def _count_osm_elements(path: str) -> int:
    try:
        with open(path) as f:
            return len(json.load(f).get("elements", []))
    except Exception:
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ground Zero Engine 1")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--skip-osm",  action="store_true")
    args = parser.parse_args()
    run_engine1(skip_osm=args.skip_osm, dry_run=args.dry_run)
