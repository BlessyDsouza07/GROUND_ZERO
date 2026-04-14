"""
bias_guard/human_travel_guide_score.py

THE HUMAN TRAVEL GUIDE SCORE
════════════════════════════════════════════════════════════════════════
A score that thinks the way a deeply knowledgeable, ethical local guide
would — someone who has lived in Mangalore their whole life, knows every
neighbourhood, knows which places the tourists go vs where residents
actually live, and cares deeply about giving you an honest answer.

NOT what exists today:
  ✗ stars / ratings
  ✗ review counts
  ✗ popularity
  ✗ "hidden gem" hype
  ✗ influencer signals

WHAT THIS PRODUCES — 2 MASTER SCORES per place:

  1. PLACE TRUTH SCORE (0–100)
     "How real, complete, and trustworthy is the data about this place?"
     Built from 6 pillars: existence, identity, completeness,
     source integrity, temporal validity, community anchoring

  2. HUMAN FIT SCORE (0–100)
     "How good is this place for a real human being right now?"
     Built from 5 dimensions: local life evidence, accessibility equity,
     cultural integrity, experience reality, time suitability

  Combined → COMPANION SCORE (0–100)
     The one number your app uses. A human travel guide's verdict.
     70+ = confidently recommend
     50–69 = recommend with context
     30–49 = present with caution
     <30  = do not surface

ALSO PRODUCES per record:
  - grade:           S / A / B / C / D  (not just A-D)
  - confidence:      HIGH / MEDIUM / LOW / UNCERTAIN
  - companion_voice: A single sentence the app can speak as its own voice
  - repair_flags:    What data is missing and how to fix it
  - decision_trace:  Every scoring step, fully auditable

FORMULA DESIGN PRINCIPLES:
  1. Every sub-score comes from actual data fields in your JSONs
  2. Missing data is penalised — not ignored and not assumed
  3. Positive local signals actively increase score
  4. Negative signals (tourist trap, colonial bias, hype) actively decrease it
  5. The score is domain-aware — a beach is scored differently from a hospital
  6. The formula is fully transparent — every number has a name and a reason

RUN:
  python -m bias_guard.human_travel_guide_score --all
  python -m bias_guard.human_travel_guide_score --input data_storage/mangalore_deep_intel.json
  python -m bias_guard.human_travel_guide_score --place "Panambur Beach"
"""

import argparse
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════
# DOMAIN DEFINITIONS
# Each domain has different weights — what matters for a temple
# is different from what matters for a restaurant
# ════════════════════════════════════════════════════════════════

DOMAIN_PROFILES = {
    # domain_key: (place_truth_weight, human_fit_weight, name)
    "food":          (0.40, 0.60, "Food & Drink"),
    "nature":        (0.35, 0.65, "Nature & Outdoors"),
    "culture":       (0.55, 0.45, "Culture & Heritage"),
    "spiritual":     (0.60, 0.40, "Spiritual & Religious"),
    "market":        (0.40, 0.60, "Markets & Commerce"),
    "transport":     (0.70, 0.30, "Transport & Infrastructure"),
    "emergency":     (0.80, 0.20, "Emergency Services"),
    "accommodation": (0.45, 0.55, "Accommodation"),
    "activity":      (0.40, 0.60, "Activities & Recreation"),
    "community":     (0.50, 0.50, "Community Spaces"),
    "default":       (0.45, 0.55, "General"),
}

def _detect_domain(record: Dict) -> str:
    """Detect domain from available data fields."""
    tags    = _tags(record)
    cat     = _category(record).lower()
    name    = record.get("name", "").lower()

    amenity  = tags.get("amenity", "").lower()
    tourism  = tags.get("tourism", "").lower()
    leisure  = tags.get("leisure", "").lower()
    natural  = tags.get("natural", "").lower()
    shop     = tags.get("shop", "").lower()
    historic = tags.get("historic", "").lower()
    religion = tags.get("religion", "").lower()

    if amenity in ("restaurant","cafe","fast_food","food_court","bar") or "food" in cat:
        return "food"
    if natural in ("beach","water","coastline") or "beach" in name or "nature" in cat:
        return "nature"
    if amenity == "place_of_worship" or religion or "temple" in cat or "church" in cat or "mosque" in cat:
        return "spiritual"
    if historic or "heritage" in cat or "museum" in cat or "culture" in cat:
        return "culture"
    if amenity in ("market","marketplace") or shop or "market" in name:
        return "market"
    if amenity in ("bus_station","ferry_terminal","taxi") or "transport" in cat:
        return "transport"
    if amenity in ("hospital","clinic","police","fire_station") or "emergency" in cat:
        return "emergency"
    if tourism in ("hotel","hostel","guest_house") or "hotel" in name:
        return "accommodation"
    if leisure or "park" in cat or "garden" in name or "activity" in cat:
        return "activity"
    if amenity in ("community_centre","library","school","college"):
        return "community"
    return "default"


# ════════════════════════════════════════════════════════════════
# PILLAR 1 — EXISTENCE VALIDITY (max 20 points)
# "Does this place actually exist and can we verify it?"
#
# This is where the travel guide says: "I've been there.
# I can confirm it's real." Without this, nothing else matters.
# ════════════════════════════════════════════════════════════════

