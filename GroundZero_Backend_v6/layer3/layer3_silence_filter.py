"""
Silence Filter — "silence is the default, not notifications".

Everything that can keep the app quiet, in the order it is applied by the orchestrator:

    0. safety override            -> the ONLY thing that may break through everything, incl. Quiet Hours
    1. session not active         -> paused / ended_early / completed sessions never notify (Layer 4B)
    2. Quiet Hours                -> tourist muted the app until `quiet_until`
    3. geofence silence           -> once a place has notified us / while dwelling inside its boundary,
                                     send nothing (Blueprint §17: "once inside a place's boundary, the app sends nothing")
    4. group gate (ANCHOR slots)  -> meal/rest slot holds until the whole group_session_id has converged
    5. Tier A hard blockers       -> fatigue gap, movement speed
    6. Tier B weighted signals    -> weighted average >= 0.75

The first gate that says "stay silent" wins; the caller gets a machine-readable `reason` and
`retry_after_seconds` (default 90 s, Blueprint §12.2).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from layer3_config import Settings
from layer3_models import CheckResult, Decision, TierBResult
from layer3_repository import AbstractLayer3Repository
from layer3_utils import ensure_aware, haversine_m, place_latlng


class SilenceFilter:
    def __init__(self, s: Settings, repo: AbstractLayer3Repository):
        self.s = s
        self.repo = repo

    # ---------------------------------------------------------------- gate 1
    @staticmethod
    def session_gate(session: Dict[str, Any]) -> Optional[str]:
        return None if session.get("status") == "active" else "session_not_active"

    # ---------------------------------------------------------------- gate 2
    @staticmethod
    def quiet_gate(session: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
        q = ensure_aware(session.get("quiet_until"))
        if q and q > now:
            return {"reason": "quiet_hours", "quiet_until": q.isoformat(), "remaining_seconds": int((q - now).total_seconds())}
        return None

    # ---------------------------------------------------------------- gate 3
    def geofence_silence(self, session: Dict[str, Any], master, lat: Optional[float], lng: Optional[float],
                         target_place_id: Optional[str]) -> Tuple[Optional[str], bool]:
        """Returns (reason_or_None, release_lock).

        * lock present + tourist within `place_release_m` of the locked place  -> silent
        * lock present + tourist farther away                                  -> release the lock
        * no location supplied (manual trigger without GPS)                    -> lock stays, only same-place is blocked
        """
        lock = session.get("geofence_lock_place_id")
        if not lock:
            return None, False
        if lat is None or lng is None:
            return ("inside_place_boundary" if target_place_id == lock else None), False
        locked = master.get(lock)
        ll = place_latlng(locked) if locked else None
        if not ll:
            return None, True
        d = haversine_m(lat, lng, ll[0], ll[1])
        if d <= self.s.place_release_m:
            return "inside_place_boundary", False
        return None, True

    # ---------------------------------------------------------------- gate 4
    def group_gate(self, session: Dict[str, Any], slot: Dict[str, Any], place: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
        """ANCHOR (meal / rest) slots hold until every *reporting* member of the group is in range.

        Members whose last ping is older than `group_ping_fresh_min` are listed as `unverified` and
        do NOT block (a dead phone must not silence the whole group's lunch forever)."""
        gid = session.get("group_session_id")
        if not gid or str(slot.get("role", "")).upper() != "ANCHOR":
            return None
        ll = place_latlng(place)
        if not ll:
            return None
        members = [m for m in self.repo.group_sessions(gid) if m["session_id"] != session["session_id"] and m.get("status") == "active"]
        if not members:
            return None
        waiting, unverified = [], []
        for m in members:
            p = self.repo.latest_ping(m["session_id"])
            fresh = p and (now - ensure_aware(p["ts"])).total_seconds() <= self.s.group_ping_fresh_min * 60
            if not fresh:
                unverified.append(m["session_id"])
                continue
            if haversine_m(p["lat"], p["lng"], ll[0], ll[1]) > self.s.geofence_radius_m:
                waiting.append(m["session_id"])
        if waiting:
            return {"reason": "group_not_converged", "waiting_for": waiting, "unverified": unverified}
        return None

    # ---------------------------------------------------------------- final arbitration
    def arbitrate(self, tier_a_checks: List[CheckResult], tier_b: Optional[TierBResult]) -> Tuple[Decision, str]:
        for c in tier_a_checks:
            if not c.passed:
                return Decision.SILENT, f"tier_a_failed:{c.name}"
        if tier_b is None:
            return Decision.SILENT, "tier_b_not_evaluated"
        if tier_b.weighted_average is None or tier_b.signals_used < self.s.tier_b_min_signals:
            return Decision.SILENT, "insufficient_signal_data"
        if not tier_b.passed:
            return Decision.SILENT, "tier_b_below_threshold"
        return Decision.SPEAK, "all_clear"
