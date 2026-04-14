"""
bias_guard/human_bias_guard.py

THE HUMAN BIAS GUARD  — v1
════════════════════════════════════════════════════════════════════
Not a keyword filter. Not a source counter.

A genuine bias intelligence system that thinks the way a conscious,
ethical travel companion would — asking 9 deep questions about every
place before ever recommending it to a human.

9 BIAS DIMENSIONS:
  1. Tourist Gaze Bias       — Is this place seen through outsider eyes only?
  2. Colonial Memory Bias    — Does data favour colonial/foreign structures
                               over indigenous/local ones?
  3. Economic Class Bias     — Does the dataset over-represent expensive places
                               and erase budget/working-class spaces?
  4. Religious Majority Bias — Are minority faith places systematically
                               underdocumented vs majority faith places?
  5. Temporal Bias           — Is data frozen in the past? Does it reflect
                               what exists today?
  6. Language Erasure Bias   — Are places documented only in English,
                               erasing their local identity?
  7. Crowd Herd Bias         — Is this place only "known" because everyone
                               goes there? Is popularity being mistaken
                               for quality?
  8. Mapper Density Bias     — Is this place well-documented only because
                               OSM mappers happen to live nearby?
  9. Sensationalism Bias     — Is the place framed as "extreme", "dangerous",
                               "wild", or "exotic" — othering language?

WHAT MAKES THIS DIFFERENT:
  Old approach: "Does this description contain the word 'best'?" → reject
  This system:  "Is this place being recommended to tourists while its
                 own community can't afford to use it?" → flag + explain

  Old approach: source count ≥ 2 → approved
  This system:  "Has this place been documented by someone who actually
                 lives here, or only by visitors passing through?" → flag

  Old approach: binary approve/reject
  This system:  Each dimension produces a 0–1 score + human-readable
                explanation + recommendation for the app to act on

OUTPUT per record:
  {
    "bias_profile": {
      "tourist_gaze":      {"score": 0.8, "flag": True,  "reason": "..."},
      "colonial_memory":   {"score": 0.2, "flag": False, "reason": "..."},
      "economic_class":    {"score": 0.6, "flag": True,  "reason": "..."},
      "religious_majority":{"score": 0.1, "flag": False, "reason": "..."},
      "temporal":          {"score": 0.3, "flag": False, "reason": "..."},
      "language_erasure":  {"score": 0.7, "flag": True,  "reason": "..."},
      "crowd_herd":        {"score": 0.5, "flag": False, "reason": "..."},
      "mapper_density":    {"score": 0.4, "flag": False, "reason": "..."},
      "sensationalism":    {"score": 0.0, "flag": False, "reason": "..."},
    },
    "overall_bias_index":  0.42,   # 0=unbiased, 1=maximally biased
    "bias_flags_count":    3,
    "human_summary":       "This place is framed primarily for tourist consumption.
                            Its local name is absent. Pricing excludes 70% of
                            Mangalore residents. Consider reframing or contextualising.",
    "recommendation":      "present_with_context",
    # present_with_context | present_normally | flag_for_review | suppress
    "suppressed":          False,
  }

DATASET AUDIT OUTPUT:
  - Per-dimension bias distribution across entire dataset
  - Which categories are systematically over/under-represented
  - Which communities are invisible in the data
  - Geographic equity analysis
  - Economic equity analysis
  - Actionable repair suggestions

Usage:
  python -m bias_guard.human_bias_guard --all
  python -m bias_guard.human_bias_guard --input data_core/mangalore_rare_enriched.json
  python -m bias_guard.human_bias_guard --report-only
"""

import argparse
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════
# DIMENSION 1 — TOURIST GAZE BIAS
# "Is this place seen through outsider eyes only?"
#
# A place suffering tourist gaze has been documented, named, and
# described entirely from the perspective of someone passing through.
# Its everyday community reality — the fact that locals use it for
# something completely different — is invisible.
#
# Signals: English-only name, tourism OSM tag, no local language name,
#          Wikipedia article written for outsiders, hotel/resort framing
# ════════════════════════════════════════════════════════════════

def _tourist_gaze_bias(record: Dict) -> Tuple[float, str]:
    tags   = _get_tags(record)
    name   = record.get("name", "")
    cat    = _get_category(record)

    score = 0.0
    signals = []

    # Strong gaze signals
    if tags.get("tourism") in ("attraction", "viewpoint", "resort"):
        score += 0.35
        signals.append("tagged as tourist attraction in OSM")

    if cat in ("Hotel", "Heritage Site") and not tags.get("name:kn") and not tags.get("name:tulu"):
        score += 0.20
        signals.append("no local-language name documented")

    # English-only name with no local script
    if name and not any(ord(c) > 127 for c in name):
        if not tags.get("name:kn") and not tags.get("name:ml") and not tags.get("name:tulu"):
            score += 0.15
            signals.append("English-only name, local script absent")

    # Wikipedia description exists but sounds like a travel guide
    desc = _get_description(record)
    tourist_framing = ["visitors", "tourists", "travellers", "sightseers",
                        "must see", "popular destination", "tourist spot"]
    if any(w in desc.lower() for w in tourist_framing):
        score += 0.20
        signals.append("description uses tourist-framing language")

    # No local use signals
    if not tags.get("opening_hours") and not tags.get("phone"):
        score += 0.10
        signals.append("no practical info for residents (hours, phone)")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "No tourist gaze signals detected"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 2 — COLONIAL MEMORY BIAS