def _pillar_existence(record: Dict) -> Tuple[float, List[str]]:
    tags   = _tags(record)
    score  = 20.0
    trace  = []

    # CRITICAL: demolished/removed = 0 immediately
    if tags.get("demolished") == "yes" or tags.get("removed") == "yes":
        return 0.0, ["DEMOLISHED — place no longer exists"]

    if tags.get("disused") == "yes":
        score -= 12
        trace.append("-12 disused tag — place may have closed")

    if tags.get("abandoned") == "yes":
        score -= 10
        trace.append("-10 abandoned tag")

    if tags.get("fixme"):
        score -= 5
        trace.append(f"-5 fixme flag: {str(tags['fixme'])[:60]}")

    # Verified by at least 2 independent sources = strong existence signal
    sources = _mapped_sources(record)
    if len(sources) >= 2:
        score += 0  # baseline — already at 20 for multi-source
        trace.append(f"✓ {len(sources)} independent sources confirm existence")
    elif len(sources) == 1:
        score -= 4
        trace.append("-4 single source only — existence less verified")
    else:
        score -= 10
        trace.append("-10 no verified sources")

    # Has coordinates = physically locatable
    lat, lon = _coords(record)
    if lat and lon:
        trace.append("✓ coordinates present")
    else:
        score -= 8
        trace.append("-8 no coordinates — cannot be located")

    return round(max(0.0, min(20.0, score)), 2), trace


# ════════════════════════════════════════════════════════════════
# PILLAR 2 — IDENTITY INTEGRITY (max 15 points)
# "Does this place know who it is — in its own language?"
#
# A place with no local-language name has had its identity
# partially erased. A Tulu temple listed only as "Sri Temple"
# in English is incomplete. A place with its Kannada name
# intact is more real.
# ════════════════════════════════════════════════════════════════

def _pillar_identity(record: Dict) -> Tuple[float, List[str]]:
    tags  = _tags(record)
    name  = record.get("name", "")
    score = 8.0   # base — has a name at all
    trace = []

    if not name or len(name.strip()) < 2:
        return 0.0, ["No name — identity unknown"]

    trace.append(f"✓ name present: {name}")

    # Local script names
    if tags.get("name:kn"):
        score += 3
        trace.append("+3 Kannada name present")
    if tags.get("name:tulu"):
        score += 3
        trace.append("+3 Tulu name present")
    if tags.get("name:ml"):
        score += 1
        trace.append("+1 Malayalam name present")
    if tags.get("name:kok"):
        score += 1
        trace.append("+1 Konkani name present")

    # Official alt name (local name different from tourist name)
    if tags.get("alt_name") or tags.get("official_name"):
        score += 1
        trace.append("+1 official/alt name documented")

    # Name in local script suggests authentic documentation
    # (non-ASCII characters in name = local language likely)
    if any(ord(c) > 127 for c in name):
        score += 2
        trace.append("+2 local script in primary name")

    return round(min(15.0, score), 2), trace


# ════════════════════════════════════════════════════════════════
# PILLAR 3 — DATA COMPLETENESS (max 15 points)
# "How much do we actually know about this place?"
#
# A place with just a pin and a name is a ghost.
# A place with opening hours, a description, contact info,
# and category tags is a real place your app can speak about.
# ════════════════════════════════════════════════════════════════

def _pillar_completeness(record: Dict) -> Tuple[float, List[str]]:
    tags   = _tags(record)
    score  = 0.0
    trace  = []
    domain = _detect_domain(record)

    # Description / Wikipedia summary
    desc = _description(record)
    if len(desc) > 150:
        score += 4
        trace.append("+4 rich description present")
    elif len(desc) > 30:
        score += 2
        trace.append("+2 basic description present")
    else:
        trace.append("  no description")

    # Opening hours (critical for food/market/activity)
    if tags.get("opening_hours"):
        bonus = 3 if domain in ("food","market","activity","accommodation") else 2
        score += bonus
        trace.append(f"+{bonus} opening hours present")
    elif domain in ("food","market","activity"):
        score -= 2
        trace.append(f"-2 opening hours missing (critical for {domain})")

    # Contact info
    if tags.get("phone") or tags.get("website") or tags.get("email"):
        score += 1
        trace.append("+1 contact information present")

    # Category tags
    cat_fields = sum(1 for k in ("amenity","tourism","leisure","natural","historic","shop")
                     if tags.get(k))
    if cat_fields >= 2:
        score += 2
        trace.append(f"+2 well-tagged ({cat_fields} category fields)")
    elif cat_fields == 1:
        score += 1
        trace.append("+1 minimally tagged")

    # Deep intel domain data
    if record.get("geo_data") and record.get("category_data"):
        score += 3
        trace.append("+3 deep intelligence domains present")

    return round(min(15.0, score), 2), trace


# ════════════════════════════════════════════════════════════════
# PILLAR 4 — SOURCE INTEGRITY (max 15 points)
# "Where does this information come from, and is it trustworthy?"
#
# Not just how many sources — but WHICH sources and whether
# they are neutral, independent, and community-verified.
# ════════════════════════════════════════════════════════════════

SOURCE_TRUST = {
    "community_map":    5,   # OSM — highest trust, community-maintained
    "government":       4,   # ASI, GBIF, Open-Meteo — official but can lag
    "public_media":     3,   # Wikipedia/Wikidata — good but can be tourist-biased
    "field_observation":2,   # Synthetic/modelled — lower trust
    "user_behavior":    1,   # Behavioral signals — weakest
}

