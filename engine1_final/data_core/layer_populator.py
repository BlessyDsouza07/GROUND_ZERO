"""
data_core/layer_populator.py

Five-Layer Intelligence Populator for Ground Zero.

Takes a BaseEntity (already normalized from OSM) and populates:
  Layer 2: ContextualLayer  — best_time, crowd, family_friendly, energy, rain_suitable
  Layer 3: BehavioralLayer  — dwell_time, repeat_visits, peak_hours, fatigue_index
  Layer 4: AuthenticityLayer— source_count, agreement, gov_verified, bias, freshness
  Layer 5: ExperienceLayer  — experience_type, emotion_score, sensory_profile,
                               local_secrets_index, silence_suitability

ALL values are computed deterministically from:
  - entity.domain + entity.category + entity.subcategory
  - OSM_EXTRA tags (hours, cuisine, wheelchair, description, etc.)
  - decision_trace signals (WIKIDATA_ENRICHED, OTM_ENRICHED, etc.)
  - Hidden gem flags (unexplored_flag, hidden_gem_tier)

FORMULA REFERENCE (Ground Zero report §4.5.1):
  AuthenticityLayer.compute_formula_score() is the canonical formula.
  Used by DomainScorer as an input signal to final_authenticity_score.
"""

import json
import math
from datetime import datetime, timezone
from typing import List, Dict, Optional

from core.base_models import (
    BaseEntity, Domain,
    ContextualLayer, BehavioralLayer, AuthenticityLayer, ExperienceLayer
)
from utils.logger import get_logger

logger = get_logger("LayerPopulator")