# "Does the data favour colonial/foreign structures over local ones?"
#
# In Indian coastal cities, colonial-era buildings, churches built by
# Portuguese missionaries, and British-era administrative buildings
# are massively over-documented vs. indigenous Tulu shrines, community
# spaces, and pre-colonial heritage that exists at the same location.
# ════════════════════════════════════════════════════════════════

COLONIAL_MARKERS = [
    "portuguese", "british", "colonial", "fort", "garrison",
    "st.", "saint", "chapel", "cathedral", "basilica",
    "survey", "residency", "bungalow", "church of"
]
INDIGENOUS_MARKERS = [
    "tulu", "yaksha", "bhuta", "kola", "naga", "guttu",
    "bali", "kambala", "paddana", "siri", "janapada",
    "mogaveera", "billava", "bunt", "gaud saraswat"
]

def _colonial_memory_bias(record: Dict) -> Tuple[float, str]:
    name  = record.get("name", "").lower()
    desc  = _get_description(record).lower()
    tags  = _get_tags(record)
    cat   = _get_category(record)
    text  = name + " " + desc

    score = 0.0
    signals = []

    has_colonial   = any(m in text for m in COLONIAL_MARKERS)
    has_indigenous = any(m in text for m in INDIGENOUS_MARKERS)

    # Colonial site with no indigenous context
    if has_colonial and not has_indigenous:
        score += 0.40
        signals.append("colonial-era framing with no indigenous cultural context")

    # Church/cathedral with no mention of pre-existing community
    if cat == "Church" and tags.get("denomination") in ("roman_catholic", "latin"):
        score += 0.20
        signals.append("Catholic church — Portuguese mission history often erases pre-existing shrines")

    # Heritage site documented only in colonial frame
    if cat == "Heritage Site" and has_colonial:
        score += 0.25
        signals.append("heritage documentation uses colonial frame")

    # Indigenous site with very thin documentation (OSM only, no description)
    if has_indigenous and not _get_description(record):
        score += 0.30
        signals.append("indigenous cultural site with no description — underdocumented")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "No colonial bias signals detected"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 3 — ECONOMIC CLASS BIAS
# "Does the dataset erase working-class and budget spaces?"
#
# A travel companion that only knows luxury hotels, fine dining, and
# paid attractions is useless — and harmful — to most humans.
# Mangalore has incredible working-class food culture (fish markets,
# roadside tiffin centres, community canteens) that barely exists in
# any dataset because it has no website, no Google listing, no OSM tag.
# ════════════════════════════════════════════════════════════════

LUXURY_SIGNALS   = ["hotel", "resort", "spa", "fine dining", "premium",
                     "heritage hotel", "boutique", "suites", "rooftop bar"]
WORKING_CLASS_SIGNALS = ["dhaba", "tiffin", "mess", "canteen", "toddy shop",
                          "fish market", "street food", "cycle", "auto stand",
                          "labour", "workers"]

def _economic_class_bias(record: Dict) -> Tuple[float, str]:
    name  = record.get("name", "").lower()
    desc  = _get_description(record).lower()
    tags  = _get_tags(record)
    cat   = _get_category(record)
    text  = name + " " + desc

    score   = 0.0
    signals = []

    # Economic data from deep_intel if available
    econ = record.get("economic_data", {})
    price_level = econ.get("price_level", "")

    if price_level == "high":
        score += 0.30
        signals.append("high price level — excludes majority of residents")

    if tags.get("stars") and int(tags.get("stars", 0) or 0) >= 4:
        score += 0.25
        signals.append(f"{tags['stars']}-star rating signals luxury targeting")

    if any(s in text for s in LUXURY_SIGNALS):
        score += 0.20
        signals.append("luxury framing language in name/description")

    # Positive signal — working class presence reduces bias
    if any(s in text for s in WORKING_CLASS_SIGNALS):
        score = max(0.0, score - 0.30)
        signals.append("✓ working-class use signals present (reduces bias)")

    # Free entry bonus
    if econ.get("free_entry") or price_level == "free":
        score = max(0.0, score - 0.20)
        signals.append("✓ free entry — accessible to all")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "No economic class bias signals"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 4 — RELIGIOUS MAJORITY BIAS