def _pillar_source_integrity(record: Dict) -> Tuple[float, List[str]]:
    sources = _mapped_sources(record)
    score   = 0.0
    trace   = []

    if not sources:
        return 0.0, ["No verified sources"]

    # Score each source type by trust level
    for src in sources:
        pts = SOURCE_TRUST.get(src, 0)
        score += pts
        trace.append(f"+{pts} {src}")

    # Diversity bonus — independent source types
    if len(sources) >= 3:
        score += 3
        trace.append("+3 diversity bonus (3+ source types)")
    elif len(sources) == 2:
        score += 1
        trace.append("+1 diversity bonus (2 source types)")

    # Community map + government = strongest possible combination
    if "community_map" in sources and "government" in sources:
        score += 2
        trace.append("+2 community + government cross-verification")

    return round(min(15.0, score), 2), trace


# ════════════════════════════════════════════════════════════════
# PILLAR 5 — TEMPORAL VALIDITY (max 10 points)
# "Is this information from today's world, not 2014?"
# ════════════════════════════════════════════════════════════════

def _pillar_temporal(record: Dict) -> Tuple[float, List[str]]:
    tags   = _tags(record)
    score  = 7.0   # assume reasonably current as baseline
    trace  = []

    # Demolished = immediately 0 (caught in existence too, belt+suspenders)
    if tags.get("demolished") == "yes" or tags.get("removed") == "yes":
        return 0.0, ["DEMOLISHED — no temporal validity"]

    # Check survey date
    survey_date = tags.get("check_date") or tags.get("survey:date") or ""
    if survey_date:
        try:
            year = int(survey_date[:4])
            age  = datetime.now().year - year
            if age == 0:
                score += 3
                trace.append("+3 surveyed this year")
            elif age <= 2:
                score += 2
                trace.append(f"+2 surveyed {age}y ago — recent")
            elif age <= 5:
                trace.append(f"  surveyed {age}y ago — acceptable")
            elif age <= 8:
                score -= 3
                trace.append(f"-3 surveyed {age}y ago — getting stale")
            else:
                score -= 5
                trace.append(f"-5 surveyed {age}y ago — likely outdated")
        except: pass

    # Wikipedia trends: recently viewed = probably still exists
    trends = record.get("wikipedia_trends", {})
    views  = trends.get("wikipedia_views_30d", 0)
    if views > 5000:
        score += 2
        trace.append(f"+2 high Wikipedia activity ({views} views/30d)")
    elif views > 500:
        score += 1
        trace.append(f"+1 active Wikipedia presence ({views} views/30d)")

    # Deep intel has live weather data = collector ran recently
    env = record.get("environment_data", {})
    if env.get("air_quality_index") and env.get("air_quality_index") != "unknown":
        score += 1
        trace.append("+1 live environmental data present")

    return round(min(10.0, max(0.0, score)), 2), trace


# ════════════════════════════════════════════════════════════════
# PILLAR 6 — COMMUNITY ANCHORING (max 25 points)
# "Is this place embedded in real community life — or is it
#  just a building that happens to be in Mangalore?"
#
# This is the most important pillar. It separates a genuine
# human travel companion from a glorified Google Maps export.
# A fish market where 300 fishermen bring their catch at 5am
# scores higher here than a 5-star hotel with 10,000 reviews.
# ════════════════════════════════════════════════════════════════

LOCAL_USE_SIGNALS = [
    "dhaba", "tiffin", "mess", "canteen", "toddy shop",
    "fish market", "kori rotti", "neer dosa", "goli baje",
    "mogaveera", "billava", "bunt", "tulu", "beary",
    "cooperative", "self help", "community hall", "panchayat",
    "mangalorean", "udupi style", "coastal community",
    "fishermen", "farmers market", "local bus", "auto stand",
    "ration shop", "government hospital", "primary school",
]

TOURIST_BUBBLE_SIGNALS = [
    "resort", "luxury hotel", "boutique stay", "rooftop bar",
    "curated experience", "insta", "heritage hotel", "villa",
    "tourist complex", "backpacker hostel for foreigners",
]

def _pillar_community_anchoring(record: Dict) -> Tuple[float, List[str]]:
    tags   = _tags(record)
    name   = record.get("name", "").lower()
    desc   = _description(record).lower()
    text   = name + " " + desc
    domain = _detect_domain(record)
    score  = 10.0  # baseline — assume neutral
    trace  = []

    # LOCAL USE SIGNALS — strongest positive
    local_found = [s for s in LOCAL_USE_SIGNALS if s in text]
    if local_found:
        bonus = min(8, len(local_found) * 2)
        score += bonus
        trace.append(f"+{bonus} local community use signals: {', '.join(local_found[:3])}")

    # Community-managed tag (OSM)
    if tags.get("operator:type") in ("cooperative","ngo","community","government"):
        score += 4
        trace.append("+4 community/government operated")

    # Free or low-cost
    econ  = record.get("economic_data", {})
    price = econ.get("price_level", "")
    if price in ("free", "low"):
        score += 3
        trace.append("+3 free or low-cost — accessible to all")

    # Local ratio from crowd_data
    crowd = record.get("crowd_data", {})
    local_ratio   = crowd.get("local_ratio",   0)
    tourist_ratio = crowd.get("tourist_ratio", 0)
    if local_ratio > 0.75:
        score += 5
        trace.append(f"+5 local ratio {local_ratio:.0%} — genuinely local")
    elif local_ratio > 0.50:
        score += 2
        trace.append(f"+2 local ratio {local_ratio:.0%} — mostly local")
    elif tourist_ratio > 0.70:
        score -= 4
        trace.append(f"-4 tourist ratio {tourist_ratio:.0%} — tourist-dominated")

    # Tourist bubble signals
    bubble_found = [s for s in TOURIST_BUBBLE_SIGNALS if s in text]
    if bubble_found:
        penalty = min(8, len(bubble_found) * 3)
        score  -= penalty
        trace.append(f"-{penalty} tourist-bubble signals: {', '.join(bubble_found[:2])}")

    # Review intelligence signals (from external_intelligence module data)
    review = record.get("review_data", {})
    hype   = review.get("hype_index", 0)
    if hype > 0.75:
        score -= 5
        trace.append(f"-5 high hype index {hype} — media-driven, not community-driven")
    elif hype > 0.50:
        score -= 2
        trace.append(f"-2 elevated hype index {hype}")

    # Cultural relevance from special collector
    cultural = record.get("cultural_data", {})
    crel     = cultural.get("cultural_relevance_score", 0)
    if crel > 0.7:
        score += 4
        trace.append(f"+4 high cultural relevance score {crel}")
    elif crel > 0.4:
        score += 2
        trace.append(f"+2 moderate cultural relevance {crel}")

    # Heritage and community-managed flags
    if cultural.get("community_managed"):
        score += 3
        trace.append("+3 community-managed")
    if cultural.get("heritage_status"):
        score += 2
        trace.append("+2 heritage status recognised")

    return round(min(25.0, max(0.0, score)), 2), trace


