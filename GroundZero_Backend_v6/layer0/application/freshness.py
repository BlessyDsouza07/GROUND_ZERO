"""
Freshness scoring (blueprint 3.4 `freshness_score`, used by Layer 2 Hard
Filters — "freshness_score too low" per Table 3/5.1).

freshness_score decays from 1.0 the longer a place has gone unverified by
any collector pass, and gets a hard penalty if a source explicitly marks it
temporarily_unavailable. This is pure time math — no I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

from layer0.domain.entities import Place


class FreshnessService:
    def __init__(self, stale_after_days: int = 180):
        self.stale_after_days = stale_after_days

    def score(self, place: Place, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)

        if place.temporarily_unavailable:
            return 0.0

        if place.last_verified_at is None:
            return 0.0  # never verified by any collector -> not trustworthy yet

        age_days = (now - place.last_verified_at).total_seconds() / 86400.0
        if age_days <= 0:
            return 1.0

        # Linear decay to 0 at stale_after_days, floored at 0.
        score = max(0.0, 1.0 - (age_days / self.stale_after_days))
        return round(score, 4)

    def is_fresh_enough(self, place: Place, min_score: float, now: datetime | None = None) -> bool:
        return self.score(place, now=now) >= min_score