class LayerPopulator:
    """
    Call populate(entity) after normalization and enrichment,
    before structural validation and domain scoring.
    """

    def populate(self, entity: BaseEntity) -> None:
        """Populate all 5 layers in place. Does not return."""
        extra = self._extract_extra(entity)
        trace_flags = self._extract_trace_flags(entity)

        self._populate_contextual(entity, extra, trace_flags)
        self._populate_behavioral(entity, extra, trace_flags)
        self._populate_authenticity(entity, extra, trace_flags)
        self._populate_experience(entity, extra, trace_flags)

        entity.decision_trace.append("LAYERS_POPULATED:contextual,behavioral,authenticity,experience")

    # ──────────────────────────────────────────────────────────
    # LAYER 2: CONTEXTUAL
    # ──────────────────────────────────────────────────────────

    def _populate_contextual(self, entity: BaseEntity, extra: dict, flags: dict) -> None:
        ctx = entity.contextual
        d   = entity.domain
        sub = entity.subcategory.lower()
        cat = entity.category.lower()

        # ── best_time_to_visit ───────────────────────────────
        hours = extra.get("opening_hours", "")
        if any(x in sub for x in ("beach", "nature", "waterfall", "viewpoint", "lake")):
            ctx.best_time_to_visit = "morning or evening"
        elif "night" in hours or "nightclub" in cat or "bar" in cat or "pub" in cat:
            ctx.best_time_to_visit = "evening or night"
        elif any(x in sub for x in ("market", "bazaar", "fish market")):
            ctx.best_time_to_visit = "early morning"
        elif any(x in sub for x in ("museum", "gallery", "church", "temple", "mosque")):
            ctx.best_time_to_visit = "morning or afternoon"
        elif d in (Domain.FOOD,):
            ctx.best_time_to_visit = "lunch or dinner"
        elif d in (Domain.STAY, Domain.TRANSPORT):
            ctx.best_time_to_visit = "any"
        else:
            ctx.best_time_to_visit = "morning"

        # From hidden gem best_time override
        if flags.get("best_time"):
            ctx.best_time_to_visit = flags["best_time"]

        # ── crowd_level ──────────────────────────────────────
        if flags.get("unexplored_flag") or flags.get("hidden_gem_tier", 99) == 1:
            ctx.crowd_level = "low"
        elif any(x in sub for x in ("beach", "stadium", "shopping mall", "bus station")):
            ctx.crowd_level = "high"
        elif any(x in sub for x in ("museum", "gallery", "nature reserve")):
            ctx.crowd_level = "low"
        elif d in (Domain.FOOD, Domain.STAY):
            ctx.crowd_level = "medium"
        else:
            ctx.crowd_level = "medium"

        # ── avg_duration_minutes ─────────────────────────────
        duration_map = {
            "beach": 90, "nature reserve": 75, "park": 60,
            "museum": 90, "gallery": 60, "heritage building": 45,
            "hindu temple": 30, "church / chapel": 25, "mosque / dargah": 25,
            "tourist attraction": 60, "waterfall": 45,
            "hotel": 480, "hostel": 480, "guest house": 480,
            "cafe / coffee shop": 45, "restaurant": 60,
            "ice cream / desserts": 20, "fast food": 15,
            "seafood restaurant": 60, "street food stall": 10,
            "bus station / ksrtc": 15, "railway station": 20,
            "shopping mall": 90, "bazaar / marketplace": 45, "fish market": 30,
            "swimming pool": 60, "sports centre": 90, "gym": 60,
            "spa & wellness": 90, "viewpoint": 20,
        }
        ctx.avg_duration_minutes = duration_map.get(sub, 30)
        if flags.get("avg_duration_override"):
            ctx.avg_duration_minutes = flags["avg_duration_override"]

        # ── family_friendly ──────────────────────────────────
        not_family = {"bar", "pub", "nightclub", "nightclub / live music"}
        ctx.family_friendly = sub not in not_family

        # ── solo_safe ────────────────────────────────────────
        ctx.solo_safe = True  # default; unsafe if only remote + no crowd
        if flags.get("unexplored_flag") and ctx.crowd_level == "low":
            ctx.solo_safe = False  # remote unexplored at night unsafe solo

        # ── rain_suitable ────────────────────────────────────
        indoor_subs = {
            "museum", "gallery", "hotel", "hostel", "guest house",
            "shopping mall", "cinema / movie hall", "theatre / performing arts",
            "café / coffee shop", "restaurant", "library", "sports centre",
            "swimming pool", "gym / fitness centre", "arts & culture centre"
        }
        ctx.rain_suitable = sub in indoor_subs

        # ── energy_required ──────────────────────────────────
        high_energy = {"waterfall", "nature reserve", "hill / hillock", "hiking",
                       "sports centre", "gym / fitness centre", "adventure sport"}
        low_energy  = {"museum", "gallery", "café / coffee shop", "library",
                       "hotel", "viewpoint", "place of worship", "street food stall"}
        if any(x in sub for x in high_energy):
            ctx.energy_required = "high"
        elif any(x in sub for x in low_energy):
            ctx.energy_required = "low"
        else:
            ctx.energy_required = "moderate"

        if flags.get("energy_required"):
            ctx.energy_required = flags["energy_required"]

        # ── weather_sensitive ────────────────────────────────
        weather_sensitive_subs = {"beach", "waterfall", "viewpoint", "estuary beach",
                                   "nature reserve", "tidal", "river ferry crossing"}
        ctx.weather_sensitive = any(x in sub for x in weather_sensitive_subs)

        # ── best_weather_condition ───────────────────────────
        ctx.best_weather_condition = "any" if ctx.rain_suitable else "clear"

        # ── walking_distance_m (rough estimate by area) ──────
        if d == Domain.TRANSPORT:      ctx.walking_distance_m = 0
        elif d == Domain.FOOD:         ctx.walking_distance_m = 250
        elif d in (Domain.PLACES, Domain.EXPLORE): ctx.walking_distance_m = 400
        else:                          ctx.walking_distance_m = 300

        # ── age suitability ──────────────────────────────────
        if "nightclub" in sub or "bar" in sub or "pub" in sub:
            ctx.age_suitable_min = 21
        elif "waterfall" in sub or "adventure" in sub:
            ctx.age_suitable_min = 8
        else:
            ctx.age_suitable_min = 0
        ctx.age_suitable_max = 99

        # ── silence_trigger ──────────────────────────────────
        # System should speak only when tourist approaches — high value moments
        trigger_subs = {"beach", "temple", "church", "mosque", "viewpoint",
                        "waterfall", "heritage building", "museum", "festival"}
        ctx.silence_trigger = any(x in sub for x in trigger_subs) or bool(flags.get("hidden_gem_tier"))

    # ──────────────────────────────────────────────────────────
    # LAYER 3: BEHAVIORAL
    # ──────────────────────────────────────────────────────────

    def _populate_behavioral(self, entity: BaseEntity, extra: dict, flags: dict) -> None:
        beh = entity.behavioral
        sub = entity.subcategory.lower()
        d   = entity.domain

        # ── tourist_dwell_time_min ───────────────────────────
        # Reality = 70–90% of expected duration (tourists often leave early)
        expected = entity.contextual.avg_duration_minutes
        beh.expected_dwell_time_min = expected
        beh.tourist_dwell_time_min = max(5, int(expected * 0.78))

        # ── repeat_visit_probability ─────────────────────────
        repeat_high  = {"beach", "café / coffee shop", "market", "bazaar", "temple",
                         "park", "viewpoint"}
        repeat_low   = {"museum", "heritage building", "tourist attraction"}
        if any(x in sub for x in repeat_high):
            beh.repeat_visit_probability = 0.65
        elif any(x in sub for x in repeat_low):
            beh.repeat_visit_probability = 0.15
        else:
            beh.repeat_visit_probability = 0.35

        # Unexplored places: low repeat (hard to find twice)
        if flags.get("unexplored_flag"):
            beh.repeat_visit_probability = max(0.2, beh.repeat_visit_probability - 0.2)

        # ── drop_off_rate ────────────────────────────────────
        # Fraction who leave before completing the experience
        if "market" in sub or "festival" in sub:
            beh.drop_off_rate = 0.10  # low — people stay till done
        elif "museum" in sub or "gallery" in sub:
            beh.drop_off_rate = 0.35  # some find it too long
        elif "beach" in sub:
            beh.drop_off_rate = 0.08  # people settle in
        elif d == Domain.FOOD:
            beh.drop_off_rate = 0.05  # stay to eat
        else:
            beh.drop_off_rate = 0.20

        # ── peak_hours ───────────────────────────────────────
        peak_map = {
            "beach":           [17, 18, 19, 7, 8],
            "fish market":     [5, 6, 7, 8],
            "temple":          [6, 7, 17, 18],
            "church":          [7, 8, 18],
            "mosque":          [6, 12, 17, 18, 19],
            "café":            [8, 9, 10, 16, 17],
            "restaurant":      [12, 13, 19, 20, 21],
            "museum":          [10, 11, 15, 16],
            "market":          [9, 10, 11, 18, 19],
            "bus station":     [6, 7, 8, 17, 18],
            "railway station": [6, 7, 8, 16, 17, 18],
            "viewpoint":       [6, 17, 18],
            "festival":        [18, 19, 20, 21],
        }
        for keyword, hours in peak_map.items():
            if keyword in sub:
                beh.peak_hours = hours
                break
        if not beh.peak_hours:
            beh.peak_hours = [10, 11, 16, 17]

        # ── confusion_zone ───────────────────────────────────
        # Places where tourists commonly get lost / confused
        beh.confusion_zone = (
            flags.get("unexplored_flag") is True or
            "village" in sub or "hamlet" in sub or
            "quarter" in entity.subcategory.lower()
        )

        # ── decision_point ───────────────────────────────────
        # Transport hubs, junctions, ferry points = tourist decision points
        beh.decision_point = (
            d == Domain.TRANSPORT or
            "ferry" in sub or "junction" in entity.name.lower() or
            "station" in sub
        )

        # ── high_miss_probability ────────────────────────────
        # Easy to walk past without noticing?
        beh.high_miss_probability = (
            flags.get("hidden_gem_tier", 0) == 1 or
            "street vendor" in sub or
            "alley" in entity.name.lower() or
            flags.get("unexplored_flag") is True
        )

        # ── fatigue_index ────────────────────────────────────
        fatigue_map = {
            "waterfall": 0.7, "hill": 0.7, "nature reserve": 0.6,
            "beach": 0.3, "museum": 0.4, "restaurant": 0.1,
            "temple": 0.25, "market": 0.5, "festival": 0.5,
        }
        for keyword, fatigue in fatigue_map.items():
            if keyword in sub:
                beh.fatigue_index = fatigue
                break
        else:
            beh.fatigue_index = 0.3

    # ──────────────────────────────────────────────────────────
    # LAYER 4: AUTHENTICITY
    # ──────────────────────────────────────────────────────────

    def _populate_authenticity(self, entity: BaseEntity, extra: dict, flags: dict) -> None:
        auth = entity.authenticity

        # ── source_count ─────────────────────────────────────
        auth.source_count = len(entity.sources)
        if auth.source_count == 0:
            auth.source_count = 1

        # ── source_agreement_score ───────────────────────────
        # More distinct source types → higher agreement
        type_map = {
            "OSM": "community", "community_map": "community",
            "public_media": "media", "Government": "government",
            "TourismBoard": "government", "FieldSurvey": "field",
            "local_knowledge": "local",
        }
        types = set(type_map.get(s, "other") for s in entity.sources)
        auth.source_agreement_score = round(min(len(types) / 4.0, 1.0), 3)

        # ── gov_verified ─────────────────────────────────────
        auth.gov_verified = any(s in ("Government", "TourismBoard") for s in entity.sources)
        if extra.get("heritage") or extra.get("heritage_ref"):
            auth.gov_verified = True

        # ── wiki_verified ─────────────────────────────────────
        auth.wiki_verified = bool(extra.get("wikipedia") or extra.get("wikidata"))
        for t in entity.decision_trace:
            if t.startswith("WIKIDATA_ENRICHED") or t.startswith("WIKIPEDIA_ENRICHED"):
                auth.wiki_verified = True
                break

        # ── cross_ref_count ──────────────────────────────────
        cross_refs = 0
        if extra.get("wikipedia"): cross_refs += 1
        if extra.get("wikidata"):  cross_refs += 1
        for t in entity.decision_trace:
            if t.startswith("OTM_ENRICHED"): cross_refs += 1; break
            if t.startswith("WIKIDATA_ENRICHED"): cross_refs += 1; break
        if auth.gov_verified: cross_refs += 1
        if flags.get("local_knowledge"): cross_refs += 1
        auth.cross_ref_count = cross_refs

        # ── promotion_bias_score ─────────────────────────────
        # Check description for promotional language
        desc = (extra.get("description") or "").lower()
        promo_words = {"best", "must visit", "viral", "trending", "famous",
                       "luxury", "exclusive", "hidden gem", "instagrammable"}
        hits = sum(1 for w in promo_words if w in desc)
        auth.promotion_bias_score = round(min(hits * 0.15, 1.0), 3)

        # ── freshness_score ──────────────────────────────────
        # OSM data has edit timestamps — approximate from established date
        established = str(extra.get("established", "") or extra.get("start_date", "") or "")
        try:
            # Handle 3-digit years (e.g. "968"), 4-digit (e.g. "1910"), full dates (e.g. "1910-01-01")
            year_str = established.strip().split("-")[0].strip()
            year = int(year_str) if year_str.isdigit() else 2000
            age = max(0, 2026 - year)
            # Ancient temples = very stable = high freshness
            # New restaurants = less stable = medium freshness
            if age > 500:    auth.freshness_score = 0.9  # ancient — documented
            elif age > 50:   auth.freshness_score = 0.75
            elif age > 10:   auth.freshness_score = 0.6
            else:            auth.freshness_score = 0.5
        except Exception:
            auth.freshness_score = 0.55  # default for unknown age

        # ── last_verified ────────────────────────────────────
        auth.last_verified = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # ── local_validation ─────────────────────────────────
        auth.local_validation = flags.get("local_knowledge", False)
        if flags.get("hidden_gem_tier", 0) == 1:
            auth.local_validation = True

        # ── anomaly_flag ─────────────────────────────────────
        auth.anomaly_flag = auth.promotion_bias_score > 0.5

    # ──────────────────────────────────────────────────────────
    # LAYER 5: EXPERIENCE
    # ──────────────────────────────────────────────────────────

    def _populate_experience(self, entity: BaseEntity, extra: dict, flags: dict) -> None:
        exp = entity.experience
        sub = entity.subcategory.lower()
        d   = entity.domain
        name = entity.name.lower()

        # ── experience_type ──────────────────────────────────
        types = []
        if any(x in sub for x in ("beach", "waterfall", "nature", "lake", "wetland")):
            types.append("natural")
        if any(x in sub for x in ("temple", "mosque", "church", "dargah", "shrine")):
            types.extend(["spiritual", "cultural"])
        if any(x in sub for x in ("museum", "gallery", "heritage", "monument", "ruins")):
            types.append("historical")
        if d == Domain.FOOD:
            types.append("gastronomic")
        if any(x in sub for x in ("market", "bazaar", "festival", "cultural")):
            types.append("cultural")
        if any(x in sub for x in ("viewpoint", "lighthouse", "hilltop", "peak")):
            types.append("scenic")
        if entity.contextual.crowd_level == "low":
            types.append("peaceful")
        elif entity.contextual.crowd_level == "high":
            types.append("vibrant")
        if flags.get("unexplored_flag") or flags.get("hidden_gem_tier", 99) <= 2:
            types.append("authentic")
        if any(x in sub for x in ("sports", "swimming", "adventure", "gym")):
            types.append("active")
        if extra.get("feast_season") or extra.get("festival"):
            types.append("festive")

        exp.experience_type = list(dict.fromkeys(types))  # deduplicate preserving order

        # ── emotion_score (from §2.7 Talavera et al.) ────────
        # Positive signals: peaceful, natural, spiritual, gastronomic, authentic
        # Negative signals: crowded, tourist_trap, high fatigue
        # Neutral: informational, transit, shopping
        positive_types = {"natural", "spiritual", "gastronomic", "peaceful", "authentic",
                          "scenic", "historical", "festive"}
        neutral_types  = {"informational", "transit", "shopping"}

        positive_count = sum(1 for t in types if t in positive_types)
        neutral_count  = sum(1 for t in types if t in neutral_types)
        total = max(len(types), 1)

        pos_raw = min(positive_count / total, 1.0)
        neu_raw = min(neutral_count / total, 1.0)

        # Crowd penalty
        if entity.contextual.crowd_level == "high": pos_raw *= 0.85
        # Authentic bonus
        if "authentic" in types or flags.get("hidden_gem_tier", 99) == 1: pos_raw = min(pos_raw + 0.1, 1.0)
        # Fatigue penalty
        if entity.behavioral.fatigue_index > 0.6: neu_raw += 0.1

        neg_raw = max(0.0, 1.0 - pos_raw - neu_raw)

        # Normalise to sum = 1.0
        total_e = pos_raw + neu_raw + neg_raw
        if total_e > 0:
            p = round(pos_raw / total_e, 2)
            nu = round(neu_raw / total_e, 2)
            ne = round(max(0.0, 1.0 - p - nu), 2)  # ensure exact sum = 1.0
            exp.emotion_score = {"positive": p, "neutral": nu, "negative": ne}

        # ── sensory_profile ──────────────────────────────────
        sensory = {}
        if any(x in sub for x in ("beach", "coastal", "estuary")):
            sensory["sound"] = "waves and wind"
            sensory["smell"] = "salt air and sea"
            sensory["visual"] = "open horizon"
        elif any(x in sub for x in ("temple", "church", "mosque")):
            sensory["sound"] = "bells / call to prayer / silence"
            sensory["smell"] = "incense / flowers"
            sensory["visual"] = "architectural grandeur"
        elif any(x in sub for x in ("market", "bazaar", "fish market")):
            sensory["sound"] = "vendors and crowds"
            sensory["smell"] = "spices and fresh produce"
            sensory["visual"] = "colour and movement"
        elif d == Domain.FOOD:
            sensory["sound"] = "kitchen noise and conversation"
            sensory["smell"] = "cooking aromas"
            sensory["visual"] = "food preparation and plating"
        elif any(x in sub for x in ("waterfall", "river", "lake", "wetland")):
            sensory["sound"] = "flowing water and birds"
            sensory["smell"] = "earth and moisture"
            sensory["visual"] = "natural water feature"
        exp.sensory_profile = sensory

        # ── local_secrets_index ──────────────────────────────
        # 0.0 = famous tourist spot, 1.0 = known only to locals
        tier = flags.get("hidden_gem_tier", 3)
        unexplored = flags.get("unexplored_flag", False)
        if tier == 1 and unexplored:
            exp.local_secrets_index = 0.95
        elif tier == 1:
            exp.local_secrets_index = 0.80
        elif tier == 2:
            exp.local_secrets_index = 0.55
        else:
            exp.local_secrets_index = 0.20

        # Known wikipedia = less secret
        if extra.get("wikipedia"): exp.local_secrets_index *= 0.7
        exp.local_secrets_index = round(min(exp.local_secrets_index, 1.0), 3)

        # ── tourist_reality_gap ──────────────────────────────
        # Mismatch between expectation and reality
        # Famous places often disappoint (positive gap → over-delivers if unknown)
        if "vibrant" in types and entity.contextual.crowd_level == "high":
            exp.tourist_reality_gap = 0.3   # crowded places often disappoint
        elif flags.get("unexplored_flag"):
            exp.tourist_reality_gap = -0.2  # unknowns often pleasantly surprise
        else:
            exp.tourist_reality_gap = 0.1

        # ── silence_suitability ──────────────────────────────
        # How suitable is this for the Ground Zero silence engine single-sentence nudge?
        if "peaceful" in types and entity.contextual.crowd_level == "low":
            exp.silence_suitability = 0.9
        elif "spiritual" in types:
            exp.silence_suitability = 0.85
        elif "historical" in types or "scenic" in types:
            exp.silence_suitability = 0.75
        elif entity.contextual.crowd_level == "high":
            exp.silence_suitability = 0.3  # too noisy for a quiet nudge
        else:
            exp.silence_suitability = 0.5

    # ──────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────

    def _extract_extra(self, entity: BaseEntity) -> dict:
        for t in entity.decision_trace:
            if t.startswith("OSM_EXTRA:"):
                try:
                    return json.loads(t.replace("OSM_EXTRA:", ""))
                except Exception:
                    pass
        # Also try HG_META (hidden gems metadata)
        for t in entity.decision_trace:
            if t.startswith("HG_META:"):
                try:
                    return json.loads(t.replace("HG_META:", ""))
                except Exception:
                    pass
        return {}

    def _extract_trace_flags(self, entity: BaseEntity) -> dict:
        flags: dict = {}
        for t in entity.decision_trace:
            if t.startswith("OSM_EXTRA:"):
                try:
                    extra = json.loads(t.replace("OSM_EXTRA:", ""))
                    if extra.get("unexplored_flag"): flags["unexplored_flag"] = True
                except Exception:
                    pass
            if t.startswith("HG_META:"):
                try:
                    meta = json.loads(t.replace("HG_META:", ""))
                    flags.update(meta)
                except Exception:
                    pass
        return flags
