"""
core/base_models.py

Foundation data models for the 6-domain City Intelligence Data Core.

This module is:
- Deterministic
- Domain-agnostic
- Fully serializable
- Engine-independent
- Scalable across cities
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import uuid


# ============================================================
# DOMAIN ENUM (6 CORE DOMAINS)
# ============================================================

class Domain(str, Enum):
    PLACES = "places"
    FOOD = "food"
    CULTURE = "culture"
    ACTIVITIES = "activities"
    TRAVEL_INTEL = "travel_intel"
    SAFETY_SUPPORT = "safety_support"


# ============================================================
# GRADE SYSTEM
# ============================================================

class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# ============================================================
# DERIVED SIGNAL CONTAINER
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
# BASE ENTITY MODEL
# ============================================================

@dataclass
class BaseEntity:
    # Core Identity
    name: str
    domain: Domain
    category: str
    subcategory: str
    latitude: float
    longitude: float
    sources: List[str]

    # Auto fields
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    # Scoring
    structural_score: float = 0.0
    review_score: float = 0.0
    domain_score: float = 0.0
    final_authenticity_score: float = 0.0
    grade: Grade = Grade.D

    # Signals
    derived_signals: DerivedSignals = field(default_factory=DerivedSignals)

    # Explainability
    decision_trace: List[str] = field(default_factory=list)

    # ============================================================
    # VALIDATION
    # ============================================================

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

    # ============================================================
    # SCORING METHODS
    # ============================================================

    def update_structural_score(self, score: float):
        self.structural_score = round(max(0.0, min(score, 1.0)), 3)
        self.decision_trace.append(f"Structural score set to {self.structural_score}")

    def update_review_score(self, score: float):
        self.review_score = round(max(0.0, min(score, 1.0)), 3)
        self.decision_trace.append(f"Review score set to {self.review_score}")

    def compute_final_score(self):
        """
        Default deterministic formula:
        60% structural
        40% review/domain score
        """

        combined = (self.structural_score * 0.6) + (self.review_score * 0.4)
        self.final_authenticity_score = round(min(combined, 1.0), 3)

        self.assign_grade()

        self.decision_trace.append(
            f"Final authenticity score computed: {self.final_authenticity_score}"
        )

    def assign_grade(self):
        score = self.final_authenticity_score

        if score >= 0.85:
            self.grade = Grade.A
        elif score >= 0.70:
            self.grade = Grade.B
        elif score >= 0.55:
            self.grade = Grade.C
        else:
            self.grade = Grade.D

        self.decision_trace.append(f"Grade assigned: {self.grade.value}")

    # ============================================================
    # SERIALIZATION
    # ============================================================

    def to_dict(self) -> Dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "domain": self.domain.value,
            "category": self.category,
            "subcategory": self.subcategory,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "sources": self.sources,
            "structural_score": self.structural_score,
            "review_score": self.review_score,
            "domain_score": self.domain_score,
            "final_authenticity_score": self.final_authenticity_score,
            "grade": self.grade.value,
            "derived_signals": self.derived_signals.to_dict(),
            "decision_trace": self.decision_trace,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    # ============================================================
    # UPDATE TIMESTAMP
    # ============================================================

    def touch(self):
        self.last_updated = datetime.utcnow()
        self.decision_trace.append("Entity timestamp updated")


# ============================================================
# SIMPLE TEST EXECUTION (SAFE TO RUN)
# ============================================================

if __name__ == "__main__":
    entity = BaseEntity(
        name="Panambur Beach",
        domain=Domain.PLACES,
        category="Nature",
        subcategory="Beach",
        latitude=12.95,
        longitude=74.80,
        sources=["OSM", "TourismBoard"]
    )

    entity.validate()
    entity.update_structural_score(0.82)
    entity.update_review_score(0.76)
    entity.compute_final_score()

    print(entity.to_dict())