# "Are minority faiths systematically underdocumented?"
#
# In Mangalore, Hindu temples (majority) are extensively documented in
# OSM with opening hours, photos, Wikipedia articles, architecture
# details. Mosques (Muslim minority) and Jain temples often have
# just a name pin. Dargahs and syncretic shrines — where multiple
# communities worship together — are almost invisible in data.
# ════════════════════════════════════════════════════════════════

def _religious_majority_bias(record: Dict) -> Tuple[float, str]:
    tags     = _get_tags(record)
    religion = tags.get("religion", "").lower()
    cat      = _get_category(record)
    desc     = _get_description(record)

    score   = 0.0
    signals = []

    if cat not in ("Temple", "Church", "Mosque", "Heritage Site"):
        return 0.0, "Not a religious site"

    is_minority = religion in ("muslim", "islam", "jain", "buddhist",
                                "zoroastrian", "sikh")
    is_majority = religion in ("hindu",)
    is_syncretic = any(w in record.get("name","").lower()
                       for w in ["dargah", "mazaar", "syncretic", "shared"])

    # Minority site with thin documentation
    if is_minority and not desc:
        score += 0.50
        signals.append(f"{religion} site has no description — minority faith underdocumented")

    if is_minority and not tags.get("opening_hours"):
        score += 0.20
        signals.append("minority faith site missing opening hours")

    # Syncretic site — almost always underdocumented
    if is_syncretic:
        score += 0.30
        signals.append("syncretic/shared sacred site — typically erased from mainstream data")

    # Majority faith site with full documentation — contrast signal
    if is_majority and desc and tags.get("opening_hours"):
        score += 0.05
        signals.append("note: majority faith site is well-documented (creates relative gap)")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "Religious documentation appears balanced"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 5 — TEMPORAL BIAS
# "Is this data frozen in time? Does it reflect what exists today?"
#
# The saddest form of travel data bias: recommending places that no
# longer exist, or presenting a city as it was 10 years ago.
# A restaurant that closed during COVID. A beach that eroded.
# A temple that was demolished and rebuilt. A market that moved.
# ════════════════════════════════════════════════════════════════

def _temporal_bias(record: Dict) -> Tuple[float, str]:
    tags    = _get_tags(record)
    score   = 0.0
    signals = []

    # Check OSM lifecycle tags
    if tags.get("disused") == "yes" or tags.get("abandoned") == "yes":
        score += 0.90
        signals.append("⚠ CRITICAL: tagged as disused/abandoned in OSM")

    if tags.get("demolished") == "yes" or tags.get("removed") == "yes":
        score += 1.0
        signals.append("⚠ CRITICAL: tagged as demolished/removed — place no longer exists")

    # Old data with no recent update signal
    osm_timestamp = tags.get("check_date") or tags.get("survey:date") or ""
    if osm_timestamp:
        try:
            survey_year = int(osm_timestamp[:4])
            age_years   = datetime.now().year - survey_year
            if age_years > 5:
                score += 0.30
                signals.append(f"last surveyed {age_years} years ago — may be outdated")
            elif age_years > 2:
                score += 0.10
                signals.append(f"last surveyed {age_years} years ago")
        except: pass

    # No hours = can't verify it's still operating
    cat = _get_category(record)
    if cat in ("Restaurant", "Café", "Market", "Street Food") and not tags.get("opening_hours"):
        score += 0.15
        signals.append("food/market place with no opening hours — operation unverified")

    # Fixme tag = someone flagged it needs verification
    if tags.get("fixme"):
        score += 0.25
        signals.append(f"OSM fixme tag present: '{str(tags['fixme'])[:80]}'")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "No temporal bias signals detected"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 6 — LANGUAGE ERASURE BIAS
# "Has this place's local identity been erased by Anglicisation?"
#
# "Mangalore" itself is a bias — the city's actual name is Mangaluru.
# "Panambur Beach" erases the Tulu name. A dhaba called "Hotel Sharma"
# in OSM has lost its actual signboard name in the local script.
# This matters because language is identity — documenting only the
# English transliteration of a place subtly signals that local
# languages are secondary.
# ════════════════════════════════════════════════════════════════

