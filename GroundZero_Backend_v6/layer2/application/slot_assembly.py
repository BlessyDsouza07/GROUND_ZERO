"""
Slot Assembly (blueprint Table 5). Takes hard-filtered, scored candidates
and assembles them into the day's narrative arc:

  Grounding -> Signature -> Anchor -> Personal (incl. Wildcard) -> Local Secret

Selection order matters: Grounding/Signature/Anchor/Local Secret are each
filled by their own criterion first (so a place doesn't get "used up" by
a lower-priority role), then Personal slots (including the Wildcard) are
filled from what's left, ranked by personal_fit.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from layer0.domain.entities import Place
from layer1.domain.entities import TripDuration
from layer2.domain.entities import (
    SLOT_COUNTS_FULL_DAY,
    SLOT_COUNTS_HALF_DAY,
    WILDCARD_COUNT_FULL_DAY,
    WILDCARD_COUNT_HALF_DAY,
    ScoredPlace,
    SlotRole,
)

# "Everyday Mangalore place" categories eligible for the Grounding slot —
# ordinary, non-touristy, low-bias places that "ease the tourist in."
_GROUNDING_CATEGORIES = {"cafe", "market", "local_kitchen", "bakery", "park"}

# The "one flagship must-see" — Signature slot draws from genuinely
# iconic/heritage categories with meaningfully low bias (i.e. not a hyped
# trap), ranked by personal_fit among eligible candidates.
_SIGNATURE_CATEGORIES = {"heritage_site", "museum", "tourist_attraction", "beach", "viewpoint", "place_of_worship"}

# Meal/rest-break categories for the Anchor slot.
_ANCHOR_CATEGORIES = {"restaurant", "food_court", "cafe", "local_kitchen"}

LOCAL_SECRET_MAX_MEDIA_MENTIONS = 3
LOCAL_SECRET_MIN_LOCAL_PERCENTAGE = 0.9


@dataclass
class AssembledSlot:
    role: SlotRole
    scored_place: ScoredPlace
    is_wildcard: bool = False


class SlotAssemblyService:
    def __init__(self, random_seed: int | None = None):
        self._rng = random.Random(random_seed)

    def _slot_counts(self, trip_duration: TripDuration) -> tuple[dict[SlotRole, int], int]:
        if trip_duration == TripDuration.HALF_DAY:
            return SLOT_COUNTS_HALF_DAY, WILDCARD_COUNT_HALF_DAY
        return SLOT_COUNTS_FULL_DAY, WILDCARD_COUNT_FULL_DAY  # FULL_DAY and MULTI_DAY (per-day) both use full-day counts

    def assemble(
        self,
        candidates: list[ScoredPlace],
        places_by_id: dict[str, Place],
        trip_duration: TripDuration,
    ) -> list[AssembledSlot]:
        counts, wildcard_count = self._slot_counts(trip_duration)
        # Shuffle first (seeded, reproducible), then stable-sort by
        # personal_fit descending — ties land in shuffled order rather
        # than arbitrary input-list order. This is what self._rng and
        # random_seed actually exist for; previously self._rng was
        # constructed but never used anywhere, making random_seed a
        # silent no-op — confirmed by an architectural audit.
        shuffled = list(candidates)
        self._rng.shuffle(shuffled)
        remaining = sorted(
            shuffled,
            key=lambda c: c.rank_score if c.rank_score is not None else c.personal_fit,
            reverse=True,
        )
        used_ids: set[str] = set()
        assembled: list[AssembledSlot] = []

        def take_best(category_set: set[str], n: int, role: SlotRole) -> None:
            nonlocal remaining
            taken = 0
            for candidate in list(remaining):
                if taken >= n:
                    break
                place = places_by_id.get(candidate.place_id)
                if place is None or candidate.place_id in used_ids:
                    continue
                if place.category not in category_set:
                    continue
                assembled.append(AssembledSlot(role=role, scored_place=candidate))
                used_ids.add(candidate.place_id)
                taken += 1

        # Grounding, Signature, Anchor: each filled first by its own criterion
        take_best(_GROUNDING_CATEGORIES, counts[SlotRole.GROUNDING], SlotRole.GROUNDING)
        take_best(_SIGNATURE_CATEGORIES, counts[SlotRole.SIGNATURE], SlotRole.SIGNATURE)
        take_best(_ANCHOR_CATEGORIES, counts[SlotRole.ANCHOR], SlotRole.ANCHOR)

        # Local Secret: near-zero media mentions, ~100% local source
        local_secret_pool = [
            c for c in remaining
            if c.place_id not in used_ids and c.is_local_secret_eligible
        ]
        for candidate in local_secret_pool[: counts[SlotRole.LOCAL_SECRET]]:
            assembled.append(AssembledSlot(role=SlotRole.LOCAL_SECRET, scored_place=candidate))
            used_ids.add(candidate.place_id)

        # Personal (including Wildcard): fill remaining slots by personal_fit,
        # then designate the required number as Wildcard — places whose
        # category falls OUTSIDE the tourist's dominant curiosity categories,
        # i.e. "the guide's trust me on this."
        personal_pool = [c for c in remaining if c.place_id not in used_ids]
        personal_target = counts[SlotRole.PERSONAL]

        wildcard_candidates = [
            c for c in personal_pool
            if places_by_id.get(c.place_id) and c.breakdown.get("curiosity_score", 1.0) < 0.4
        ]
        chosen_wildcards: list[ScoredPlace] = wildcard_candidates[:wildcard_count]
        for wc in chosen_wildcards:
            assembled.append(AssembledSlot(role=SlotRole.PERSONAL, scored_place=wc, is_wildcard=True))
            used_ids.add(wc.place_id)

        remaining_personal_slots = personal_target - len(chosen_wildcards)
        personal_pool = [c for c in remaining if c.place_id not in used_ids]
        for candidate in self._fill_personal_diverse(personal_pool, remaining_personal_slots, places_by_id):
            assembled.append(AssembledSlot(role=SlotRole.PERSONAL, scored_place=candidate))
            used_ids.add(candidate.place_id)

        return assembled

    def _fill_personal_diverse(
        self, pool: list[ScoredPlace], n: int, places_by_id: dict[str, Place],
    ) -> list[ScoredPlace]:
        """Fills up to n Personal slots off `pool` (already personal_fit-
        sorted), capping how many slots the same place category can take.

        Bug fixed: the previous version was `pool[:n]` — pure top-N by
        personal_fit with no diversity check at all. That's fine when
        candidates are genuinely spread across categories, but breaks
        down for a profile whose curiosity/purpose concentrates on one
        category (e.g. "spiritual" + a curiosity sentence mentioning
        temples): when several same-category places carry an identical
        or near-identical personal_fit — which happens often, since
        category-level priors (layer0/application/place_enricher.py,
        bias_signal_estimator.py) give every unenriched place in that
        category the same energy/crowd/dwell/bias numbers — a pure top-N
        cut has no basis to prefer variety, and the day fills with one
        category end to end (confirmed: 7 of 9 Personal slots on the
        same real profile were all "heritage_site" places tied at the
        exact same personal_fit). Capping keeps the day matching
        everything the tourist actually asked for (temples AND beaches
        AND viewpoints), not just whichever category happened to have
        the most near-duplicate candidates.

        The cap only applies while there's enough variety to honor it —
        a second, uncapped pass fills any slots the capped pass couldn't,
        because filling the day always wins over enforcing variety.
        """
        if n <= 0:
            return []
        max_per_category = max(2, math.ceil(n * 0.34))
        chosen: list[ScoredPlace] = []
        chosen_ids: set[str] = set()
        category_counts: dict[str, int] = {}
        for candidate in pool:
            if len(chosen) >= n:
                break
            place = places_by_id.get(candidate.place_id)
            category = place.category if place else None
            if category and category_counts.get(category, 0) >= max_per_category:
                continue
            chosen.append(candidate)
            chosen_ids.add(candidate.place_id)
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

        if len(chosen) < n:
            for candidate in pool:
                if len(chosen) >= n:
                    break
                if candidate.place_id in chosen_ids:
                    continue
                chosen.append(candidate)
                chosen_ids.add(candidate.place_id)

        return chosen