# ════════════════════════════════════════════════════════════════
# ─── PLACE TRUTH SCORE (sum of 6 pillars, 0–100) ───────────────
# ════════════════════════════════════════════════════════════════

def compute_place_truth_score(record: Dict) -> Tuple[float, Dict]:
    p1, t1 = _pillar_existence(record)
    p2, t2 = _pillar_identity(record)
    p3, t3 = _pillar_completeness(record)
    p4, t4 = _pillar_source_integrity(record)
    p5, t5 = _pillar_temporal(record)
    p6, t6 = _pillar_community_anchoring(record)

    total = p1 + p2 + p3 + p4 + p5 + p6

    return round(min(100.0, total), 2), {
        "existence":            {"score": p1, "max": 20, "trace": t1},
        "identity":             {"score": p2, "max": 15, "trace": t2},
        "completeness":         {"score": p3, "max": 15, "trace": t3},
        "source_integrity":     {"score": p4, "max": 15, "trace": t4},
        "temporal_validity":    {"score": p5, "max": 10, "trace": t5},
        "community_anchoring":  {"score": p6, "max": 25, "trace": t6},
    }


# ════════════════════════════════════════════════════════════════
# HUMAN FIT SCORE — 5 dimensions (0–100)
# "How good is this place for a real human being right now?"
#
# Separate from truth — a place can be perfectly documented
# (high truth) but terrible for a human to visit right now
# (polluted, overcrowded, dangerous at night, unaffordable).
# ════════════════════════════════════════════════════════════════

def _hf_local_life_evidence(record: Dict) -> Tuple[float, List[str]]:
    """Is there evidence of real local life happening here? (max 25)"""
    score = 10.0
    trace = []
    tags  = _tags(record)
    desc  = _description(record).lower()
    text  = record.get("name","").lower() + " " + desc
    crowd = record.get("crowd_data", {})

    # Footfall patterns suggest daily use
    wday = crowd.get("avg_weekday_footfall", 0)
    wend = crowd.get("avg_weekend_footfall", 0)
    if wday > 200:
        score += 5
        trace.append(f"+5 high weekday footfall {wday} — daily community use")
    elif wday > 50:
        score += 2
        trace.append(f"+2 moderate weekday footfall {wday}")

    # Low-cost / free entry = residents can actually use it
    econ  = record.get("economic_data", {})
    price = econ.get("price_level", "")
    avg   = econ.get("avg_spend_per_person", 0)
    if price == "free" or avg == 0:
        score += 5
        trace.append("+5 free entry — accessible to all residents")
    elif price == "low" or (avg and avg < 100):
        score += 3
        trace.append(f"+3 low cost (avg ₹{avg}) — affordable")
    elif avg and avg > 1500:
        score -= 5
        trace.append(f"-5 high avg spend ₹{avg} — excludes most residents")

    # Local language in name or tags
    if tags.get("name:kn") or tags.get("name:tulu"):
        score += 3
        trace.append("+3 local-language name = community owns this place")

    return round(min(25.0, max(0.0, score)), 2), trace


def _hf_accessibility_equity(record: Dict) -> Tuple[float, List[str]]:
    """Can different kinds of humans actually get here? (max 20)"""
    score = 10.0
    trace = []
    tags  = _tags(record)
    geo   = record.get("geo_data", {})
    exp   = record.get("experience_data", {})

    # Public transport access
    pt = geo.get("public_transport_score", 0)
    if pt > 0.7:
        score += 5
        trace.append(f"+5 excellent public transport access ({pt})")
    elif pt > 0.4:
        score += 2
        trace.append(f"+2 moderate public transport ({pt})")
    elif pt < 0.2:
        score -= 3
        trace.append(f"-3 poor public transport ({pt}) — only accessible by private vehicle")

    # Walkability
    walk = geo.get("walkability_score", 0)
    if walk > 0.7:
        score += 3
        trace.append(f"+3 highly walkable ({walk})")

    # Wheelchair / disability access
    if exp.get("wheelchair_accessible") or tags.get("wheelchair") == "yes":
        score += 3
        trace.append("+3 wheelchair accessible")
    elif tags.get("wheelchair") == "no":
        score -= 2
        trace.append("-2 explicitly not wheelchair accessible")

    # Child friendly
    if exp.get("child_friendly"):
        score += 2
        trace.append("+2 child-friendly")

    return round(min(20.0, max(0.0, score)), 2), trace


