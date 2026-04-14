"""
data_core/data_hub_builder.py  [v3 — Five-Layer Hub]

Builds the city_store.json consumed by the HIVE Engine (Layer 2).
Every entity is serialised with all 5 intelligence layers.
"""

import json, os
from datetime import datetime, timezone
from typing import List, Dict
from core.base_models import BaseEntity, Domain
from utils.logger import get_logger

logger = get_logger("DataHubBuilder")
MIN_THRESHOLD = 0.25  # minimum final_authenticity_score to enter hub


class DataHubBuilder:

    def build(self, entities: List[BaseEntity]) -> Dict:
        groups: Dict[Domain, List[BaseEntity]] = {}
        for e in entities:
            if e.final_authenticity_score < MIN_THRESHOLD:
                continue
            groups.setdefault(e.domain, []).append(e)

        hub: Dict = {}
        total_in_hub = 0
        for domain, items in groups.items():
            ranked = sorted(items, key=lambda e: e.final_authenticity_score, reverse=True)
            hub[domain.value] = [self._serialize(e, i + 1) for i, e in enumerate(ranked)]
            total_in_hub += len(ranked)

        grade_counts = {}
        for e in entities:
            g = e.grade.value
            grade_counts[g] = grade_counts.get(g, 0) + 1

        hub["_meta"] = {
            "generated_at":        datetime.now(timezone.utc).isoformat(),
            "total_entities":      len(entities),
            "total_in_hub":        total_in_hub,
            "filtered_below_threshold": len(entities) - total_in_hub,
            "min_threshold":       MIN_THRESHOLD,
            "grade_breakdown":     grade_counts,
            "domains":             [k for k in hub.keys() if k != "_meta"],
            "engine_version":      "v3-five-layer",
        }
        return hub

    def save(self, hub: Dict, file_path: str = "data_storage/output/city_store.json"):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(hub, f, indent=2, ensure_ascii=False)
        logger.info(f"Hub saved → {file_path}")

    def _serialize(self, e: BaseEntity, rank: int) -> Dict:
        extra  = self._extract_extra(e)
        osm_id = next((t.replace("OSM_ID:", "").strip() for t in e.decision_trace if t.startswith("OSM_ID:")), None)

        return {
            "rank":       rank,
            "entity_id":  e.entity_id,
            "osm_id":     osm_id,
            "name":       e.name,
            "domain":     e.domain.value,
            "category":   e.category,
            "subcategory": e.subcategory,

            # ── Layer 1: Structural ──────────────────────────
            "structural": {
                "coordinates": {"latitude": e.latitude, "longitude": e.longitude},
                "address":     extra.get("address"),
                "phone":       extra.get("phone"),
                "email":       extra.get("email"),
                "website":     extra.get("website"),
                "opening_hours": extra.get("opening_hours"),
                "cuisine":     extra.get("cuisine"),
                "stars":       extra.get("stars"),
                "wheelchair":  extra.get("wheelchair"),
                "description": extra.get("description"),
                "image_url":   extra.get("image_url"),
                "price_info":  extra.get("price_info"),
                "wifi":        extra.get("wifi"),
                "outdoor_seating": extra.get("outdoor_seating"),
                "takeaway":    extra.get("takeaway"),
                "vegetarian":  extra.get("vegetarian"),
                "halal":       extra.get("halal"),
                "elevation_m": extra.get("elevation_m"),
                "capacity":    extra.get("capacity"),
            },

            # ── Cultural Identity ────────────────────────────
            "cultural": {
                "alt_name":       extra.get("alt_name"),
                "name_kannada":   extra.get("name_kannada"),
                "name_tulu":      extra.get("name_tulu"),
                "name_malayalam": extra.get("name_malayalam"),
                "religion":       extra.get("religion"),
                "denomination":   extra.get("denomination"),
                "deity":          extra.get("deity"),
                "festival":       extra.get("festival") or extra.get("feast_season"),
                "heritage":       extra.get("heritage"),
                "established":    extra.get("established"),
                "wikipedia":      extra.get("wikipedia"),
                "wikidata":       extra.get("wikidata"),
                "sport":          extra.get("sport"),
                "tulu_cultural_tag": extra.get("tulu_cultural_tag"),
            },

            # ── Layer 2: Contextual ──────────────────────────
            "contextual": e.contextual.to_dict(),

            # ── Layer 3: Behavioral ──────────────────────────
            "behavioral": e.behavioral.to_dict(),

            # ── Layer 4: Authenticity ────────────────────────
            "authenticity": {
                **e.authenticity.to_dict(),
                "formula_score": e.authenticity.compute_formula_score(),
            },

            # ── Layer 5: Experience ──────────────────────────
            "experience": e.experience.to_dict(),

            # ── Exploration flags ────────────────────────────
            "exploration": {
                "unexplored_flag":    extra.get("unexplored_flag", False),
                "hidden_gem_tier":    extra.get("hidden_gem_tier"),
                "local_secrets_index": e.experience.local_secrets_index,
                "silence_suitability": e.experience.silence_suitability,
                "fishing":    extra.get("fishing"),
                "boat_access": extra.get("boat_access"),
                "seasonal":   extra.get("seasonal"),
                "tidal":      extra.get("tidal"),
                "access":     extra.get("access"),
                "best_time":  extra.get("best_time"),
                "feast_season": extra.get("feast_season"),
            },

            # ── Scores & Sources ─────────────────────────────
            "scores": {
                "structural":        e.structural_score,
                "final_authenticity": e.final_authenticity_score,
                "grade":             e.grade.value,
                "formula_score":     e.authenticity.compute_formula_score(),
            },
            "sources": e.sources,
            "bias_transparency": {
                "sources_count":        len(e.sources),
                "source_agreement":     e.authenticity.source_agreement_score,
                "promotion_bias_score": e.authenticity.promotion_bias_score,
                "gov_verified":         e.authenticity.gov_verified,
                "wiki_verified":        e.authenticity.wiki_verified,
                "anomaly_flag":         e.authenticity.anomaly_flag,
            },
            "derived_signals":  e.derived_signals.to_dict(),
            "last_updated":     e.last_updated.isoformat(),
        }

    def _extract_extra(self, entity: BaseEntity) -> dict:
        for t in entity.decision_trace:
            for prefix in ("OSM_EXTRA:", "HG_META:"):
                if t.startswith(prefix):
                    try:
                        return json.loads(t[len(prefix):])
                    except Exception:
                        pass
        return {}
