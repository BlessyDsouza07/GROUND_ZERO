"""
Replan Trigger — Blueprint §6.3.

When the tourist enters the 300 m zone of a slot whose place is `temporarily_unavailable`:
    1. the slot is removed from the queue (status -> "replaced"),
    2. the unused candidate pool is re-scored in real time,
    3. the next-best place for the SAME role is substituted,
    4. the tourist receives the companion_voice for the substitute — never an error.

The re-scoring here is self-contained (it does not import Layer 2 and does not require any
change to it). It applies the same hard filters and the same Personal Fit formula as the
blueprint (Section 5.1 / 5.2 / 12.1):

    raw = 0.30*companion + 0.20*energy + 0.20*curiosity + 0.15*crowd + 0.15*time
    personal_fit = raw * (1 - bias_index)

so a hyped substitute can never beat an authentic one. Layer 2's 16-component scorer is richer;
this is the blueprint's 5-component core, which is what a real-time swap needs.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from layer3_bridge import MasterCoreStore
from layer3_config import TIME_SUITABILITY, Settings
from layer3_context_engine import CROWD_MATRIX, ENERGY_MATRIX
from layer3_utils import (
    as_list, band_score, haversine_m, hour_float, normalize_crowd_level, normalize_crowd_tolerance,
    normalize_energy, num, parse_opening_hours, pget, place_category, place_id_of, place_latlng,
    place_name_of, place_tags, to_local,
)

NEVER_RECOMMEND = {"STAY", "TRANSPORT", "EMERGENCY", "UNKNOWN"}
PURPOSE_CATEGORIES = {
    "cultural": {"EXPLORE", "SPIRITUAL", "LOCAL_LIFE"},
    "foodie": {"FOOD", "LOCAL_LIFE", "SHOPPING"},
    "adventure": {"NATURE", "EXPLORE"},
    "leisure": {"NATURE", "SHOPPING", "LOCAL_LIFE"},
    "spiritual": {"SPIRITUAL"},
}
PURPOSE_TAGS = {
    "cultural": {"heritage", "history", "culture", "temples", "churches", "architecture", "museum"},
    "foodie": {"local-food", "food", "seafood", "street-food", "authentic"},
    "adventure": {"adventure", "trek", "beach", "nature", "water-sports"},
    "leisure": {"beach", "nature", "relax", "shopping", "park"},
    "spiritual": {"temples", "churches", "spiritual", "pilgrimage", "mosque"},
}
INACCESSIBLE_TAGS = {"stairs-only", "stairs_only", "stairs", "uneven-terrain", "uneven_terrain", "uneven", "steep", "no-wheelchair", "not-wheelchair-accessible"}


class ReplanEngine:
    def __init__(self, s: Settings, master: MasterCoreStore):
        self.s = s
        self.master = master

    # ---------------------------------------------------------------- public
    def find_substitute(self, *, role: str, original_place_id: Optional[str], profile: Dict[str, Any],
                        queue: List[Dict[str, Any]], visited_ids: Set[str], unavailable_ids: Set[str],
                        lat: Optional[float], lng: Optional[float], now: datetime,
                        energy_band: Optional[str], wallet_remaining: Optional[int],
                        current_crowd_hint: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        role = (role or "PERSONAL").upper()
        used = {s["place_id"] for s in queue if s.get("place_id")} | set(visited_ids)
        if original_place_id:
            used.add(str(original_place_id))
        excluded = set(as_list(pget(profile, "return_visitor_exclusions", default=[]))) | used | set(unavailable_ids)
        origin = (lat, lng) if lat is not None and lng is not None else None
        best: Optional[Dict[str, Any]] = None
        considered = 0
        for p in self.master.all():
            pid = place_id_of(p)
            if not pid or pid in excluded:
                continue
            ok, why = self._hard_filters(p, role, profile, origin, now, wallet_remaining, unavailable_ids)
            if not ok:
                continue
            considered += 1
            score = self.personal_fit(p, profile, energy_band, origin, now)
            ll = place_latlng(p)
            d_km = haversine_m(origin[0], origin[1], ll[0], ll[1]) / 1000.0 if origin and ll else 0.0
            # route-efficiency nudge (mirrors Layer 2's Route Efficiency component): a tourist standing at a
            # closed chapel should not be sent across the city if an equally good place is round the corner.
            rank = score["personal_fit"] * max(0.7, 1.0 - 0.06 * d_km)
            if best is None or rank > best["rank_score"]:
                best = {"place": p, "rank_score": round(rank, 4), "distance_km": round(d_km, 2), **score}
        if best:
            best["candidates_considered"] = considered
        return best

    # ---------------------------------------------------------------- hard filters (Blueprint §5.1)
    def _hard_filters(self, p: Dict[str, Any], role: str, profile: Dict[str, Any], origin, now: datetime,
                      wallet_remaining: Optional[int], unavailable_ids: Set[str]):
        cat = place_category(p)
        if cat in NEVER_RECOMMEND:
            return False, "category"
        if place_id_of(p) in unavailable_ids or p.get("temporarily_unavailable"):
            return False, "unavailable"
        if str(p.get("bias_recommendation") or "").lower() == "suppress":
            return False, "suppressed"
        ll = place_latlng(p)
        if not ll:
            return False, "no_coordinates"
        if origin and haversine_m(origin[0], origin[1], ll[0], ll[1]) > self.s.replan_max_distance_km * 1000:
            return False, "too_far"
        cost = p.get("estimated_cost")
        budget_left = wallet_remaining if wallet_remaining is not None else pget(profile, "budget")
        if cost is not None and budget_left is not None and not p.get("is_free_entry") and num(cost) > num(budget_left):
            return False, "over_budget"
        local = to_local(now, self.s.timezone)
        oh = parse_opening_hours(pget(p, "opening_hours", "opening_hours_raw", "hours"))
        if oh.known and oh.is_open(local) is False:
            return False, "closed_now"
        flags = {f.lower().replace(" ", "_") for f in as_list(pget(profile, "accessibility_flags", default=[]))}
        if flags & {"wheelchair", "limited_walking", "limited-walking"}:
            if {t.lower() for t in as_list(p.get("accessibility_tags"))} & INACCESSIBLE_TAGS:
                return False, "accessibility"
        if cat == "FOOD" and not self._diet_ok(p, as_list(pget(profile, "dietary_flags", default=[]))):
            return False, "dietary"
        if not self._role_ok(role, p, cat):
            return False, "role"
        return True, ""

    @staticmethod
    def _diet_ok(p: Dict[str, Any], flags: List[str]) -> bool:
        flags_l = {f.lower() for f in flags}
        if not flags_l & {"veg", "vegetarian", "vegan"}:
            return True
        text = " ".join([str(p.get("food_notes") or "")] + place_tags(p)).lower()
        if not text.strip():
            return True  # unknown -> allowed (unverified)
        cleaned = re.sub(r"non[\s\-_]?veg(etarian)?", "", text)
        if re.search(r"\bveg(etarian|an)?\b", cleaned):
            return True
        return not re.search(r"non[\s\-_]?veg|seafood|fish|beef|mutton|chicken|prawn", text)

    @staticmethod
    def _role_ok(role: str, p: Dict[str, Any], cat: str) -> bool:
        if role == "ANCHOR":
            return cat == "FOOD"
        if role == "LOCAL_SECRET":
            hidden = (p.get("media_mentions") is not None and num(p.get("media_mentions"), 99) <= 5) or \
                     num(p.get("local_percentage"), 0) >= 70 or (p.get("bias_index") is not None and num(p.get("bias_index"), 1) <= 0.1)
            return hidden
        if role in ("SIGNATURE", "PEAK"):
            grade = str(p.get("grade") or "").upper()
            return cat in ("EXPLORE", "NATURE", "SPIRITUAL") and (not grade or grade in ("S", "A", "B"))
        if role == "GROUNDING":
            return cat in ("LOCAL_LIFE", "SHOPPING", "FOOD", "SPIRITUAL") and num(p.get("bias_index"), 0.0) <= 0.4
        if role == "WILDCARD":
            return cat != "FOOD" and num(p.get("bias_index"), 0.0) <= 0.4
        return cat != "FOOD"  # PERSONAL / DISCOVERY / REFLECTION / MEMORY

    # ---------------------------------------------------------------- Personal Fit Score (Blueprint §5.2 / §12.1)
    def personal_fit(self, p: Dict[str, Any], profile: Dict[str, Any], energy_band: Optional[str], origin, now: datetime) -> Dict[str, Any]:
        purpose = str(pget(profile, "purpose", default="")).lower()
        cat = place_category(p)
        tags = set(place_tags(p))
        if purpose in PURPOSE_CATEGORIES:
            companion = 1.0 if cat in PURPOSE_CATEGORIES[purpose] else (0.8 if tags & PURPOSE_TAGS[purpose] else 0.5)
            if cat in PURPOSE_CATEGORIES[purpose] and tags & PURPOSE_TAGS[purpose]:
                companion = 1.0
        else:
            companion = 0.7
        band = normalize_energy(energy_band) or normalize_energy(pget(profile, "energy_band", "energy")) or "medium"
        req = normalize_energy(pget(p, "energy_requirement", "energy_level")) or "medium"
        energy = ENERGY_MATRIX[band][req]
        vec = {v.lower() for v in as_list(pget(profile, "curiosity_vector", default=[]))}
        curiosity = min(1.0, len(vec & tags) / len(vec)) if vec else 0.5
        tol = normalize_crowd_tolerance(pget(profile, "crowd_tolerance"))
        lvl = normalize_crowd_level(p.get("crowd_level"))
        crowd = CROWD_MATRIX[tol][lvl] if tol and lvl else 0.7
        ll = place_latlng(p)
        travel_min = 0.0
        if origin and ll:
            d = haversine_m(origin[0], origin[1], ll[0], ll[1])
            travel_min = d / 1000.0 / (4.0 if d < 1500 else 20.0) * 60.0
        arrive = to_local(now + timedelta(minutes=travel_min), self.s.timezone)
        time_s = band_score(hour_float(arrive), TIME_SUITABILITY.get(cat, TIME_SUITABILITY["DEFAULT"]), 0.5)
        raw = 0.30 * companion + 0.20 * energy + 0.20 * curiosity + 0.15 * crowd + 0.15 * time_s
        bias = min(1.0, max(0.0, num(p.get("bias_index"), 0.5)))
        fit = raw * (1.0 - bias)
        return {"personal_fit": round(fit, 4), "raw_score": round(raw, 4), "bias_index": bias,
                "components": {"companion": round(companion, 2), "energy": round(energy, 2), "curiosity": round(curiosity, 2),
                               "crowd": round(crowd, 2), "time": round(time_s, 2)},
                "travel_minutes_estimate": round(travel_min, 1)}