def _hf_cultural_integrity(record: Dict) -> Tuple[float, List[str]]:
    """Does this place feel honest and real — not performing for outsiders? (max 20)"""
    score = 10.0
    trace = []

    # Human bias guard scores (from previous audit if available)
    hb = record.get("human_bias", {})
    bp = hb.get("bias_profile", {})

    if bp:
        tourist_gaze  = bp.get("tourist_gaze",  {}).get("score", 0)
        sensationalism= bp.get("sensationalism", {}).get("score", 0)
        colonial      = bp.get("colonial_memory",{}).get("score", 0)

        if tourist_gaze > 0.5:
            score -= 5
            trace.append(f"-5 tourist gaze bias {tourist_gaze:.2f} — place performing for outsiders")
        if sensationalism > 0.3:
            score -= 4
            trace.append(f"-4 sensationalist framing detected")
        if colonial > 0.5:
            score -= 3
            trace.append(f"-3 colonial memory bias {colonial:.2f}")

    # Cultural data
    cultural = record.get("cultural_data", {})
    crel     = cultural.get("cultural_relevance_score", 0)
    if crel > 0.7:
        score += 6
        trace.append(f"+6 strong cultural relevance ({crel})")
    elif crel > 0.4:
        score += 3
        trace.append(f"+3 moderate cultural relevance ({crel})")

    # Local tradition link
    if cultural.get("local_tradition_link"):
        score += 4
        trace.append("+4 documented link to local tradition")

    return round(min(20.0, max(0.0, score)), 2), trace


def _hf_experience_reality(record: Dict) -> Tuple[float, List[str]]:
    """What is the actual human experience of being here? (max 20)"""
    score = 10.0
    trace = []
    exp   = record.get("experience_data", {})
    env   = record.get("environment_data", {})
    crowd = record.get("crowd_data", {})
    safety= record.get("safety_data", {})

    # Cleanliness
    clean = exp.get("cleanliness_score", 0)
    if clean > 0.7:
        score += 3
        trace.append(f"+3 clean environment ({clean})")
    elif clean < 0.3:
        score -= 3
        trace.append(f"-3 poor cleanliness ({clean})")

    # Air quality (from live Open-Meteo data)
    aqi = env.get("air_quality_index", 0)
    if isinstance(aqi, (int, float)):
        if aqi < 50:
            score += 2
            trace.append(f"+2 good air quality AQI {aqi}")
        elif aqi > 150:
            score -= 3
            trace.append(f"-3 poor air quality AQI {aqi} — health risk")

    # Noise
    noise = exp.get("noise_level", "")
    if noise == "quiet":
        score += 2
        trace.append("+2 quiet environment")
    elif noise == "very_loud":
        score -= 2
        trace.append("-2 very loud")

    # Overcrowding
    crush = safety.get("crowd_crush_risk", "")
    if crush == "High":
        score -= 4
        trace.append("-4 high crowd crush risk — dangerous when busy")

    # Visual appeal (matters for experience, not for ranking)
    appeal = exp.get("visual_appeal_score", 0)
    if appeal > 0.7:
        score += 2
        trace.append(f"+2 high visual appeal ({appeal})")

    # Night safety
    night = safety.get("night_safety_score", 0)
    if night > 0.7:
        score += 2
        trace.append(f"+2 good night safety ({night})")
    elif night < 0.3:
        score -= 3
        trace.append(f"-3 poor night safety ({night})")

    return round(min(20.0, max(0.0, score)), 2), trace


def _hf_time_suitability(record: Dict) -> Tuple[float, List[str]]:
    """Is now a good time to visit? (max 15)"""
    score  = 8.0
    trace  = []
    domain = _detect_domain(record)
    tags   = _tags(record)
    temp   = record.get("temporal_data", {})
    env    = record.get("environment_data", {})
    crowd  = record.get("crowd_data", {})

    # Seasonal peak — are we in peak season?
    peaks = temp.get("seasonal_peak_months", [])
    now_month = datetime.now().month
    if peaks and now_month in peaks:
        score += 4
        trace.append(f"+4 currently in peak season (month {now_month})")
    elif peaks:
        trace.append(f"  not peak season (peaks: months {peaks})")

    # Flood risk — Mangalore monsoon awareness
    flood = env.get("flood_risk", "")
    if flood == "High" and now_month in (6,7,8,9):
        score -= 5
        trace.append("-5 high flood risk during current monsoon season")
    elif flood == "High":
        trace.append("  flood risk noted (not monsoon season currently)")

    # Currently open?
    hours = tags.get("opening_hours", "")
    if hours:
        score += 2
        trace.append("+2 opening hours documented")
    elif domain in ("food","market","activity","accommodation"):
        score -= 2
        trace.append(f"-2 no opening hours for {domain} place — visit timing uncertain")

    # Rain impact from temporal_data
    rain = temp.get("rain_impact_index", 0)
    if isinstance(rain, (int,float)) and rain > 0.7:
        score -= 2
        trace.append(f"-2 high rain impact index {rain}")

    return round(min(15.0, max(0.0, score)), 2), trace