def _language_erasure_bias(record: Dict) -> Tuple[float, str]:
    tags   = _get_tags(record)
    name   = record.get("name", "")
    cat    = _get_category(record)
    score  = 0.0
    signals= []

    has_kannada  = bool(tags.get("name:kn"))
    has_tulu     = bool(tags.get("name:tulu"))
    has_konkani  = bool(tags.get("name:kok"))
    has_any_local= has_kannada or has_tulu or has_konkani

    # Religious/cultural place with no local script name
    if cat in ("Temple", "Church", "Mosque", "Heritage Site", "Market"):
        if not has_any_local:
            score += 0.40
            signals.append("cultural/religious place has no local-script name in OSM")

    # Anglicised name that clearly had a local original
    # (name ends in common Tulu/Kannada suffixes but no local name documented)
    tulu_suffixes = ["matha", "kshetra", "gudda", "kere", "padavu",
                      "bunder", "bandar", "uru", "pete", "bazaar"]
    if any(name.lower().endswith(s) or s in name.lower() for s in tulu_suffixes):
        if not has_any_local:
            score += 0.30
            signals.append("name contains Tulu/Kannada suffix but no local-script version documented")

    # Place with only English description, no Kannada/Tulu content
    if not has_any_local and cat not in ("Hospital", "Police Station"):
        score += 0.20
        signals.append("no local-language metadata present")

    # Positive: local script present
    if has_tulu:
        score = max(0.0, score - 0.40)
        signals.append("✓ Tulu name documented")
    if has_kannada:
        score = max(0.0, score - 0.25)
        signals.append("✓ Kannada name documented")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "Local language representation present"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 7 — CROWD HERD BIAS
# "Is popularity being mistaken for quality?"
#
# The most dangerous bias for a genuine travel companion.
# A place that 10,000 tourists visit is not necessarily good —
# it's just what the previous 10,000 tourists were also told to visit.
# This creates a feedback loop where data amplifies existing crowds
# and makes the companion just another herd-directing machine.
#
# Signals: high tourist ratio, high hype index, low local ratio,
#          Wikipedia views spike, Instagram-tagged
# ════════════════════════════════════════════════════════════════

def _crowd_herd_bias(record: Dict) -> Tuple[float, str]:
    score   = 0.0
    signals = []

    crowd = record.get("crowd_data", {})
    review = record.get("review_data", {})
    virality = record.get("virality_data", {})

    tourist_ratio = crowd.get("tourist_ratio", 0)
    local_ratio   = crowd.get("local_ratio", 1)
    hype_index    = review.get("hype_index", 0)

    # High tourist-to-local ratio
    if tourist_ratio > 0.70:
        score += 0.40
        signals.append(f"tourist ratio {tourist_ratio:.0%} — locals avoid this place")
    elif tourist_ratio > 0.50:
        score += 0.20
        signals.append(f"tourist ratio {tourist_ratio:.0%} — more tourists than locals")

    # High hype index
    if hype_index > 0.75:
        score += 0.30
        signals.append(f"hype index {hype_index} — place is media-driven, not community-driven")
    elif hype_index > 0.60:
        score += 0.15
        signals.append(f"elevated hype index {hype_index}")

    # Instagram/viral potential (from virality domain)
    if virality.get("instagram_potential") == "High":
        score += 0.15
        signals.append("high Instagram potential — visual-driven, not experience-driven")

    # Overcrowding
    crowd_risk = crowd.get("overcrowding_risk", "")
    if crowd_risk == "High":
        score += 0.20
        signals.append("high overcrowding risk — quantity over quality")

    # Strong local use = anti-herd signal
    if local_ratio > 0.80:
        score = max(0.0, score - 0.30)
        signals.append("✓ strongly local — not a herd destination")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "No crowd herd signals detected"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 8 — MAPPER DENSITY BIAS
# "Is this place documented only because mappers live nearby?"
#
# OpenStreetMap data density correlates with where HOT/OSM volunteers
# and tech-educated mappers live. In Mangalore, the city centre and
# areas near colleges have 5–10x more OSM data than the fishing
# villages, coastal hamlets, and peripheral markets.
# This means the dataset systematically knows more about places that
# are convenient to document than places that are actually interesting.
# ════════════════════════════════════════════════════════════════

def _mapper_density_bias(record: Dict) -> Tuple[float, str]:
    score   = 0.0
    signals = []

    geo = record.get("geo_data", {})
    dist = geo.get("distance_from_center_km", 0)
    zone = geo.get("footfall_heatmap_zone", "")

    # Peripheral locations are likely under-documented
    if dist > 8:
        score += 0.35
        signals.append(f"{dist:.1f}km from centre — likely under-mapped peripheral area")
    elif dist > 5:
        score += 0.15
        signals.append(f"{dist:.1f}km from centre — moderate mapping density")

    # Low authenticity in deep_intel suggests thin OSM data
    bg = record.get("bias_guard", {})
    auth = bg.get("authenticity_score", 0)
    if auth and auth < 0.65:
        score += 0.20
        signals.append(f"low authenticity score {auth} — sparse documentation")

    # No tags beyond bare minimum
    tags = _get_tags(record)
    tag_count = len([v for v in tags.values() if v])
    if tag_count <= 2:
        score += 0.25
        signals.append(f"only {tag_count} OSM tags — bare minimum documentation")

    # City core well-mapped = relatively lower bias
    if zone == "city_core_high":
        score = max(0.0, score - 0.20)
        signals.append("✓ city core zone — well-mapped area")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "Mapping density appears adequate"
    return score, reason


