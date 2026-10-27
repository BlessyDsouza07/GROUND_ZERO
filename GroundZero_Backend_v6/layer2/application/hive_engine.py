"""
HIVE Engine orchestrator (blueprint Section 5 pipeline diagram):

  Hard Filters -> Personal Fit Score -> Weather scheduling -> Slot assembly
    -> Transport tagging -> Recommendation Queue

Note: the blueprint's pipeline diagram lists "Weather scheduling" before
"Slot assembly", but weather-based rescheduling operates on *already
time-ordered* slots (it moves outdoor slots away from rain hours within a
sequence). We therefore assemble slots first (which produces the role-
ordered sequence: Grounding -> Signature -> Anchor -> Personal -> Local
Secret), THEN apply weather adjustment to that sequence — the only order
in which "reschedule around rain" is a meaningful operation. This is a
deliberate, documented deviation from the diagram's literal box order.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta

from layer0.domain.entities import Place
from layer0.domain.repositories import PlaceRepository
from layer0.infrastructure.collectors.weather_collector import HourlyForecast, WeatherCollector
from layer0.infrastructure.http_client import SourceUnavailable
from layer1.domain.entities import TouristProfile, TripDuration
from layer2.application.hard_filters import HardFilterService
from layer2.application.personal_fit_score import PersonalFitScoreService
from layer2.application.reachability import ReachabilityService
from layer2.application.routing_service import RoutingService
from layer2.application.ranking import RankingConfig, eligible as ranking_eligible, order_route, rank_score
from layer2.application.slot_assembly import (
    LOCAL_SECRET_MAX_MEDIA_MENTIONS,
    LOCAL_SECRET_MIN_LOCAL_PERCENTAGE,
    AssembledSlot,
    SlotAssemblyService,
)
from layer2.application.transport_tagger import TransportTagger
from layer2.application.weather_scheduler import ScheduledSlot, WeatherScheduler
from layer2.domain.entities import (
    SLOT_COUNTS_FULL_DAY,
    SLOT_COUNTS_HALF_DAY,
    RecommendationQueue,
    RecommendationSlotItem,
    ScoredPlace,
    SlotRole,
    TransportEstimate,
    TransportMode,
)

# Budget headroom left unallocated to place costs during trimming, reserved
# for transport (auto/cab fares) which isn't known until after transport
# tagging runs (which happens after this trim, since transport depends on
# the final route order). 20% is a reasonable buffer for a Mangaluru-scale
# day; if real fare data later shows this is too tight/loose, only this
# constant needs to change.
BUDGET_TRANSPORT_HEADROOM = 0.20

# These roles form the day's narrative backbone (blueprint 5.3) and are
# never trimmed for budget — only Personal slots (including the Wildcard)
# are negotiable. If even the backbone alone exceeds budget, the day will
# come in over budget; that's a real constraint conflict, not a bug, and
# is surfaced via RecommendationQueue.total_estimated_cost vs profile.budget.
# TOURIST_PICK is protected for the same reason a hard override always
# should be: it's a place the tourist explicitly added themselves (see
# CustomPlaceService) — HIVE doesn't get to silently drop it for being
# over budget or failing a Hard Filter check any more than it gets to
# drop Signature or Anchor.
_BUDGET_PROTECTED_ROLES = {SlotRole.GROUNDING, SlotRole.SIGNATURE, SlotRole.ANCHOR, SlotRole.LOCAL_SECRET, SlotRole.TOURIST_PICK}

logger = logging.getLogger("groundzero.layer2.hive_engine")


class HiveEngine:
    def __init__(
        self,
        place_repository: PlaceRepository,
        hard_filters: HardFilterService,
        fit_score: PersonalFitScoreService,
        slot_assembly: SlotAssemblyService,
        weather_scheduler: WeatherScheduler,
        transport_tagger: TransportTagger,
        weather_collector: WeatherCollector,
        mangaluru_center: tuple[float, float] = (12.9141, 74.8560),
        reachability: ReachabilityService | None = None,
        routing_service: RoutingService | None = None,
        ranking: RankingConfig | None = None,
    ):
        self.place_repository = place_repository
        self.hard_filters = hard_filters
        self.fit_score = fit_score
        self.slot_assembly = slot_assembly
        self.weather_scheduler = weather_scheduler
        self.transport_tagger = transport_tagger
        self.weather_collector = weather_collector
        self.mangaluru_center = mangaluru_center
        self.reachability = reachability or ReachabilityService()
        # Optional: when given, real OSRM road-network routing is used
        # instead of transport_tagger's straight-line-only estimate (see
        # routing_service.py). Kept optional and separate from
        # transport_tagger — rather than replacing it — so existing tests
        # that construct HiveEngine with only a TransportTagger keep
        # passing unchanged with the previous (sync, haversine-only)
        # behavior; production wiring (api/dependencies.py) passes this.
        self.routing_service = routing_service
        # Ranking v2 (eligibility gate, evidence-based tie-break, geographic
        # route ordering). None = legacy behaviour, so tests that predate it
        # are unaffected; production wiring passes RankingConfig().
        self.ranking = ranking

    async def _estimate_transport(self, origin: Place, destination: Place) -> TransportEstimate:
        # Live OSRM can be slow or unreachable. A trip must never wait
        # minutes on it: cap each lookup, and after a failure skip live
        # routing for a cool-down so the rest of the itinerary uses the
        # local circuity-adjusted estimate (still a sensible number).
        if self.routing_service is not None and time.monotonic() >= getattr(self, "_routing_off_until", 0.0):
            try:
                return await asyncio.wait_for(self.routing_service.estimate(origin, destination), timeout=3.0)
            except Exception as exc:  # noqa: BLE001 - any routing failure => local estimate
                logger.warning("Live routing skipped (%s); using local estimate", exc.__class__.__name__)
                self._routing_off_until = time.monotonic() + 120.0
        return self.transport_tagger.estimate(origin, destination)

    async def _transit_minutes_between(
        self, assembled: list[AssembledSlot], places_by_id: dict[str, Place]
    ) -> list[int]:
        """Real travel time for each consecutive pair in `assembled`'s
        current order — the same estimate _build_items will show the
        tourist for that hop — so WeatherScheduler can space out clock
        times by how long the hop actually takes instead of a flat
        guess. See WeatherScheduler.schedule docstring."""
        minutes: list[int] = []
        for prev_slot, next_slot in zip(assembled, assembled[1:]):
            origin = places_by_id.get(prev_slot.scored_place.place_id)
            destination = places_by_id.get(next_slot.scored_place.place_id)
            if origin is None or destination is None:
                minutes.append(15)  # matches the old flat-gap fallback
                continue
            estimate = await self._estimate_transport(origin, destination)
            minutes.append(estimate.duration_minutes)
        return minutes

    async def _get_forecast(self) -> list[HourlyForecast]:
        try:
            lat, lon = self.mangaluru_center
            return await asyncio.wait_for(self.weather_collector.hourly_forecast(lat, lon), timeout=4.0)
        except (SourceUnavailable, asyncio.TimeoutError, Exception):
            # No forecast available this run -> weather scheduling becomes
            # a no-op (naive schedule only). Never fabricate a forecast.
            return []

    def _to_scored_place(self, place: Place, profile: TouristProfile, scheduled_hour: int,
                         origin: tuple[float, float] | None = None) -> ScoredPlace:
        breakdown = self.fit_score.score(place, profile, scheduled_hour=scheduled_hour)
        is_local_secret = (
            place.bias_signals.media_mentions <= LOCAL_SECRET_MAX_MEDIA_MENTIONS
            and place.bias_signals.local_percentage >= LOCAL_SECRET_MIN_LOCAL_PERCENTAGE
        )
        return ScoredPlace(
            place_id=place.id or "",
            name=place.name,
            category=place.category,
            raw_score=breakdown.raw_score,
            bias_index=breakdown.bias_index,
            personal_fit=breakdown.personal_fit,
            breakdown={
                "companion_score": breakdown.companion_score,
                "energy_score": breakdown.energy_score,
                "curiosity_score": breakdown.curiosity_score,
                "crowd_score": breakdown.crowd_score,
                "time_score": breakdown.time_score,
            },
            is_local_secret_eligible=is_local_secret,
            rank_score=(rank_score(breakdown.personal_fit, place, self.ranking, origin) if self.ranking else None),
        )

    def _reason_for(self, role: str, scored: ScoredPlace) -> str:
        if role == SlotRole.TOURIST_PICK.value:
            return "You added this place yourself — it's included no matter what HIVE would have scored it."
        top_component = max(scored.breakdown.items(), key=lambda kv: kv[1])[0]
        readable = {
            "companion_score": "matches your trip's purpose",
            "energy_score": "matches your current energy level",
            "curiosity_score": "matches what you said you're curious about",
            "crowd_score": "fits your crowd comfort level",
            "time_score": "well-timed for when you'll be there",
        }.get(top_component, "a strong overall fit")
        return f"Selected as {role}: {readable} (personal_fit={scored.personal_fit})"

    def _enforce_budget(self, assembled: list, places_by_id: dict, budget: float) -> list:
        """Trims Personal/Wildcard slots (lowest personal_fit first) until
        cumulative PLACE cost (transport not yet known at this point — see
        BUDGET_TRANSPORT_HEADROOM) fits within budget. Grounding, Signature,
        Anchor, and Local Secret are never trimmed — they're the day's
        narrative backbone, not negotiable line items."""
        budget_ceiling = budget * (1 - BUDGET_TRANSPORT_HEADROOM)

        protected = [s for s in assembled if s.role in _BUDGET_PROTECTED_ROLES]
        negotiable = [s for s in assembled if s.role not in _BUDGET_PROTECTED_ROLES]

        protected_cost = sum(
            places_by_id[s.scored_place.place_id].estimated_cost
            for s in protected if s.scored_place.place_id in places_by_id
        )

        # Keep negotiable slots highest personal_fit first, wildcards
        # de-prioritized slightly (they're the "trust me" experimental
        # picks — the first thing to cut if money's tight).
        negotiable_sorted = sorted(
            negotiable,
            key=lambda s: (s.scored_place.personal_fit - (0.05 if s.is_wildcard else 0.0)),
            reverse=True,
        )

        kept_negotiable = []
        running_cost = protected_cost
        for slot in negotiable_sorted:
            place = places_by_id.get(slot.scored_place.place_id)
            if place is None:
                continue
            if running_cost + place.estimated_cost <= budget_ceiling:
                running_cost += place.estimated_cost
                kept_negotiable.append(slot)
            # else: dropped — doesn't fit within the remaining budget headroom

        kept_ids = {s.scored_place.place_id for s in protected} | {s.scored_place.place_id for s in kept_negotiable}
        return [s for s in assembled if s.scored_place.place_id in kept_ids]

    async def _build_items(self, scheduled: list, places_by_id: dict) -> list[RecommendationSlotItem]:
        """Transport-tags a scheduled slot sequence into RecommendationSlotItems.
        Extracted as its own method because budget enforcement needs to
        call this repeatedly — removing a slot changes who's adjacent to
        whom, which changes transport costs, which can only be known by
        re-running this."""
        items: list[RecommendationSlotItem] = []
        prev_place: Place | None = None
        for scheduled_slot in scheduled:
            place = places_by_id.get(scheduled_slot.slot.scored_place.place_id)
            if place is None:
                continue

            travel_mode = TransportMode.WALK
            travel_time = 0
            travel_cost = 0.0
            travel_is_routed = False
            if prev_place is not None:
                transport = await self._estimate_transport(prev_place, place)
                travel_mode, travel_time, travel_cost = transport.mode, transport.duration_minutes, transport.cost_inr
                travel_is_routed = transport.is_routed

            item_cost = place.estimated_cost + travel_cost
            items.append(
                RecommendationSlotItem(
                    place_id=place.id or "",
                    place_name=place.name,
                    role=scheduled_slot.slot.role,
                    scheduled_time=scheduled_slot.scheduled_at,
                    travel_mode=travel_mode,
                    travel_time_minutes=travel_time,
                    travel_is_routed=travel_is_routed,
                    estimated_cost=item_cost,
                    reason_selected=self._reason_for(scheduled_slot.slot.role.value, scheduled_slot.slot.scored_place),
                    personal_score=scheduled_slot.slot.scored_place.personal_fit,
                    weather_adjusted=scheduled_slot.weather_adjusted,
                    weather_adjustment_note=scheduled_slot.weather_note,
                )
            )
            prev_place = place
        return items

    async def _enforce_budget_strict(self, scheduled: list, places_by_id: dict, budget: float) -> list:
        """Hard guarantee (unlike the pre-transport _enforce_budget, which
        is only an approximation since transport cost isn't known until
        after it runs): repeatedly drops the lowest personal_fit negotiable
        slot and re-tags transport for the resulting sequence, until the
        real total (place cost + real transport cost) fits budget or only
        protected backbone roles remain. Bounded to at most len(scheduled)
        iterations — trivial cost for a ≤13-slot day."""
        current = list(scheduled)
        for _ in range(len(scheduled) + 1):
            items = await self._build_items(current, places_by_id)
            total = sum(item.estimated_cost for item in items)
            if total <= budget:
                return current

            negotiable = [s for s in current if s.slot.role not in _BUDGET_PROTECTED_ROLES]
            if not negotiable:
                return current  # backbone alone exceeds budget — nothing left to trim, see docstring

            worst = min(
                negotiable,
                key=lambda s: s.slot.scored_place.personal_fit - (0.05 if s.slot.is_wildcard else 0.0),
            )
            current = [s for s in current if s is not worst]

        return current

    def _revalidate_opening_hours(
        self,
        scheduled: list,
        places_by_id: dict,
        scored: list[ScoredPlace],
        used_ids: set[str],
    ) -> tuple[list, int]:
        """Root cause of "recommended a place that's actually closed by the
        time you'd get there": Hard Filters only ever check openness once,
        against the trip's single start_time (see build_recommendation_queue),
        before the weather scheduler assigns each slot's real scheduled_at.
        A full-day plan spans many hours — something open at a 9am start
        can easily be scheduled, correctly by every other rule, into a
        6pm slot it's actually closed for. This runs AFTER scheduling, so
        every slot gets checked against its own real time. A closed slot
        is first swapped for the best still-unused candidate of the same
        category that IS open at that time (same substitution spirit as
        the Replan Trigger / weather pre-shift — fix it silently, don't
        just show the tourist a broken plan); if nothing else qualifies,
        the slot is dropped rather than shown as a bad recommendation.
        Returns (revalidated_scheduled, dropped_count) — dropped_count
        feeds the slots_requested vs slots_filled diagnostic."""
        by_category: dict[str, list[ScoredPlace]] = {}
        for sp in scored:
            by_category.setdefault(sp.category, []).append(sp)

        result = []
        dropped = 0
        for scheduled_slot in scheduled:
            place = places_by_id.get(scheduled_slot.slot.scored_place.place_id)
            if place is None or self.hard_filters.is_open_at(place, scheduled_slot.scheduled_at):
                result.append(scheduled_slot)
                continue

            replacement = None
            for candidate in sorted(
                by_category.get(place.category, []), key=lambda c: c.personal_fit, reverse=True
            ):
                if candidate.place_id in used_ids:
                    continue
                candidate_place = places_by_id.get(candidate.place_id)
                if candidate_place is None:
                    continue
                if self.hard_filters.is_open_at(candidate_place, scheduled_slot.scheduled_at):
                    replacement = candidate
                    break

            if replacement is None:
                dropped += 1
                continue

            used_ids.add(replacement.place_id)
            new_slot = AssembledSlot(
                role=scheduled_slot.slot.role, scored_place=replacement, is_wildcard=scheduled_slot.slot.is_wildcard,
            )
            result.append(
                ScheduledSlot(
                    slot=new_slot, scheduled_at=scheduled_slot.scheduled_at,
                    weather_adjusted=scheduled_slot.weather_adjusted,
                    weather_note=(scheduled_slot.weather_note or "") + " (swapped: original was closed at this time)",
                )
            )

        return result, dropped

    async def build_recommendation_queue(
        self,
        profile: TouristProfile,
        start_time: datetime,
        pinned_place_ids: list[str] | None = None,
        start_latitude: float | None = None,
        start_longitude: float | None = None,
    ) -> RecommendationQueue:
        """start_latitude/start_longitude: the tourist's real position when
        they open the app to start the trip (blueprint's "as the tourist
        switches on the app" moment). When given, HIVE only considers
        places within a reachable radius of that point — a real geofence
        around the TOURIST, not the per-place proximity trigger in
        layer5/geofencing.py. The radius starts fixed by trip_duration_hours
        and widens automatically if the immediate area is too sparse (see
        reachability.py) — "fixed yet adjustable" per spec. Optional and
        backward-compatible: omitted (None), the full Master Data Core is
        considered exactly as before.

        pinned_place_ids: places the tourist explicitly added themselves
        (via CustomPlaceService — search-a-map-pin or type-a-name-and-note)
        that HIVE didn't recommend. These are forced into the queue as a
        protected TOURIST_PICK slot each — bypassing Hard Filters (closed,
        over budget, accessibility mismatch, whatever) and budget trimming,
        because the tourist chose them, not HIVE. They still get scheduled
        into the day's time sequence and transport-tagged like every other
        slot, so "added" genuinely means "you'll be taken there," not just
        "noted somewhere.\""""
        pinned_place_ids = pinned_place_ids or []
        all_places = await self.place_repository.list_all()

        # Pull pinned places out before Hard Filters/scoring runs on the
        # general candidate pool — they're handled on their own track
        # below so a Hard Filter (or simply not being the top scorer)
        # can never silently exclude something the tourist asked for by
        # name, and so they don't also get double-picked as an ordinary
        # Personal slot.
        pinned_ids_set = set(pinned_place_ids)
        pinned_places = [p for p in all_places if p.id in pinned_ids_set]
        # SECURITY FIX (final-release-hardening pass, Oct 2026): a
        # tourist-added place starts verification_status="pending" (see
        # CustomPlaceService.add_or_find) until an admin reviews it — the
        # general candidate pool, which gets recommended to EVERY
        # tourist, must never include one. Pinned places are exempt from
        # this same as they're exempt from Hard Filters/reachability
        # below: pinned_places is sliced out of all_places (unfiltered)
        # above, so the tourist who just added a pending place of their
        # own still gets taken there — this filter only stops it from
        # also being silently recommended to everyone else.
        candidate_pool = [
            p for p in all_places
            if p.id not in pinned_ids_set and p.verification_status == "verified"
        ]

        # Reachability geofence — restrict the candidate pool to what's
        # actually reachable from where the tourist is standing right now,
        # before any scoring happens. Pinned (TOURIST_PICK) places are
        # deliberately exempt, same reasoning as Hard Filters below: the
        # tourist chose them by name, distance isn't HIVE's call to make.
        geofence_radius_km: float | None = None
        if start_latitude is not None and start_longitude is not None:
            reach_result = self.reachability.filter_by_radius(
                candidate_pool, start_latitude, start_longitude, profile.trip_duration_hours
            )
            candidate_pool = reach_result.places
            geofence_radius_km = reach_result.radius_km_used

        # Hard Filters
        remaining_budget = profile.budget
        survivors = self.hard_filters.filter_candidates(candidate_pool, profile, start_time, remaining_budget)

        # Personal Fit Score (scored at the tourist's stated start hour;
        # slots get their real per-slot hour once scheduled below)
        start_hour = start_time.hour
        origin = (start_latitude, start_longitude) if start_latitude is not None and start_longitude is not None else None
        if self.ranking:
            survivors = ranking_eligible(survivors, self.ranking)
        scored = [self._to_scored_place(p, profile, start_hour, origin) for p in survivors]
        places_by_id = {p.id: p for p in survivors if p.id}

        # Slot assembly (role-ordered sequence)
        assembled = self.slot_assembly.assemble(scored, places_by_id, profile.trip_duration_hours)

        # Tourist-picked places: scored too (so the queue can still show a
        # personal_fit / reason, for transparency), but always kept
        # regardless of that score, and always added to places_by_id so
        # every downstream step (budget, weather, transport) treats them
        # like a real slot rather than a special case that needs its own
        # branch everywhere.
        for place in pinned_places:
            if not place.id:
                continue
            places_by_id[place.id] = place
            scored_pinned = self._to_scored_place(place, profile, start_hour)
            assembled.append(AssembledSlot(role=SlotRole.TOURIST_PICK, scored_place=scored_pinned))

        # Budget enforcement, pass 1 (approximation, place cost only — see
        # BUDGET_TRANSPORT_HEADROOM docstring): trims the obviously-over-
        # budget slots before spending effort on weather/transport for them.
        # TOURIST_PICK is in _BUDGET_PROTECTED_ROLES, so pinned places are
        # never touched by this — only ordinary Personal slots flex to
        # make room for them.
        assembled = self._enforce_budget(assembled, places_by_id, profile.budget)
        if self.ranking:
            assembled = order_route(assembled, places_by_id, start_time, self.ranking, origin)

        # Weather scheduling (see module docstring re: pipeline order).
        # Real per-hop transit time is computed up front — via the same
        # routing_service/TransportTagger estimate ultimately shown to the
        # tourist for that hop in _build_items — so the clock time given
        # for a stop reflects how long it actually takes to get there,
        # not a flat placeholder unrelated to the real distance.
        forecast = await self._get_forecast()
        transit_minutes = await self._transit_minutes_between(assembled, places_by_id)
        scheduled = self.weather_scheduler.schedule(
            assembled, places_by_id, start_time, forecast, transit_minutes=transit_minutes,
        )
        if len(scheduled) < len(assembled):
            logger.info(
                "profile %s: %d slot(s) dropped for running past a sane same-day schedule window "
                "(see weather_scheduler.py)",
                profile.id, len(assembled) - len(scheduled),
            )

        # Opening-hours re-validation (see _revalidate_opening_hours
        # docstring): the Hard Filters pass above only checked openness
        # once, at start_time — now that every slot has its own real
        # scheduled_at, re-check each one against ITS time, swap or drop
        # anything that would actually be closed by then.
        used_ids = {s.slot.scored_place.place_id for s in scheduled} | {p.id for p in pinned_places if p.id}
        scheduled, opening_hours_dropped = self._revalidate_opening_hours(scheduled, places_by_id, scored, used_ids)

        # Budget enforcement, pass 2 (strict, real transport cost included)
        scheduled = await self._enforce_budget_strict(scheduled, places_by_id, profile.budget)

        # Transport tagging + Recommendation Queue assembly
        items = await self._build_items(scheduled, places_by_id)
        total_cost = sum(item.estimated_cost for item in items)

        # Slot-shortfall diagnostics (blueprint's 5-role table target vs.
        # what actually made it into the final queue). Previously silent —
        # an 8-of-13 itinerary looked identical in the API response to a
        # deliberately-scaled half-day plan, with nothing to tell them
        # apart. non-TOURIST_PICK count is what's comparable to the target,
        # since pinned places are tourist-added extras on top of it.
        role_counts = SLOT_COUNTS_HALF_DAY if profile.trip_duration_hours == TripDuration.HALF_DAY else SLOT_COUNTS_FULL_DAY
        slots_requested = sum(role_counts.values())
        slots_filled = sum(1 for i in items if i.role != SlotRole.TOURIST_PICK)
        if slots_filled < slots_requested:
            logger.warning(
                "profile %s: itinerary filled %d/%d slots (%d dropped for being closed at scheduled time) — "
                "likely a thin candidate pool for this profile's category/role mix, see slot_assembly.py",
                profile.id, slots_filled, slots_requested, opening_hours_dropped,
            )

        return RecommendationQueue(
            profile_id=profile.id or "",
            items=items,
            total_estimated_cost=round(total_cost, 2),
            generated_at=datetime.now(start_time.tzinfo),
            geofence_radius_km=geofence_radius_km,
            slots_requested=slots_requested,
            slots_filled=slots_filled,
            slots_dropped_closed=opening_hours_dropped,
        )

    async def build_multi_day_recommendation_queue(
        self,
        profile: TouristProfile,
        start_time: datetime,
        pinned_place_ids: list[str] | None = None,
        start_latitude: float | None = None,
        start_longitude: float | None = None,
    ) -> list[RecommendationQueue]:
        """Blueprint Q8/TouristProfile.multi_day_count support — previously
        unimplemented (the field existed on the domain model since Layer 1
        was built, but nothing in Layer 2 ever consumed it; every call
        produced exactly one day regardless of trip_duration_hours).

        Generates one RecommendationQueue per day. Each day excludes every
        place used on an earlier day of THIS trip (reusing the
        return_visitor_exclusions mechanism, which Hard Filters already
        enforces) — day 2 won't repeat day 1's Signature pick. Each day
        gets the profile's stated budget independently (budget is
        documented as "per day" on TouristProfile), not the total split
        across days.

        pinned_place_ids are only ever pinned into Day 1 — a tourist-added
        place is a specific place they want to visit once, not every day
        of the trip. It's still automatically excluded from later days via
        the same used_place_ids mechanism as any other visited place.

        Falls back to a single day if trip_duration_hours isn't MULTI_DAY,
        so callers can treat this as the general entry point.
        """
        if profile.trip_duration_hours != TripDuration.MULTI_DAY:
            return [await self.build_recommendation_queue(
                profile, start_time, pinned_place_ids,
                start_latitude=start_latitude, start_longitude=start_longitude,
            )]

        day_count = profile.multi_day_count or 1
        queues: list[RecommendationQueue] = []
        used_place_ids: set[str] = set(profile.return_visitor_exclusions)

        for day_index in range(day_count):
            day_start = start_time + timedelta(days=day_index)
            day_profile = replace(profile, return_visitor_exclusions=list(used_place_ids))
            day_pins = pinned_place_ids if day_index == 0 else None
            # Day 1's geofence center is the tourist's real position; later
            # days reuse it as a reasonable anchor (same city, same hotel
            # area) rather than dropping the radius filter entirely — a
            # future Layer 4B "resume at day start" flow (blueprint 9.5)
            # is the natural place to refresh this per day once it exists.
            queue = await self.build_recommendation_queue(
                day_profile, day_start, day_pins,
                start_latitude=start_latitude, start_longitude=start_longitude,
            )
            used_place_ids.update(item.place_id for item in queue.items if item.place_id)
            queues.append(queue)

        return queues