def compute_human_fit_score(record: Dict) -> Tuple[float, Dict]:
    h1, t1 = _hf_local_life_evidence(record)
    h2, t2 = _hf_accessibility_equity(record)
    h3, t3 = _hf_cultural_integrity(record)
    h4, t4 = _hf_experience_reality(record)
    h5, t5 = _hf_time_suitability(record)

    total = h1 + h2 + h3 + h4 + h5

    return round(min(100.0, total), 2), {
        "local_life_evidence":  {"score": h1, "max": 25, "trace": t1},
        "accessibility_equity": {"score": h2, "max": 20, "trace": t2},
        "cultural_integrity":   {"score": h3, "max": 20, "trace": t3},
        "experience_reality":   {"score": h4, "max": 20, "trace": t4},
        "time_suitability":     {"score": h5, "max": 15, "trace": t5},
    }


# ════════════════════════════════════════════════════════════════
# COMPANION SCORE — combines both, domain-weighted
# ════════════════════════════════════════════════════════════════

def compute_companion_score(record: Dict) -> Dict:
    """Compute the full Human Travel Guide Score for one place."""

    domain        = _detect_domain(record)
    pt_w, hf_w, dname = DOMAIN_PROFILES.get(domain, DOMAIN_PROFILES["default"])

    truth_score, truth_pillars = compute_place_truth_score(record)
    fit_score,   fit_dims      = compute_human_fit_score(record)

    companion = round((truth_score * pt_w) + (fit_score * hf_w), 2)

    # GRADE — S tier added for truly exceptional places
    if   companion >= 88: grade = "S"
    elif companion >= 75: grade = "A"
    elif companion >= 62: grade = "B"
    elif companion >= 48: grade = "C"
    elif companion >= 32: grade = "D"
    else:                 grade = "F"

    # CONFIDENCE — how much data do we have to trust this score?
    sources      = _mapped_sources(record)
    has_deep     = bool(record.get("geo_data"))
    has_desc     = len(_description(record)) > 50
    has_coords   = all(_coords(record))

    if len(sources) >= 2 and has_deep and has_desc and has_coords:
        confidence = "HIGH"
    elif len(sources) >= 1 and has_coords:
        confidence = "MEDIUM"
    elif has_coords:
        confidence = "LOW"
    else:
        confidence = "UNCERTAIN"

    # RECOMMENDATION — what should the app do?
    if truth_pillars["existence"]["score"] == 0:
        recommendation = "suppress"          # doesn't exist
    elif companion >= 70:
        recommendation = "present_normally"
    elif companion >= 50:
        recommendation = "present_with_context"
    elif companion >= 32:
        recommendation = "present_with_caution"
    else:
        recommendation = "do_not_surface"

    # COMPANION VOICE — what a human guide would actually say
    voice = _generate_companion_voice(
        record, companion, grade, domain, truth_pillars, fit_dims
    )

    # REPAIR FLAGS — what data is missing
    repairs = _repair_flags(record, truth_pillars, fit_dims)

    result = {
        "companion_score":     companion,
        "place_truth_score":   truth_score,
        "human_fit_score":     fit_score,
        "grade":               grade,
        "confidence":          confidence,
        "domain":              dname,
        "recommendation":      recommendation,
        "companion_voice":     voice,
        "repair_flags":        repairs,
        "truth_pillars":       truth_pillars,
        "fit_dimensions":      fit_dims,
        "domain_weights":      {"place_truth": pt_w, "human_fit": hf_w},
        "scored_at":           datetime.now(timezone.utc).isoformat(),
    }

    record["companion_score"] = result
    return result


# ════════════════════════════════════════════════════════════════
# COMPANION VOICE — the sentence your app speaks
# ════════════════════════════════════════════════════════════════

def _generate_companion_voice(record: Dict, score: float, grade: str,
                               domain: str, pillars: Dict, dims: Dict) -> str:
    name = record.get("name", "This place")
    cat  = _category(record)
    crowd= record.get("crowd_data", {})
    cultural = record.get("cultural_data", {})
    econ = record.get("economic_data", {})

    if pillars["existence"]["score"] == 0:
        return f"{name} no longer exists — it has been demolished or removed."

    if score >= 88:
        local_ratio = crowd.get("local_ratio", 0)
        if local_ratio > 0.7:
            return f"{name} is one of those places where you'll be surrounded by Mangaloreans, not other tourists — that alone tells you everything."
        crel = cultural.get("cultural_relevance_score", 0)
        if crel > 0.7:
            return f"{name} is deeply woven into Mangalore's living culture — the kind of place a local would be quietly proud you found."
        return f"{name} is as real as it gets — well-documented, community-rooted, and genuinely worth your time."

    if score >= 75:
        price = econ.get("price_level", "")
        if price in ("free","low"):
            return f"{name} is a solid local spot — accessible, real, and the kind of place Mangaloreans actually use."
        return f"{name} is well-documented and community-anchored. Worth visiting with a little context."

    if score >= 62:
        return f"{name} is worth visiting but has some data gaps — check opening hours before you go."

    if score >= 48:
        hb  = record.get("human_bias", {})
        tg  = hb.get("bias_profile", {}).get("tourist_gaze", {}).get("score", 0)
        if tg > 0.5:
            return f"{name} is known primarily to tourists. Ask a local first — there may be better alternatives nearby."
        return f"{name} has limited documentation. It exists, but your experience may vary."

    return f"{name} has significant data gaps. Surface only if the user specifically asks."


# ════════════════════════════════════════════════════════════════
# REPAIR FLAGS — actionable missing data
# ════════════════════════════════════════════════════════════════