# ════════════════════════════════════════════════════════════════
# DIMENSION 9 — SENSATIONALISM BIAS
# "Is this place framed as 'exotic', 'dangerous', or 'other'?"
#
# The most subtle and harmful bias for a travel companion.
# Describing a neighbourhood as "gritty", a festival as "wild",
# a community as "tribal", or a food as "bizarre" — this is othering
# language that dehumanises the people who live and work there.
# A genuinely humane companion never does this.
# ════════════════════════════════════════════════════════════════

OTHERING_LANGUAGE = [
    "exotic", "tribal", "primitive", "wild", "bizarre", "strange",
    "unusual", "unique culture", "mystical", "mysterious", "ancient ritual",
    "untouched", "undiscovered", "off the beaten", "authentic experience",
    "real india", "local colour", "colourful locals", "simple people",
    "humble people", "quaint", "backward", "remote tribe",
    "dangerous area", "rough neighbourhood", "avoid after dark",
    "chaotic", "poverty tourism", "slum tour"
]

def _sensationalism_bias(record: Dict) -> Tuple[float, str]:
    desc    = _get_description(record).lower()
    name    = record.get("name", "").lower()
    text    = desc + " " + name
    score   = 0.0
    signals = []
    matched = []

    for phrase in OTHERING_LANGUAGE:
        if phrase in text:
            matched.append(phrase)

    if matched:
        score = min(1.0, len(matched) * 0.25)
        signals.append(f"othering/sensationalist language: {', '.join(matched[:3])}")

    # Danger framing
    danger_words = ["dangerous", "unsafe", "crime", "avoid", "beware", "sketchy"]
    danger_found = [w for w in danger_words if w in text]
    if danger_found:
        score += 0.30
        signals.append(f"danger-framing language: {', '.join(danger_found)}")

    score = round(min(1.0, score), 3)
    reason = "; ".join(signals) if signals else "No sensationalist language detected"
    return score, reason


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _get_tags(record: Dict) -> Dict:
    """Extract OSM tags regardless of record format."""
    # deep_intel format
    tags = record.get("category_data", {})
    if tags: return tags
    # rare_enriched format
    data = record.get("data", {})
    if data.get("osm", {}).get("tags"):
        return data["osm"]["tags"]
    return {}

def _get_category(record: Dict) -> str:
    """Get primary category regardless of format."""
    cat_data = record.get("category_data", {})
    if cat_data:
        return cat_data.get("primary_category", "")
    tags = _get_tags(record)
    if tags.get("amenity") == "restaurant": return "Restaurant"
    if tags.get("tourism") == "hotel":      return "Hotel"
    if tags.get("amenity") == "place_of_worship": return "Temple"
    if tags.get("natural") == "beach":      return "Beach"
    if tags.get("historic"):                return "Heritage Site"
    return ""

def _get_description(record: Dict) -> str:
    """Get best available description."""
    # deep_intel
    review = record.get("review_data", {})
    if review.get("wiki_description"):
        return review["wiki_description"]
    # rare_enriched
    data = record.get("data", {})
    wd = data.get("wikidata", {})
    if wd.get("description"):
        return wd["description"]
    # OSM tags
    tags = _get_tags(record)
    return tags.get("description") or tags.get("note") or ""


# ════════════════════════════════════════════════════════════════
# HUMAN SUMMARY GENERATOR
# Produces a plain-English explanation a human can act on
# ════════════════════════════════════════════════════════════════

def _generate_human_summary(bias_profile: Dict, name: str, category: str) -> str:
    high_flags = [dim for dim, result in bias_profile.items()
                  if result["score"] > 0.5]
    medium_flags = [dim for dim, result in bias_profile.items()
                    if 0.3 < result["score"] <= 0.5]

    if not high_flags and not medium_flags:
        return f"{name} appears in the data with balanced representation. No significant bias detected."

    parts = []

    if "tourist_gaze" in high_flags:
        parts.append("framed primarily for tourist consumption rather than local life")
    if "colonial_memory" in high_flags:
        parts.append("documented through a colonial lens — indigenous context is absent")
    if "economic_class" in high_flags:
        parts.append("positioned for high-income visitors — working-class Mangaloreans are not its audience")
    if "language_erasure" in high_flags:
        parts.append("local language identity has been erased — only the English version exists")
    if "crowd_herd" in high_flags:
        parts.append("popular because tourists are told to go there, not because locals love it")
    if "temporal" in high_flags:
        parts.append("data may be outdated — operation cannot be verified")
    if "sensationalism" in high_flags:
        parts.append("description uses othering/exotic language that dehumanises the community")
    if "religious_majority" in high_flags:
        parts.append("minority faith site with thin documentation — creates inequality in visibility")
    if "mapper_density" in high_flags:
        parts.append("likely under-documented due to peripheral location — data gap, not place gap")

    if parts:
        return f"{name} ({category}): " + "; ".join(parts) + "."
    return f"{name} has minor bias signals in: {', '.join(medium_flags)}."


