"""
Layer 3 data structures.

These are plain dataclasses (JSON-friendly via `to_dict`) so that Layer 4 can consume
the evaluation result without importing any Layer 3 internals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Decision(str, Enum):
    SPEAK = "speak"                # exactly one companion_voice message is delivered
    SILENT = "silent"              # stay quiet, retry in `retry_after_seconds`
    SAFETY_ALERT = "safety_alert"  # safety override — bypasses everything (incl. Quiet Hours)


class SessionStatus(str, Enum):
    SURVEY = "survey"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED_EARLY = "ended_early"
    COMPLETED = "completed"


class SlotStatus(str, Enum):
    PENDING = "pending"
    NOTIFIED = "notified"
    VISITED = "visited"
    SKIPPED = "skipped"
    REPLACED = "replaced"      # temporarily_unavailable -> swapped out by the Replan Trigger
    DROPPED = "dropped"        # removed (Pace Coach / Layer 4) — kept for audit


class SlotRole(str, Enum):
    """The 10 roles used by Layer 2's implementation (superset of the blueprint's 6)."""
    GROUNDING = "GROUNDING"
    DISCOVERY = "DISCOVERY"
    PERSONAL = "PERSONAL"
    PEAK = "PEAK"
    ANCHOR = "ANCHOR"
    LOCAL_SECRET = "LOCAL_SECRET"
    WILDCARD = "WILDCARD"
    REFLECTION = "REFLECTION"
    MEMORY = "MEMORY"
    SIGNATURE = "SIGNATURE"


class SafetyKind(str, Enum):
    """Blueprint §6.2 — exactly three sources can trigger a safety override."""
    WEATHER_ALERT = "weather_alert"
    ADVISORY = "advisory"
    SOS = "sos"


class LayerError(Exception):
    """Base error carrying an HTTP-friendly status code."""

    def __init__(self, message: str, status_code: int = 400, code: str = "layer3_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class NotFound(LayerError):
    def __init__(self, message: str, code: str = "not_found"):
        super().__init__(message, 404, code)


class SourceUnavailable(Exception):
    """A live data source could not be read. Callers must record the gap honestly —
    never substitute a fake 'all clear'."""

    def __init__(self, source: str, reason: str = ""):
        super().__init__(f"{source} unavailable: {reason}" if reason else f"{source} unavailable")
        self.source = source
        self.reason = reason


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "reason": self.reason, **self.detail}


@dataclass
class SignalResult:
    name: str
    score: Optional[float]           # None => not applicable / source unavailable
    weight: float
    available: bool = True
    estimated: bool = False          # True when derived heuristically rather than read from a source
    note: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": None if self.score is None else round(self.score, 3),
            "weight": self.weight,
            "available": self.available,
            "estimated": self.estimated,
            "note": self.note,
            "detail": self.detail,
        }


@dataclass
class TierBResult:
    weighted_average: Optional[float]
    threshold: float
    passed: bool
    signals: List[SignalResult]
    data_gaps: List[str] = field(default_factory=list)
    signals_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weighted_average": None if self.weighted_average is None else round(self.weighted_average, 3),
            "threshold": self.threshold,
            "passed": self.passed,
            "signals_used": self.signals_used,
            "data_gaps": self.data_gaps,
            "signals": [s.to_dict() for s in self.signals],
        }


@dataclass
class SafetyStatus:
    active: bool
    kind: Optional[SafetyKind] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # per-source: checked/active/detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "kind": self.kind.value if self.kind else None,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "sources": self.sources,
        }


@dataclass
class VoiceMessage:
    text: str
    language: str
    voice: str
    place_id: Optional[str] = None
    place_name: Optional[str] = None
    etiquette_whisper: Optional[str] = None
    kind: str = "companion"                 # companion | safety
    tell_more_available: bool = False
    tts_locale: str = "en-IN"
    mode: str = "template"                  # template | llm

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
