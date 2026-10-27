"""Context-aware geofencing, server side and privacy-minimal.

* Only runs with the person's location consent (checked by the caller).
* The coordinates arrive, are used to decide, and are discarded. What is
  stored per place: inside?, entered_at, last_notified_at, count.
* Poor GPS accuracy makes no decision.
* Hysteresis: enter inside r, leave only beyond 1.5 r (no flicker).
* Dwell: must remain inside for a short time before anything is suggested.
* Cooldown per place (persisted), a daily cap, and a quiet mode.
* Never suggests a place that is closed, visited or dismissed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .ranker import km

MAX_ACCURACY_M = 100
BASE_RADIUS_M = 60
MAX_RADIUS_M = 150
DWELL_SECONDS = 30
COOLDOWN = timedelta(hours=6)
DAILY_CAP = 5


@dataclass
class PlaceState:
    inside: bool = False
    entered_at: Optional[datetime] = None
    last_notified_at: Optional[datetime] = None
    notify_count: int = 0


def radius_m(accuracy_m: float) -> float:
    return max(BASE_RADIUS_M, min(MAX_RADIUS_M, accuracy_m))


def evaluate(candidates, lat: float, lon: float, accuracy_m: float, states: dict, now: datetime,
             quiet: bool = False, notified_today: int = 0):
    """candidates: iterable of (place_id, name, lat, lon, open_state, excluded_bool).
    states: place_id -> PlaceState (mutated). Returns notification dict or None."""
    if accuracy_m is None or accuracy_m > MAX_ACCURACY_M:
        return {"notify": None, "reason": "location_accuracy_too_low"}
    r = radius_m(accuracy_m)
    best = None
    for pid, name, plat, plon, open_state, excluded in candidates:
        d = km(lat, lon, plat, plon) * 1000
        st = states.setdefault(pid, PlaceState())
        if d <= r:
            if not st.inside:
                st.inside, st.entered_at = True, now
        elif d > r * 1.5 and st.inside:
            st.inside, st.entered_at = False, None
            continue
        if not st.inside:
            continue
        if excluded or open_state == "closed":
            continue
        if (now - (st.entered_at or now)).total_seconds() < DWELL_SECONDS:
            continue
        if st.last_notified_at and now - st.last_notified_at < COOLDOWN:
            continue
        if best is None or d < best[0]:
            best = (d, pid, name, st)
    if quiet:
        return {"notify": None, "reason": "quiet_mode"}
    if notified_today >= DAILY_CAP:
        return {"notify": None, "reason": "daily_cap"}
    if not best:
        return {"notify": None, "reason": "nothing_to_say"}
    d, pid, name, st = best
    st.last_notified_at, st.notify_count = now, st.notify_count + 1
    return {"notify": {"place_id": pid, "name": name, "distance_m": int(d)}, "reason": "dwelling_near_place"}