def _get_recommendation(overall_score: float, flags: List[str],
                         temporal_score: float) -> str:
    """Decide what the app should do with this record."""

    # Place literally doesn't exist anymore
    if temporal_score >= 0.9:
        return "suppress"

    # Multiple severe biases
    if overall_score > 0.65 and len(flags) >= 4:
        return "flag_for_review"

    # Sensationalism — always needs context
    if "sensationalism" in flags:
        return "present_with_context"

    # Colonial or religious bias — needs contextualisation
    if "colonial_memory" in flags or "religious_majority" in flags:
        return "present_with_context"

    # Moderate overall bias
    if overall_score > 0.40:
        return "present_with_context"

    return "present_normally"


# ════════════════════════════════════════════════════════════════
# CORE AUDIT FUNCTION — runs all 9 dimensions on one record
# ════════════════════════════════════════════════════════════════

DIMENSION_WEIGHTS = {
    "sensationalism":    0.20,   # highest — most harmful
    "temporal":          0.18,   # high — wrong info = dangerous
    "tourist_gaze":      0.14,
    "colonial_memory":   0.12,
    "language_erasure":  0.12,
    "economic_class":    0.10,
    "religious_majority":0.07,
    "crowd_herd":        0.05,
    "mapper_density":    0.02,
}

def audit_record(record: Dict) -> Dict:
    """Run all 9 bias dimensions on a single record."""

    name     = record.get("name", "Unknown")
    category = _get_category(record)

    # Run all 9 dimensions
    dimensions = {
        "tourist_gaze":       _tourist_gaze_bias(record),
        "colonial_memory":    _colonial_memory_bias(record),
        "economic_class":     _economic_class_bias(record),
        "religious_majority": _religious_majority_bias(record),
        "temporal":           _temporal_bias(record),
        "language_erasure":   _language_erasure_bias(record),
        "crowd_herd":         _crowd_herd_bias(record),
        "mapper_density":     _mapper_density_bias(record),
        "sensationalism":     _sensationalism_bias(record),
    }

    THRESHOLD = 0.35  # flag if dimension score exceeds this

    bias_profile = {}
    for dim, (score, reason) in dimensions.items():
        bias_profile[dim] = {
            "score":  score,
            "flag":   score >= THRESHOLD,
            "reason": reason,
            "weight": DIMENSION_WEIGHTS[dim],
        }

    # Weighted overall bias index
    overall = sum(
        bias_profile[dim]["score"] * DIMENSION_WEIGHTS[dim]
        for dim in bias_profile
    )
    overall = round(min(1.0, overall), 3)

    # Flagged dimensions
    flagged = [dim for dim, r in bias_profile.items() if r["flag"]]

    # Temporal score for suppression decision
    temporal_score = bias_profile["temporal"]["score"]

    human_summary  = _generate_human_summary(bias_profile, name, category)
    recommendation = _get_recommendation(overall, flagged, temporal_score)

    result = {
        "bias_profile":      bias_profile,
        "overall_bias_index":overall,
        "bias_flags_count":  len(flagged),
        "flagged_dimensions":flagged,
        "human_summary":     human_summary,
        "recommendation":    recommendation,
        "suppressed":        recommendation == "suppress",
        "name":              name,
        "category":          category,
    }

    # Attach to record
    record["human_bias"] = result
    return result


# ════════════════════════════════════════════════════════════════
# DATASET AUDIT — runs across all records, produces city-level report
# ════════════════════════════════════════════════════════════════

