"""
Context Engine — Blueprint §6.1 two-tier check.

Tier A — Hard blockers (ALL must be true, no thresholds, no exceptions):
    1. safety override clear           (evaluated by SafetyEngine; reported here)
    2. notification-fatigue gap        8 min since last notification (15 min after 2 consecutive dismissals)
    3. movement speed low              < 1 km/h for >= 2 minutes  (they stopped; they're not walking past)

Tier B — Weighted signals (0..1 each, weighted average must reach 0.75):
    time_of_day, weather, crowd_level, energy_compatibility, mood_compatibility,
    season_day_type, tide_state (coastal only), nearby_events, dwell_history

A signal whose data source is down, or that does not apply (tide for an inland place), is
DROPPED and the remaining weights are re-normalised. Dropped signals are listed in
`data_gaps` so nothing is hidden. If fewer than `tier_b_min_signals` signals are available the
Context Engine stays silent (`insufficient_signal_data`) rather than guess.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from layer3_config import TIER_B_WEIGHTS, TIME_SUITABILITY, Settings
from layer3_bridge import MasterCoreStore
from layer3_models import CheckResult, SignalResult, SourceUnavailable, TierBResult
from layer3_sources import SignalSources, is_coastal
from layer3_utils import (
    band_score, clamp, haversine_m, hour_float, is_weekend, jaccard, normalize_crowd_tolerance,
    normalize_energy, num, parse_opening_hours, pget, place_category, place_id_of, place_latlng,
    place_name_of, place_tags, season_of, to_local, ensure_aware,
)

# tourist energy band x place effort -> score   (Blueprint §12.1 examples honoured)
ENERGY_MATRIX = {
    "low": {"low": 1.0, "medium": 0.5, "high": 0.0},
    "medium": {"low": 0.8, "medium": 1.0, "high": 0.6},
    "high": {"low": 0.5, "medium": 0.85, "high": 1.0},
}
# crowd tolerance x current crowd level -> score
CROWD_MATRIX = {
    "love": {"low": 0.6, "medium": 0.8, "high": 0.9},
    "fine": {"low": 1.0, "medium": 0.9, "high": 0.6},
    "prefer_quiet": {"low": 1.0, "medium": 0.6, "high": 0.25},
    "avoid": {"low": 1.0, "medium": 0.4, "high": 0.1},
}
OUTDOOR_WORDS = ("beach", "park", "garden", "viewpoint", "trek", "waterfall", "lake", "fort", "trail", "island", "sunset", "backwater")


def outdoor_factor(place: Dict[str, Any]) -> float:
    """1.0 = fully outdoor, 0.5 = mixed (temple courtyards, heritage sites), 0.1 = essentially indoor."""
    cat = place_category(place)
    hay = " ".join([place_name_of(place), str(place.get("subcategory") or "")] + place_tags(place)).lower()
    if cat == "NATURE" or any(w in hay for w in OUTDOOR_WORDS):
        return 1.0
    if cat in ("EXPLORE", "SPIRITUAL", "EVENTS"):
        return 0.5
    return 0.1


# ---------------------------------------------------------------------------
# Tier A
# ---------------------------------------------------------------------------
class TierAEvaluator:
    def __init__(self, s: Settings):
        self.s = s

    def fatigue(self, session: Dict[str, Any], now: datetime) -> CheckResult:
        streak = int(session.get("consecutive_dismissals") or 0)
        gap_min = self.s.fatigue_gap_after_dismissals_min if streak >= self.s.dismissal_streak else self.s.fatigue_gap_min
        last = ensure_aware(session.get("last_notification_at"))
        detail = {"required_gap_minutes": gap_min, "consecutive_dismissals": streak}
        if last is None:
            return CheckResult("fatigue_gap", True, {**detail, "minutes_since_last": None})
        elapsed = (now - last).total_seconds()
        detail["minutes_since_last"] = round(elapsed / 60.0, 1)
        if elapsed < gap_min * 60:
            detail["remaining_seconds"] = int(gap_min * 60 - elapsed)
            return CheckResult("fatigue_gap", False, detail, reason="fatigue_gap_not_elapsed")
        return CheckResult("fatigue_gap", True, detail)

    def movement(self, pings: List[Dict[str, Any]], now: datetime) -> CheckResult:
        """Tourist has been (almost) stationary for >= movement_window_s.

        Method: every ping in the trailing window (plus the last one before it, to anchor the
        start) must lie within  R = v_max * span + jitter  of the newest ping, where jitter is the
        GPS accuracy (capped). This tolerates GPS jitter but still catches slow strolling
        (1.5 km/h for 2 min => 50 m > R ~ 33 m + jitter would only pass inside the jitter band).
        Not enough history => fail closed (`movement_insufficient_history`), retry in 90 s.
        """
        s = self.s
        pts = sorted((p for p in pings if ensure_aware(p["ts"]) <= now), key=lambda p: p["ts"])
        detail: Dict[str, Any] = {"required_window_s": s.movement_window_s, "max_kmh": s.movement_max_kmh}
        if not pts:
            return CheckResult("movement_speed", False, {**detail, "pings": 0}, reason="movement_insufficient_history")
        newest = pts[-1]
        age = (now - ensure_aware(newest["ts"])).total_seconds()
        detail["newest_ping_age_s"] = int(age)
        if age > s.movement_max_ping_age_s:
            return CheckResult("movement_speed", False, detail, reason="movement_stale_location")
        window_start = now - timedelta(seconds=s.movement_window_s)
        inside = [p for p in pts if ensure_aware(p["ts"]) >= window_start]
        before = [p for p in pts if ensure_aware(p["ts"]) < window_start]
        seq = ([before[-1]] if before else []) + inside
        span = (ensure_aware(seq[-1]["ts"]) - ensure_aware(seq[0]["ts"])).total_seconds()
        detail["span_s"] = int(span)
        detail["pings"] = len(seq)
        # coverage: the oldest observation must reach back (almost) the whole window
        if len(seq) < 2 or (now - ensure_aware(seq[0]["ts"])).total_seconds() < s.movement_window_s - 15:
            return CheckResult("movement_speed", False, detail, reason="movement_insufficient_history")
        acc = max([num(p.get("accuracy_m"), 0.0) for p in seq] + [8.0])
        jitter = min(acc, s.movement_jitter_cap_m)
        v_max_mps = s.movement_max_kmh / 3.6
        allowed = v_max_mps * max(span, s.movement_window_s) + jitter
        farthest = max(haversine_m(p["lat"], p["lng"], newest["lat"], newest["lng"]) for p in seq)
        net = haversine_m(seq[0]["lat"], seq[0]["lng"], newest["lat"], newest["lng"])
        detail.update({"max_radius_m": round(farthest, 1), "allowed_radius_m": round(allowed, 1),
                       "net_speed_kmh": round(net / max(span, 1.0) * 3.6, 2)})
        speeds = [num(p.get("speed_mps"), -1) for p in seq if p.get("speed_mps") is not None]
        if len(speeds) >= 3:
            speeds.sort()
            med = speeds[len(speeds) // 2]
            detail["device_median_kmh"] = round(med * 3.6, 2)
            if med * 3.6 > s.movement_max_kmh * 2:   # device says clearly moving
                return CheckResult("movement_speed", False, detail, reason="tourist_moving")
        if farthest > allowed:
            return CheckResult("movement_speed", False, detail, reason="tourist_moving")
        return CheckResult("movement_speed", True, detail)


# ---------------------------------------------------------------------------
# Tier B
# ---------------------------------------------------------------------------
class TierBEvaluator:
    def __init__(self, s: Settings, sources: SignalSources, master: MasterCoreStore):
        self.s = s
        self.sources = sources
        self.master = master

    def evaluate(self, session: Dict[str, Any], profile: Dict[str, Any], place: Dict[str, Any], now: datetime,
                 lat: Optional[float], lng: Optional[float], visited_ids: List[str]) -> TierBResult:
        local = to_local(now, self.s.timezone)
        ll = place_latlng(place)
        wlat, wlng = (lat, lng) if lat is not None and lng is not None else (ll or (None, None))

        weather: Optional[Dict[str, Any]] = None
        weather_err: Optional[str] = None
        if wlat is not None:
            try:
                weather = self.sources.weather(wlat, wlng)
            except SourceUnavailable as e:
                weather_err = e.reason or "unavailable"
        else:
            weather_err = "no coordinates"

        events: Optional[List[Dict[str, Any]]] = None
        events_err: Optional[str] = None
        try:
            events = self.sources.events_near(place, now)
        except SourceUnavailable as e:
            events_err = e.reason or "unavailable"

        w = TIER_B_WEIGHTS
        signals = [
            self._time(place, local, w["time_of_day"]),
            self._weather(place, weather, weather_err, w["weather"]),
            self._crowd(place, profile, now, weather, events, w["crowd_level"]),
            self._energy(session, profile, place, w["energy_compatibility"]),
            self._mood(session, now, w["mood_compatibility"]),
            self._season(place, local, profile, w["season_day_type"]),
            self._tide(place, w["tide_state"]),
            self._events(events, events_err, w["nearby_events"]),
            self._dwell(place, visited_ids, w["dwell_history"]),
        ]
        usable = [x for x in signals if x.available and x.score is not None]
        gaps = [f"{x.name}: {x.note}" for x in signals if not x.available and x.note and "not applicable" not in x.note]
        if not usable:
            return TierBResult(None, self.s.tier_b_threshold, False, signals, gaps, 0)
        total_w = sum(x.weight for x in usable)
        avg = sum((x.score or 0.0) * x.weight for x in usable) / total_w
        passed = avg >= self.s.tier_b_threshold and len(usable) >= self.s.tier_b_min_signals
        return TierBResult(avg, self.s.tier_b_threshold, passed, signals, gaps, len(usable))

    # ---------------------------------------------------------------- signals
    def _time(self, place, local, weight) -> SignalResult:
        cat = place_category(place)
        bands = TIME_SUITABILITY.get(cat, TIME_SUITABILITY["DEFAULT"])
        score = band_score(hour_float(local), bands, 0.5)
        detail: Dict[str, Any] = {"local_time": local.strftime("%H:%M"), "category": cat}
        raw_hours = pget(place, "opening_hours", "opening_hours_raw", "hours")
        oh = parse_opening_hours(raw_hours)
        is_open = oh.is_open(local) if oh.known else None
        if is_open is not None:
            detail["open_now"] = is_open
            detail["closes_at"] = oh.closing_time_today(local)
            if not is_open:
                score = min(score, 0.05)
                detail["flag"] = "closed_now_by_opening_hours"
        return SignalResult("time_of_day", score, weight, True, False, "", detail)

    def _weather(self, place, weather, err, weight) -> SignalResult:
        if weather is None:
            return SignalResult("weather", None, weight, False, False, err or "unavailable")
        f = outdoor_factor(place)
        precip = num(weather.get("precipitation_mm"))
        if weather.get("is_severe"):
            out_s, in_s = 0.0, 0.4
        elif precip >= 2.5:
            out_s, in_s = 0.2, 0.8
        elif precip >= 0.5 or (weather.get("is_rainy") and not weather.get("is_drizzle")):
            out_s, in_s = 0.35, 0.85
        elif weather.get("is_drizzle") or precip >= 0.1:
            out_s, in_s = 0.6, 0.95
        else:
            out_s, in_s = 1.0, 0.95
        if num(weather.get("temperature_c"), 28) >= 37:
            out_s = min(out_s, 0.55)
        score = out_s * f + in_s * (1 - f)
        return SignalResult("weather", score, weight, True, False, "", {
            "outdoor_factor": f, "precipitation_mm": precip, "temperature_c": weather.get("temperature_c"),
            "source": weather.get("source")})

    def _crowd(self, place, profile, now, weather, events, weight) -> SignalResult:
        tol = normalize_crowd_tolerance(pget(profile, "crowd_tolerance", "crowd_comfort"))
        if tol is None:
            return SignalResult("crowd_level", None, weight, False, False, "tourist crowd_tolerance missing")
        c = self.sources.crowd(place, now, weather, events)
        score = CROWD_MATRIX[tol][c["level"]]
        return SignalResult("crowd_level", score, weight, True, bool(c.get("estimated")), "",
                            {"tolerance": tol, "crowd": c["level"], "basis": c.get("basis")})

    def _energy(self, session, profile, place, weight) -> SignalResult:
        band = normalize_energy(session.get("energy_band")) or normalize_energy(pget(profile, "energy_band", "energy"))
        req = normalize_energy(pget(place, "energy_requirement", "energy_level"))
        if band is None:
            return SignalResult("energy_compatibility", None, weight, False, False, "tourist energy_band missing")
        if req is None:
            req = "medium"
            return SignalResult("energy_compatibility", ENERGY_MATRIX[band][req], weight, True, True,
                                "place has no energy_requirement — assumed medium", {"tourist": band, "place": req})
        return SignalResult("energy_compatibility", ENERGY_MATRIX[band][req], weight, True, False, "", {"tourist": band, "place": req})

    def _mood(self, session, now, weight) -> SignalResult:
        """No repeated recent dismissals; and a post-mood-check fatigue flag lowers the score for a while."""
        score = 1.0
        streak = int(session.get("consecutive_dismissals") or 0)
        detail: Dict[str, Any] = {"consecutive_dismissals": streak}
        if streak == 1:
            score -= 0.2
        elif streak >= 2:
            score -= 0.6
        upd = ensure_aware(session.get("energy_updated_at"))
        if upd and normalize_energy(session.get("energy_band")) == "low" and (now - upd) < timedelta(minutes=20):
            score -= 0.25
            detail["recent_low_energy_update"] = True
        return SignalResult("mood_compatibility", clamp(score), weight, True, False, "", detail)

    def _season(self, place, local, profile, weight) -> SignalResult:
        season = season_of(local)
        wanted = [x.lower() for x in (place.get("season_suitability") or [])] if isinstance(place.get("season_suitability"), list) else []
        detail: Dict[str, Any] = {"season": season, "weekend": is_weekend(local)}
        estimated = False
        if wanted:
            ok = season in wanted or "all" in wanted or "year_round" in wanted or "all_year" in wanted
            score = 1.0 if ok else 0.4
        else:
            estimated = True
            score = 0.9
            if season == "monsoon" and (is_coastal(place) or outdoor_factor(place) >= 1.0):
                score = 0.55
        if is_weekend(local) and place_category(place) in ("NATURE", "SHOPPING", "EVENTS"):
            tol = normalize_crowd_tolerance(pget(profile, "crowd_tolerance"))
            if tol in ("prefer_quiet", "avoid"):
                score -= 0.1
        return SignalResult("season_day_type", clamp(score), weight, True, estimated, "", detail)

    def _tide(self, place, weight) -> SignalResult:
        if not is_coastal(place):
            return SignalResult("tide_state", None, weight, False, False, "not applicable (inland place)")
        try:
            t = self.sources.tide(place)
        except SourceUnavailable as e:
            return SignalResult("tide_state", None, weight, False, False, e.reason or "unavailable")
        wave = t.get("wave_height_m")
        if wave is None:
            safe = t.get("safe_for_swimming")
            if safe is None:
                return SignalResult("tide_state", None, weight, False, False, "tide record has no wave height or safety flag")
            score = 0.9 if safe else 0.25
        elif wave < 1.0:
            score = 1.0
        elif wave < 1.5:
            score = 0.75
        elif wave < 2.5:
            score = 0.4
        else:
            score = 0.1
        if t.get("safe_for_swimming") is False:
            score = min(score, 0.3)
        return SignalResult("tide_state", score, weight, True, False, "", {
            "wave_height_m": wave, "tide_state": t.get("tide_state"), "source": t.get("source")})

    def _events(self, events, err, weight) -> SignalResult:
        if events is None:
            return SignalResult("nearby_events", None, weight, False, False, err or "unavailable")
        if not events:
            return SignalResult("nearby_events", 1.0, weight, True, False, "", {"events": 0})
        big = any(e.get("big") for e in events)
        return SignalResult("nearby_events", 0.25 if big else 0.55, weight, True, False, "",
                            {"events": [e["title"] for e in events[:3]], "big_event": big})

    def _dwell(self, place, visited_ids, weight) -> SignalResult:
        pid = place_id_of(place)
        if pid and pid in visited_ids:
            return SignalResult("dwell_history", 0.0, weight, True, False, "", {"already_visited": True})
        cat, sub, tags = place_category(place), place.get("subcategory"), place_tags(place)
        for vid in visited_ids:
            v = self.master.get(vid)
            if not v:
                continue
            same_sub = bool(sub) and sub == v.get("subcategory") and cat == place_category(v)
            if same_sub or jaccard(tags, place_tags(v)) >= 0.8:
                return SignalResult("dwell_history", 0.4, weight, True, False, "", {"near_identical_to": place_name_of(v)})
        return SignalResult("dwell_history", 1.0, weight, True, False, "", {"already_visited": False})