def _repair_flags(record: Dict, pillars: Dict, dims: Dict) -> List[str]:
    flags  = []
    tags   = _tags(record)
    domain = _detect_domain(record)

    if pillars["identity"]["score"] < 5:
        flags.append("Add local-script names: name:kn (Kannada), name:tulu (Tulu)")
    if pillars["completeness"]["score"] < 5:
        flags.append("Add description — even 1 sentence improves score significantly")
    if not tags.get("opening_hours") and domain in ("food","market","activity"):
        flags.append(f"Add opening hours — critical for {domain} places")
    if pillars["temporal_validity"]["score"] < 5:
        flags.append("Update survey date — data may be outdated")
    if dims["accessibility_equity"]["score"] < 8:
        flags.append("Add public transport info and wheelchair accessibility tag")
    if pillars["source_integrity"]["score"] < 6:
        flags.append("Cross-reference with Wikidata or ASI to add government source")

    return flags


# ════════════════════════════════════════════════════════════════
# DATASET RUNNER
# ════════════════════════════════════════════════════════════════

def audit_dataset(records: List[Dict], label: str, save_path: str = None) -> Dict:
    print(f"\n  Human Travel Guide Score — {label}")
    print(f"  Records: {len(records)}")
    print(f"  Scoring all records across 11 dimensions...")
    print(f"  {'─'*58}")

    grades       = {"S":0,"A":0,"B":0,"C":0,"D":0,"F":0}
    recs         = {"present_normally":0,"present_with_context":0,
                    "present_with_caution":0,"do_not_surface":0,"suppress":0}
    confs        = {"HIGH":0,"MEDIUM":0,"LOW":0,"UNCERTAIN":0}
    truth_total  = 0.0
    fit_total    = 0.0
    comp_total   = 0.0

    # Pillar totals for dataset-level insight
    pillar_totals = {p: 0.0 for p in
                     ("existence","identity","completeness","source_integrity",
                      "temporal_validity","community_anchoring")}
    dim_totals    = {d: 0.0 for d in
                     ("local_life_evidence","accessibility_equity",
                      "cultural_integrity","experience_reality","time_suitability")}

    for r in records:
        cs = compute_companion_score(r)
        grades[cs["grade"]]              = grades.get(cs["grade"],0) + 1
        recs[cs["recommendation"]]       = recs.get(cs["recommendation"],0) + 1
        confs[cs["confidence"]]          = confs.get(cs["confidence"],0) + 1
        truth_total  += cs["place_truth_score"]
        fit_total    += cs["human_fit_score"]
        comp_total   += cs["companion_score"]
        for p in pillar_totals:
            pillar_totals[p] += cs["truth_pillars"].get(p,{}).get("score",0)
        for d in dim_totals:
            dim_totals[d]    += cs["fit_dimensions"].get(d,{}).get("score",0)

    n = len(records) or 1

    avg_truth = round(truth_total / n, 1)
    avg_fit   = round(fit_total   / n, 1)
    avg_comp  = round(comp_total  / n, 1)

    print(f"\n  AVERAGE SCORES:")
    print(f"    Place Truth Score:   {avg_truth}/100")
    print(f"    Human Fit Score:     {avg_fit}/100")
    print(f"    Companion Score:     {avg_comp}/100  ← the number that matters")

    print(f"\n  GRADE DISTRIBUTION:")
    maxg = max(grades.values()) or 1
    for g, cnt in grades.items():
        bar = "█" * int(cnt / maxg * 30)
        print(f"    {g}  {bar} {cnt}  ({round(cnt/n*100,1)}%)")

    print(f"\n  RECOMMENDATIONS:")
    for rec, cnt in recs.items():
        print(f"    {rec:<30} {cnt:>5}  ({round(cnt/n*100,1)}%)")

    print(f"\n  CONFIDENCE:")
    for c, cnt in confs.items():
        print(f"    {c:<12} {cnt:>5}  ({round(cnt/n*100,1)}%)")

    print(f"\n  PLACE TRUTH PILLARS (avg score / max):")
    maxima = {"existence":20,"identity":15,"completeness":15,
              "source_integrity":15,"temporal_validity":10,"community_anchoring":25}
    for p, total in pillar_totals.items():
        avg = round(total/n, 1)
        mx  = maxima[p]
        pct = round(avg/mx*100)
        bar = "█" * int(pct/5)
        alert = " ⚠ WEAK" if pct < 40 else ""
        print(f"    {p:<25} {avg:>5}/{mx}  {bar}{alert}")

    print(f"\n  HUMAN FIT DIMENSIONS (avg score / max):")
    hmaxima = {"local_life_evidence":25,"accessibility_equity":20,
               "cultural_integrity":20,"experience_reality":20,"time_suitability":15}
    for d, total in dim_totals.items():
        avg = round(total/n, 1)
        mx  = hmaxima[d]
        pct = round(avg/mx*100)
        bar = "█" * int(pct/5)
        print(f"    {d:<25} {avg:>5}/{mx}  {bar}")

    report = {
        "label":           label,
        "total_records":   len(records),
        "avg_companion":   avg_comp,
        "avg_truth":       avg_truth,
        "avg_fit":         avg_fit,
        "grade_dist":      grades,
        "recommendations": recs,
        "confidence":      confs,
        "pillar_averages": {p: round(v/n,2) for p,v in pillar_totals.items()},
        "dim_averages":    {d: round(v/n,2) for d,v in dim_totals.items()},
    }

    if save_path:
        # Build final data object
        data = {"scored_records": records, "report": report,
                "scored_at": datetime.now(timezone.utc).isoformat()}
        json.dump(data, open(save_path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        size = os.path.getsize(save_path) / (1024*1024)
        print(f"\n  ✓ Saved scored dataset → {save_path}  ({size:.1f} MB)")

    return report


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

SOURCE_MAP = {
    "osm":"community_map","OSM":"community_map",
    "wikidata":"public_media","wikipedia":"public_media","wikipedia_geo":"public_media",
    "open_meteo":"government","GBIF":"government","asi":"government","ASI":"government",
    "commons":"public_media",
    "curated_model":"field_observation","synthetic_time_model":"field_observation",
}

def _tags(r: Dict) -> Dict:
    if r.get("category_data"): return r["category_data"]
    data = r.get("data",{})
    if data.get("osm",{}).get("tags"): return data["osm"]["tags"]
    return {}

def _category(r: Dict) -> str:
    cd = r.get("category_data",{})
    if cd: return cd.get("primary_category","")
    tags = _tags(r)
    if tags.get("amenity")=="restaurant": return "Restaurant"
    if tags.get("amenity")=="place_of_worship": return "Temple"
    if tags.get("natural")=="beach": return "Beach"
    if tags.get("historic"): return "Heritage Site"
    return ""

def _description(r: Dict) -> str:
    rv = r.get("review_data",{})
    if rv.get("wiki_description"): return rv["wiki_description"]
    data = r.get("data",{})
    wd = data.get("wikidata",{})
    if wd.get("description"): return wd["description"]
    tags = _tags(r)
    return tags.get("description") or tags.get("note") or ""

def _coords(r: Dict) -> Tuple:
    geo = r.get("geo_data",{})
    if geo.get("latitude") and geo.get("longitude"):
        return geo["latitude"], geo["longitude"]
    data = r.get("data",{})
    osm  = data.get("osm",{})
    if osm.get("lat") and osm.get("lon"):
        return osm["lat"], osm["lon"]
    return None, None

def _mapped_sources(r: Dict) -> List[str]:
    raw = r.get("sources",[])
    mapped = set()
    for s in raw:
        if not s: continue
        if s in SOURCE_MAP: mapped.add(SOURCE_MAP[s])
        elif "osm" in s.lower(): mapped.add("community_map")
        elif "wiki" in s.lower(): mapped.add("public_media")
        elif any(x in s.lower() for x in ("gov","gbif","asi","meteo")): mapped.add("government")
    return list(mapped)


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def run_all(save: bool = True):
    os.makedirs("data_core",    exist_ok=True)
    os.makedirs("data_storage", exist_ok=True)

    all_reports = []

    print(f"\n{'═'*60}")
    print(f"  HUMAN TRAVEL GUIDE SCORE")
    print(f"  11 dimensions. 2 master scores. 1 companion verdict.")
    print(f"{'═'*60}")

    for path, key in [
        ("data_core/mangalore_rare_enriched.json",  "places"),
        ("data_storage/mangalore_deep_intel.json",  "records"),
    ]:
        if not os.path.exists(path):
            print(f"\n  ⚠ Not found: {path}")
            continue

        data    = json.load(open(path, encoding="utf-8"))
        records = data.get(key, [])
        if isinstance(records, dict): records = list(records.values())

        save_path = path.replace(".json","_scored.json") if save else None
        report    = audit_dataset(records, key, save_path)
        all_reports.append(report)

    # Summary
    rpath = "data_core/companion_score_report.json"
    json.dump({"reports": all_reports,
               "generated_at": datetime.now(timezone.utc).isoformat()},
              open(rpath,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n{'═'*60}")
    print(f"  SCORING COMPLETE")
    for rpt in all_reports:
        print(f"  {rpt['label']:<30} avg={rpt['avg_companion']}/100")
    print(f"  Full report → {rpath}")
    print(f"{'═'*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",      action="store_true")
    parser.add_argument("--input",    help="Single JSON file path")
    parser.add_argument("--place",    help="Score a single place by name (from deep_intel)")
    parser.add_argument("--no-save",  action="store_true")
    args = parser.parse_args()

    if args.place:
        path = "data_storage/mangalore_deep_intel.json"
        if not os.path.exists(path): print(f"Not found: {path}"); return
        data    = json.load(open(path, encoding="utf-8"))
        records = data.get("records", [])
        match   = next((r for r in records
                        if args.place.lower() in r.get("name","").lower()), None)
        if not match:
            print(f"Place not found: {args.place}")
            return
        cs = compute_companion_score(match)
        print(f"\n  {match['name']}")
        print(f"  Companion Score:   {cs['companion_score']}/100  [{cs['grade']}]")
        print(f"  Place Truth:       {cs['place_truth_score']}/100")
        print(f"  Human Fit:         {cs['human_fit_score']}/100")
        print(f"  Confidence:        {cs['confidence']}")
        print(f"  Recommendation:    {cs['recommendation']}")
        print(f"\n  \"{cs['companion_voice']}\"")
        if cs["repair_flags"]:
            print(f"\n  Repair flags:")
            for f in cs["repair_flags"]:
                print(f"    → {f}")
        print()
        return

    if args.input:
        data    = json.load(open(args.input, encoding="utf-8"))
        records = data.get("records") or list(
            data.get("places",{}).values() if isinstance(data.get("places"),dict)
            else data.get("places",[])
        )
        audit_dataset(records, os.path.basename(args.input))
        return

    run_all(save=not args.no_save)


if __name__ == "__main__":
    main()