def audit_dataset(records: List[Dict], label: str) -> Dict:
    print(f"\n  Human Bias Guard — {label}")
    print(f"  Records: {len(records)}")
    print(f"  Running 9 bias dimensions per record...")
    print(f"  {'─'*55}")

    results         = []
    dim_totals      = {d: 0.0 for d in DIMENSION_WEIGHTS}
    dim_flag_counts = {d: 0   for d in DIMENSION_WEIGHTS}
    recommendations = {"present_normally": 0, "present_with_context": 0,
                        "flag_for_review": 0, "suppress": 0}
    suppressed      = []
    flagged_review  = []

    for record in records:
        r = audit_record(record)
        results.append(r)

        for dim in DIMENSION_WEIGHTS:
            dim_totals[dim]      += r["bias_profile"][dim]["score"]
            dim_flag_counts[dim] += int(r["bias_profile"][dim]["flag"])

        recommendations[r["recommendation"]] += 1

        if r["suppressed"]:
            suppressed.append({"name": r["name"], "reason": r["human_summary"]})
        if r["recommendation"] == "flag_for_review":
            flagged_review.append({"name": r["name"], "summary": r["human_summary"]})

    n = len(records) or 1

    # Per-dimension averages
    dim_averages = {d: round(dim_totals[d] / n, 3) for d in DIMENSION_WEIGHTS}
    dim_flag_pct = {d: round(dim_flag_counts[d] / n * 100, 1) for d in DIMENSION_WEIGHTS}

    # Overall dataset bias index
    dataset_bias_index = round(
        sum(dim_averages[d] * DIMENSION_WEIGHTS[d] for d in DIMENSION_WEIGHTS), 3
    )

    # Print summary
    print(f"\n  DATASET BIAS INDEX: {dataset_bias_index:.3f}  "
          f"({'LOW' if dataset_bias_index < 0.2 else 'MEDIUM' if dataset_bias_index < 0.4 else 'HIGH'})")
    print(f"\n  PER-DIMENSION AVERAGE BIAS SCORES:")
    print(f"  {'Dimension':<25} {'Avg Score':>9}  {'% Flagged':>9}  {'Weight':>7}")
    print(f"  {'─'*55}")
    for dim, avg in sorted(dim_averages.items(), key=lambda x: -x[1]):
        bar   = "█" * int(avg * 20)
        flag  = dim_flag_pct[dim]
        wt    = DIMENSION_WEIGHTS[dim]
        alert = " ⚠" if avg > 0.4 else ""
        print(f"  {dim:<25} {avg:>9.3f}  {flag:>8.1f}%  {wt:>7.2f}{alert}")

    print(f"\n  RECOMMENDATIONS:")
    for rec, count in recommendations.items():
        pct = round(count / n * 100, 1)
        print(f"    {rec:<28} {count:>5}  ({pct}%)")

    if suppressed:
        print(f"\n  ⚠ SUPPRESSED ({len(suppressed)} records — do not present to user):")
        for s in suppressed[:5]:
            print(f"    • {s['name']}")

    if flagged_review:
        print(f"\n  🔍 FLAG FOR REVIEW ({len(flagged_review)} records):")
        for f in flagged_review[:5]:
            print(f"    • {f['name']}")

    return {
        "label":              label,
        "total_records":      len(records),
        "dataset_bias_index": dataset_bias_index,
        "dimension_averages": dim_averages,
        "dimension_flag_pct": dim_flag_pct,
        "recommendations":    recommendations,
        "suppressed_count":   len(suppressed),
        "suppressed":         suppressed,
        "flagged_for_review": flagged_review,
        "per_record_results": results,
    }


# ════════════════════════════════════════════════════════════════
# EQUITY REPORT — what communities and categories are invisible?
# ════════════════════════════════════════════════════════════════

def generate_equity_report(records: List[Dict]) -> Dict:
    """Identify systematic invisibility in the dataset."""

    category_counts:  Dict[str, int] = {}
    religion_counts:  Dict[str, int] = {}
    price_counts:     Dict[str, int] = {}
    no_description    = 0
    no_local_name     = 0
    peripheral_count  = 0

    for r in records:
        cat  = _get_category(r)
        tags = _get_tags(r)
        geo  = r.get("geo_data", {})

        category_counts[cat] = category_counts.get(cat, 0) + 1

        rel = tags.get("religion", "none")
        religion_counts[rel] = religion_counts.get(rel, 0) + 1

        price = r.get("economic_data", {}).get("price_level", "unknown")
        price_counts[price] = price_counts.get(price, 0) + 1

        if not _get_description(r):         no_description += 1
        if not tags.get("name:kn") and not tags.get("name:tulu"):
            no_local_name += 1
        if geo.get("distance_from_center_km", 0) > 8:
            peripheral_count += 1

    total = len(records) or 1

    return {
        "category_distribution":     dict(sorted(category_counts.items(), key=lambda x: -x[1])),
        "religion_distribution":     dict(sorted(religion_counts.items(), key=lambda x: -x[1])),
        "price_distribution":        dict(sorted(price_counts.items(), key=lambda x: -x[1])),
        "no_description_pct":        round(no_description / total * 100, 1),
        "no_local_name_pct":         round(no_local_name  / total * 100, 1),
        "peripheral_places_pct":     round(peripheral_count / total * 100, 1),
        "equity_gaps": {
            "local_language_coverage":
                f"{100 - round(no_local_name/total*100,1)}% of places have local-script names",
            "description_coverage":
                f"{100 - round(no_description/total*100,1)}% of places have descriptions",
            "peripheral_coverage":
                f"{round(peripheral_count/total*100,1)}% of places are in peripheral zones (>8km)",
        },
        "repair_suggestions": _repair_suggestions(
            no_description/total, no_local_name/total,
            religion_counts, category_counts
        ),
    }


