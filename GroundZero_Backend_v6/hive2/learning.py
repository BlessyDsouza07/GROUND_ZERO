"""Traveller memory updates. Every affinity records where it came from and
how sure we are, so the person can see and change it. Impressions ("shown")
are never treated as likes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .experience import classify

DELTAS = {"opened": 0.03, "saved": 0.25, "navigated": 0.20, "visited": 0.15}
NEUTRAL_SKIP_REASONS = {"closed", "no_time", "too_far", "seen_it", "other"}
DECAY_HALF_LIFE_DAYS = 90


def _now_iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def _bump(aff: dict, key: str, delta: float, source: str, now: Optional[datetime]):
    a = aff.get(key) or {"weight": 0.0, "confidence": 0.0, "source": source}
    a["weight"] = round(max(-1.0, min(1.0, a["weight"] + delta)), 3)
    a["confidence"] = round(min(1.0, a.get("confidence", 0.0) + 0.1), 2)
    if a.get("source") != "stated":      # what the person typed themselves is never overwritten as "behaviour"
        a["source"] = source
    a["updated"] = _now_iso(now)
    aff[key] = a


def delta_for(kind: str, reason: Optional[str] = None, rating: Optional[int] = None) -> float:
    if kind == "dismissed":
        return -0.25 if reason == "not_interested" else 0.0
    if kind == "rated" and rating:
        return round((max(1, min(5, rating)) - 3) / 2 * 0.3, 3)
    return DELTAS.get(kind, 0.0)


def apply_event(affinities: dict, place, kind: str, reason: Optional[str] = None,
                rating: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    d = delta_for(kind, reason, rating)
    if d == 0.0:
        return affinities
    k = classify(place, now)
    for key, strength in k.experiences.items():
        _bump(affinities, f"exp:{key}", d * strength, "behaviour", now)
    _bump(affinities, f"cat:{k.category}", d * 0.6, "behaviour", now)
    return affinities


def set_stated(affinities: dict, key: str, weight: float, now: Optional[datetime] = None) -> dict:
    affinities[key] = {"weight": round(max(-1, min(1, weight)), 3), "confidence": 0.9,
                       "source": "stated", "updated": _now_iso(now)}
    return affinities


def decayed(affinities: dict, now: Optional[datetime] = None) -> dict:
    """Old behaviour fades; what the person stated does not."""
    now = now or datetime.now(timezone.utc)
    out = {}
    for k, a in affinities.items():
        a = dict(a)
        if a.get("source") != "stated":
            try:
                t = datetime.fromisoformat(a.get("updated"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                days = max(0, (now - t).days)
                a["weight"] = round(a["weight"] * 0.5 ** (days / DECAY_HALF_LIFE_DAYS), 3)
            except Exception:
                pass
        if abs(a["weight"]) >= 0.02 or a.get("source") == "stated":
            out[k] = a
    return out


def seed_from_survey(survey: dict) -> dict:
    """Optional: start from what the person said in the trip survey. Marked
    'survey' with modest confidence."""
    aff: dict = {}
    interests = [str(x).lower() for x in (survey or {}).get("interests", [])]
    table = {"beach": "coastal", "coastal": "coastal", "food": "food", "heritage": "heritage", "culture": "heritage",
             "nature": "nature", "markets": "neighbourhood", "local": "neighbourhood"}
    for i in interests:
        if i in table:
            aff[f"exp:{table[i]}"] = {"weight": 0.4, "confidence": 0.5, "source": "survey", "updated": _now_iso()}
    return aff
