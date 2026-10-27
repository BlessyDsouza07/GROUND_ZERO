"""
Ranking v2 — four evidence-based upgrades layered on top of the blueprint
Personal Fit Score, which is left untouched (Table 10 worked examples in
test_personal_fit_score.py must keep matching exactly).

What was wrong, measured on the 722-place Master Data Core:

1. **Eligibility.** Personal slots were filled from every surviving
   candidate, so hotels (104 rows), `uncategorized`, transit points and
   shops could be scheduled as stops. `eligible()` gates the pool with the
   shared whitelist (shared/place_taxonomy.py); ineligible places stay in
   the database for the Ask Engine and geofence.
2. **Ties.** 477 of 722 places share one of two bias_index values, and the
   fit components are coarse steps, so hundreds of places score identically
   and the tie order was random. `rank_score()` breaks ties with real,
   place-specific evidence instead of a shuffle:
       rank = fit * (1 - c_pen * (1 - confidence)) * (1 - w_prox + w_prox * exp(-d / scale))
   where `confidence` in [0, 1] is how much of the place's data is real
   (description, opening hours, several sources, freshness, wiki context,
   accessibility info) and `d` is distance from the tourist. Both factors
   are bounded (default <= 10 % each) so they reorder near-equals; they can
   never overturn a genuinely better fit.
3. **Geography.** Stops were emitted in slot-role order, so the day zig-
   zagged across the city. `order_route()` keeps the narrative arc (Grounding
   and Signature first, Local Secret last) and orders the middle as the
   shortest open path (nearest-neighbour + 2-opt), then places the meal
   Anchor where the clock is closest to lunchtime.
4. **Canonical categories.** CSV rows typed "temple"/"mosque" now count as
   heritage_site everywhere (see place_taxonomy.canonical_category).

No I/O, no randomness: same input -> same itinerary.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime

from layer0.application.dedup import haversine_meters
from layer0.domain.entities import Place
from layer2.application.slot_assembly import AssembledSlot
from layer2.domain.entities import SlotRole
from shared.place_taxonomy import canonical_category, is_itinerary_eligible


@dataclass(frozen=True)
class RankingConfig:
    confidence_penalty: float = 0.10     # max relative penalty for a place with no real data
    proximity_weight: float = 0.10       # max relative penalty for a place far from the tourist
    proximity_scale_km: float = 6.0      # exp(-d/scale): half-weight distance ~ 0.69*scale
    min_eligible_pool: int = 8           # below this, don't gate (better a full day than an empty one)
    lunch_hour: float = 13.25
    travel_kmh: float = 18.0             # city-average door-to-door speed used only for ordering
    travel_overhead_min: float = 5.0


def data_confidence(place: Place) -> float:
    """0..1 — how much of this place's record is real rather than a category prior."""
    c = 0.0
    if place.description or place.wiki_summary:
        c += 0.25
    if place.opening_hours and getattr(place.opening_hours, "raw", None):
        c += 0.20
    if len(place.source or []) >= 2:
        c += 0.15
    c += 0.20 * max(0.0, min(1.0, place.freshness_score or 0.0))
    if "has-wiki-context" in (place.tags or []):
        c += 0.10
    acc = place.accessibility
    if acc and (getattr(acc, "tags", None) or getattr(acc, "wheelchair", None) is not None):
        c += 0.10
    return min(1.0, c)


def eligible(places: list[Place], cfg: RankingConfig) -> list[Place]:
    """Canonicalise categories, then keep only places that may be proposed
    as a stop. Falls back to the unfiltered pool if the gate would leave too
    few places to build a day."""
    canon = [replace(p, category=canonical_category(p.category)) if canonical_category(p.category) != p.category else p
             for p in places]
    kept = [p for p in canon if is_itinerary_eligible(p.category)]
    return kept if len(kept) >= cfg.min_eligible_pool else canon


def rank_score(personal_fit: float, place: Place, cfg: RankingConfig,
               origin: tuple[float, float] | None) -> float:
    score = personal_fit * (1.0 - cfg.confidence_penalty * (1.0 - data_confidence(place)))
    if origin is not None:
        d_km = haversine_meters(origin[0], origin[1], place.coordinates.latitude, place.coordinates.longitude) / 1000.0
        score *= (1.0 - cfg.proximity_weight) + cfg.proximity_weight * math.exp(-d_km / cfg.proximity_scale_km)
    return score


# ---------------------------------------------------------------- routing
def _pt(slot: AssembledSlot, places: dict[str, Place]) -> tuple[float, float] | None:
    p = places.get(slot.scored_place.place_id)
    return (p.coordinates.latitude, p.coordinates.longitude) if p else None


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return haversine_meters(a[0], a[1], b[0], b[1]) / 1000.0


def _path_len(start, pts, end) -> float:
    seq = ([start] if start else []) + pts + ([end] if end else [])
    return sum(_km(seq[i], seq[i + 1]) for i in range(len(seq) - 1))


def _two_opt(start, pts, end):
    best, best_len = list(pts), _path_len(start, pts, end)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                l = _path_len(start, cand, end)
                if l + 1e-9 < best_len:
                    best, best_len, improved = cand, l, True
    return best


def order_route(assembled: list[AssembledSlot], places: dict[str, Place], start_time: datetime,
                cfg: RankingConfig, origin: tuple[float, float] | None = None) -> list[AssembledSlot]:
    """Reorder for a short, sensible day. Returns the input unchanged if any
    slot has no coordinates."""
    pts = {id(s): _pt(s, places) for s in assembled}
    if any(v is None for v in pts.values()) or len(assembled) < 4:
        return assembled

    head = [s for s in assembled if s.role in (SlotRole.GROUNDING, SlotRole.SIGNATURE)]
    tail = [s for s in assembled if s.role == SlotRole.LOCAL_SECRET]
    anchors = [s for s in assembled if s.role == SlotRole.ANCHOR]
    mid = [s for s in assembled if s not in head and s not in tail and s not in anchors]

    start = pts[id(head[-1])] if head else origin
    end = pts[id(tail[0])] if tail else None

    # nearest-neighbour seed, then 2-opt
    order, cur, pool = [], start, list(mid)
    while pool:
        nxt = min(pool, key=lambda s: _km(cur, pts[id(s)]) if cur else 0.0)
        order.append(nxt); pool.remove(nxt); cur = pts[id(nxt)]
    mid_pts = [pts[id(s)] for s in order]
    opt = _two_opt(start, mid_pts, end)
    by_pt: dict[tuple[float, float], list[AssembledSlot]] = {}
    for s in order:
        by_pt.setdefault(pts[id(s)], []).append(s)
    order = [by_pt[p].pop(0) for p in opt]

    # clock along head + mid to find where lunch falls
    clock = start_time.hour + start_time.minute / 60.0
    prev = origin
    def advance(slot):
        nonlocal clock, prev
        p = places[slot.scored_place.place_id]
        here = pts[id(slot)]
        if prev is not None:
            clock += (_km(prev, here) / cfg.travel_kmh) * 60 / 60.0 + cfg.travel_overhead_min / 60.0
        clock += p.dwell_time_typical_minutes / 60.0
        prev = here
    for s in head:
        advance(s)
    arrival = [clock]                      # clock available before mid[k]
    for s in order:
        advance(s)
        arrival.append(clock)
    k = min(range(len(arrival)), key=lambda i: abs(arrival[i] - cfg.lunch_hour)) if anchors else 0
    return head + order[:k] + anchors + order[k:] + tail