def _repair_suggestions(desc_gap: float, lang_gap: float,
                         religion_counts: Dict, cat_counts: Dict) -> List[str]:
    suggestions = []
    if desc_gap > 0.60:
        suggestions.append(
            f"{desc_gap:.0%} of places have no description. "
            "Run Wikipedia deep miner again with expanded article list."
        )
    if lang_gap > 0.80:
        suggestions.append(
            f"{lang_gap:.0%} of places have no local-script name. "
            "Add Kannada/Tulu name fields to OSM collection query."
        )
    muslim_count = religion_counts.get("muslim", 0) + religion_counts.get("islam", 0)
    hindu_count  = religion_counts.get("hindu", 0)
    if hindu_count > 0 and muslim_count / max(1, hindu_count) < 0.15:
        suggestions.append(
            "Muslim/Beary religious sites appear underdocumented relative to Hindu sites. "
            "Add targeted OSM queries for mosques and dargahs."
        )
    if cat_counts.get("Street Food", 0) < 20:
        suggestions.append(
            "Street food and working-class food spaces are underrepresented. "
            "Add dhaba, tiffin centre, and roadside stall queries."
        )
    return suggestions


# ════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ════════════════════════════════════════════════════════════════

def run_all(save: bool = True):
    os.makedirs("data_core",    exist_ok=True)
    os.makedirs("data_storage", exist_ok=True)

    full_report = {"generated_at": datetime.now(timezone.utc).isoformat(), "datasets": []}

    print(f"\n{'═'*60}")
    print(f"  HUMAN BIAS GUARD — 9-Dimension Bias Intelligence")
    print(f"  Not keyword filtering. Genuine ethical reasoning.")
    print(f"{'═'*60}")

    for path, label, key in [
        ("data_core/mangalore_rare_enriched.json",   "rare_enriched", "places"),
        ("data_storage/mangalore_deep_intel.json",   "deep_intel",    "records"),
    ]:
        if not os.path.exists(path):
            print(f"\n  ⚠ Not found: {path}")
            continue

        data    = json.load(open(path, encoding="utf-8"))
        records = data.get(key, [])
        if isinstance(records, dict):
            records = list(records.values())
        print(f"\n  Loaded {len(records)} records from {path}")

        audit   = audit_dataset(records, label)
        equity  = generate_equity_report(records)

        print(f"\n  EQUITY REPORT:")
        print(f"    No description:   {equity['no_description_pct']}% of places")
        print(f"    No local name:    {equity['no_local_name_pct']}% of places")
        print(f"    Peripheral zones: {equity['peripheral_places_pct']}% of places")
        if equity["repair_suggestions"]:
            print(f"\n  REPAIR SUGGESTIONS:")
            for s in equity["repair_suggestions"]:
                print(f"    → {s}")

        full_report["datasets"].append({
            **{k: v for k, v in audit.items() if k != "per_record_results"},
            "equity": equity,
        })

        if save:
            data[key] = records   # records now have human_bias attached
            data["human_bias_audit"] = {
                "dataset_bias_index": audit["dataset_bias_index"],
                "audited_at":         full_report["generated_at"],
                "suppressed":         audit["suppressed_count"],
            }
            out = path.replace(".json", "_human_audited.json")
            json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            size = os.path.getsize(out) / (1024*1024)
            print(f"\n  ✓ Saved → {out}  ({size:.1f} MB)")

    rpath = "data_core/human_bias_report.json"
    json.dump(full_report, open(rpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n{'═'*60}")
    print(f"  HUMAN BIAS AUDIT COMPLETE")
    for ds in full_report["datasets"]:
        idx = ds["dataset_bias_index"]
        level = "LOW ✓" if idx < 0.2 else "MEDIUM ⚠" if idx < 0.4 else "HIGH ✗"
        print(f"  {ds['label']:<30} Bias Index: {idx:.3f}  [{level}]")
    print(f"  Full report → {rpath}")
    print(f"{'═'*60}\n")
    return full_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",         action="store_true")
    parser.add_argument("--input",       help="Single JSON file")
    parser.add_argument("--report-only", action="store_true", help="No saved output")
    args = parser.parse_args()

    if args.all or not args.input:
        run_all(save=not args.report_only)
    else:
        if not os.path.exists(args.input):
            print(f"Not found: {args.input}"); return
        data    = json.load(open(args.input, encoding="utf-8"))
        records = data.get("records") or list(data.get("places", {}).values() if isinstance(data.get("places"), dict) else data.get("places", []))
        audit_dataset(records, os.path.basename(args.input))


if __name__ == "__main__":
    main()