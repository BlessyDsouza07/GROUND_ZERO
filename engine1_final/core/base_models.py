"""
core/base_models.py  [v3 — Five-Layer Intelligence Model]

Ground Zero Entity Data Model.

LAYER ARCHITECTURE (from Ground Zero report §4.1 + §4.5):
─────────────────────────────────────────────────────────
Layer 1: Structural Data      — name, lat, lon, type, address
Layer 2: Contextual Data      — best_time, crowd_level, family_friendly, energy_required
Layer 3: Behavioral Data      — dwell_time, repeat_visits, peak_hours, drop_off_rate
Layer 4: Authenticity Signals — source_count, agreement_score, gov_verified, bias_score
Layer 5: Emotional/Experience — experience_type, emotion_score, sentiment (from lit survey §2.7)

AUTHENTICITY FORMULA (Ground Zero report §4.5.1):
  authenticity_score = (
      log_source_weight  * log(max(source_count, 1)) +
      agreement_weight   * agreement_score +
      freshness_weight   * freshness_score -
      bias_weight        * promotion_bias_score
  ) normalised to [0, 1]

GRADING:
  A: >= 0.75  Cross-verified, rich metadata, stable external links
  B: >= 0.55  Solid source, good metadata, minor gaps
  C: >= 0.38  Basic OSM with some practical info
  D:  < 0.38  Sparse — needs more source coverage
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from enum import Enum
import uuid
import math


# ============================================================
# DOMAIN ENUM
# ============================================================

class Domain(str, Enum):
    PLACES       = "places"
    FOOD         = "food"
    CULTURE      = "culture"
    ACTIVITIES   = "activities"
    TRAVEL_INTEL = "travel_intel"
    SAFETY_SUPPORT = "safety_support"
    EMERGENCY    = "emergency"
    STAY         = "stay"
    TRANSPORT    = "transport"
    EXPLORE      = "explore"
    LOCAL        = "local"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# ============================================================
# LAYER 2: CONTEXTUAL DATA
# ============================================================

@dataclass
class ContextualLayer:
    """
    Layer 2 — Context a tourist needs BEFORE visiting.
    Computed from OSM tags, domain knowledge, time/category rules.
    """
    best_time_to_visit: str = ""           # "morning" | "afternoon" | "evening" | "night" | "any"
    crowd_level: str = "medium"            # "low" | "medium" | "high"
    avg_duration_minutes: int = 30         # estimated visit duration
    family_friendly: bool = True
    solo_safe: bool = True
    rain_suitable: bool = False            # indoor / covered venue?
    energy_required: str = "low"          # "low" | "moderate" | "high"
    walking_distance_m: int = 0           # walk from nearest transit (estimated)
    best_weather_condition: str = "clear" # "clear" | "any" | "overcast"
    weather_sensitive: bool = False       # closes/degrades in rain/storm?
    age_suitable_min: int = 0             # minimum age (0 = all ages)
    age_suitable_max: int = 99            # maximum age (99 = all ages)
    silence_trigger: bool = False         # should system speak when tourist is nearby?

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# LAYER 3: BEHAVIORAL DATA
# ============================================================

@dataclass
class BehavioralLayer:
    """
    Layer 3 — Predicted behavioral signals.
    Ground Zero report §4.5.1: 'adaptive learning from real tourist interactions'
    Initially computed from domain + category rules; updated post-trip.
    """
    tourist_dwell_time_min: int = 20       # avg minutes tourists actually stay
    expected_dwell_time_min: int = 30      # expected duration
    repeat_visit_probability: float = 0.3 # 0.0–1.0
    drop_off_rate: float = 0.2            # 0.0–1.0, fraction who leave early
    peak_hours: List[int] = field(default_factory=list)  # e.g. [9,10,17,18]
    confusion_zone: bool = False           # do tourists get lost/confused here?
    decision_point: bool = False           # a place requiring navigation choice?
    high_miss_probability: bool = False    # easy to walk past without noticing?
    fatigue_index: float = 0.3            # 0.0–1.0, how tiring is a full visit?

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# LAYER 4: AUTHENTICITY SIGNALS
# ============================================================

@dataclass
class AuthenticityLayer:
    """
    Layer 4 — Deterministic authenticity intelligence.
    Formula from Ground Zero report §4.5.1 + data quality principles.

    authenticity_score = (
        log_source_weight  * log(max(source_count, 1))  +
        agreement_weight   * source_agreement_score      +
        freshness_weight   * freshness_score             -
        bias_weight        * promotion_bias_score
    ) → normalised [0, 1]
    """
    source_count: int = 1
    source_agreement_score: float = 0.0   # 0.0–1.0, cross-source consensus
    gov_verified: bool = False             # appears in government dataset
    wiki_verified: bool = False            # has Wikipedia article
    promotion_bias_score: float = 0.0     # 0.0–1.0, higher = more promotional
    freshness_score: float = 0.5          # 0.0–1.0, how recently verified
    last_verified: str = ""               # ISO date string
    cross_ref_count: int = 0              # how many external references found
    anomaly_flag: bool = False            # suspicious signals detected
    local_validation: bool = False        # confirmed by a local source

    def compute_formula_score(self) -> float:
        """
        Deterministic authenticity formula.
        Weights aligned with Ground Zero report §4.5.1 Personal Fit Score logic.

        LOG term: rewards more sources but with diminishing returns
        AGREEMENT: rewards cross-source agreement
        FRESHNESS: rewards recently verified data
        BIAS PENALTY: penalises promotional language

        Constants calibrated for OSM-first data (max ~5 meaningful sources):
          log(1) = 0.0, log(2) = 0.69, log(3) = 1.10, log(5) = 1.61
          → normalised to [0, 1] by dividing by log(6) = 1.79
        """
        LOG_W   = 0.25   # source count weight
        AGREE_W = 0.35   # agreement weight
        FRESH_W = 0.20   # freshness weight
        BIAS_W  = 0.20   # bias penalty weight

        log_term       = math.log(max(self.source_count, 1)) / math.log(6)
        agreement_term = self.source_agreement_score
        freshness_term = self.freshness_score
        bias_penalty   = self.promotion_bias_score

        raw = (
            LOG_W   * log_term +
            AGREE_W * agreement_term +
            FRESH_W * freshness_term -
            BIAS_W  * bias_penalty
        )
        # Bonus: government or wiki verified = more authentic
        if self.gov_verified:   raw += 0.05
        if self.wiki_verified:  raw += 0.05
        if self.local_validation: raw += 0.03

        return round(min(max(raw, 0.0), 1.0), 3)

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# LAYER 5: EMOTIONAL / EXPERIENCE LAYER
# ============================================================

@dataclass
class ExperienceLayer:
    """
    Layer 5 — Emotional and experiential signals.
    Inspired by Ground Zero literature survey §2.7 (Talavera et al.):
    'Sentiment Recognition in Egocentric Photostreams'

    Experience types derived deterministically from place category/domain/tags.
    Emotion scores are seeded from category rules and updated from behavior.
    """
    experience_type: List[str] = field(default_factory=list)
    # e.g. ["peaceful", "spiritual", "crowded", "adventurous",
    #        "cultural", "gastronomic", "historical", "natural"]

    emotion_score: Dict[str, float] = field(default_factory=lambda: {
        "positive": 0.6,
        "neutral":  0.3,
        "negative": 0.1
    })

    sensory_profile: Dict[str, str] = field(default_factory=dict)
    # e.g. {"sound": "waves/bells/silence", "smell": "salt/incense/food",
    #        "visual": "panoramic/intimate/colourful"}

    tourist_reality_gap: float = 0.0
    # 0.0 = place exactly matches expectations
    # > 0.5 = significant over/under-delivery vs expectation

    local_secrets_index: float = 0.0
    # 0.0 = well-known tourist spot
    # 1.0 = known only to locals (Ground Zero 'Local Secret' slot)

    silence_suitability: float = 0.5
    # 0.0 = noisy/hectic, not suitable for silence engine nudge
    # 1.0 = peaceful/spiritual, perfect for a single quiet nudge

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


# ============================================================
# LEGACY DERIVED SIGNALS (kept for backward compat)
# ============================================================

@dataclass
class DerivedSignals:
    review_score: float = 0.0
    fake_ratio: float = 0.0
    price_index: float = 0.0
    safety_index: float = 0.0
    stability_index: float = 0.0
    crowd_index: float = 0.0
    time_suitability_index: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# BASE ENTITY — Five-Layer Model
# ============================================================

@dataclass
class BaseEntity:
    # ── Layer 1: Structural Identity ──────────────────────
    name: str
    domain: Domain
    category: str
    subcategory: str
    latitude: float
    longitude: float
    sources: List[str]

    # Auto fields
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Scoring ────────────────────────────────────────────
    structural_score: float = 0.0
    review_score: float = 0.0
    domain_score: float = 0.0
    final_authenticity_score: float = 0.0
    grade: Grade = Grade.D

    # ── Layer 2: Contextual ────────────────────────────────
    contextual: ContextualLayer = field(default_factory=ContextualLayer)

    # ── Layer 3: Behavioral ────────────────────────────────
    behavioral: BehavioralLayer = field(default_factory=BehavioralLayer)

    # ── Layer 4: Authenticity ──────────────────────────────
    authenticity: AuthenticityLayer = field(default_factory=AuthenticityLayer)

    # ── Layer 5: Experience ────────────────────────────────
    experience: ExperienceLayer = field(default_factory=ExperienceLayer)

    # ── Legacy signals (kept for scoring pipeline) ─────────
    derived_signals: DerivedSignals = field(default_factory=DerivedSignals)

    # ── Explainability ─────────────────────────────────────
    decision_trace: List[str] = field(default_factory=list)

    # ────────────────────────────────────────────────────────
    # VALIDATION
    # ────────────────────────────────────────────────────────

    def validate(self) -> bool:
        if not self.name:
            raise ValueError("Entity must have a name.")
        if not isinstance(self.domain, Domain):
            raise ValueError("Invalid domain.")
        if not (-90 <= self.latitude <= 90):
            raise ValueError("Invalid latitude.")
        if not (-180 <= self.longitude <= 180):
            raise ValueError("Invalid longitude.")
        if not self.sources:
            raise ValueError("Entity must have at least one source.")
        return True

    # ────────────────────────────────────────────────────────
    # SCORE MANAGEMENT
    # ────────────────────────────────────────────────────────

    def update_structural_score(self, score: float):
        self.structural_score = round(max(0.0, min(score, 1.0)), 3)
        self.decision_trace.append(f"structural_score={self.structural_score}")

    def update_review_score(self, score: float):
        self.review_score = round(max(0.0, min(score, 1.0)), 3)
        self.decision_trace.append(f"review_score={self.review_score}")

    def compute_final_score(self):
        combined = (self.structural_score * 0.6) + (self.review_score * 0.4)
        self.final_authenticity_score = round(min(combined, 1.0), 3)
        self.assign_grade()
        self.decision_trace.append(f"final_score={self.final_authenticity_score}")

    def assign_grade(self):
        s = self.final_authenticity_score
        if s >= 0.85:   self.grade = Grade.A
        elif s >= 0.70: self.grade = Grade.B
        elif s >= 0.55: self.grade = Grade.C
        else:           self.grade = Grade.D
        self.decision_trace.append(f"grade={self.grade.value}")

    def touch(self):
        self.last_updated = datetime.now(timezone.utc)

    # ────────────────────────────────────────────────────────
    # SERIALISATION
    # ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "entity_id":   self.entity_id,
            "name":        self.name,
            "domain":      self.domain.value,
            "category":    self.category,
            "subcategory": self.subcategory,
            "latitude":    self.latitude,
            "longitude":   self.longitude,
            "sources":     self.sources,
            "structural_score":          self.structural_score,
            "review_score":              self.review_score,
            "final_authenticity_score":  self.final_authenticity_score,
            "grade":       self.grade.value,
            "contextual":  self.contextual.to_dict(),
            "behavioral":  self.behavioral.to_dict(),
            "authenticity": self.authenticity.to_dict(),
            "experience":  self.experience.to_dict(),
            "derived_signals": self.derived_signals.to_dict(),
            "decision_trace": self.decision_trace,
            "created_at":  self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
