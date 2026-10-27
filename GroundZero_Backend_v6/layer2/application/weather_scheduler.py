"""
Weather Engine (blueprint 5.4 + Table 3 Q9 note: "weather pre-shift").
Integrates the Layer 0 WeatherCollector's hourly forecast to reorder
assembled slots: outdoor slots move away from forecast rain windows,
indoor-friendly slots get promoted into those windows instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from layer0.domain.entities import Place
from layer0.infrastructure.collectors.weather_collector import HourlyForecast
from layer2.application.slot_assembly import AssembledSlot
from layer2.domain.entities import SlotRole


@dataclass(frozen=True)
class ScheduledSlot:
    slot: AssembledSlot
    scheduled_at: datetime
    weather_adjusted: bool
    weather_note: str | None


# Bug fixed: nothing here ever checked elapsed time at all. The naive
# scheduler just kept stacking dwell + transit for every assembled slot
# regardless of how many there were, so a 12-stop day with several long
# cab hops could (and did, in a real run — 11:44am to 12:47am) schedule
# stops into the next calendar day for a trip the tourist asked to be
# one day. Note this is deliberately NOT "must fit within
# trip_duration_hours" — a full-day plan is genuinely allowed to run
# to, say, 9 or 10pm (13 stops at realistic dwell+transit times
# routinely do, and the existing full-day slot counts in
# layer2/domain/entities.py assume that's fine); the actual invariant
# being enforced is narrower and non-negotiable: a one-day trip never
# schedules a stop that reads as "tomorrow." same_day_cutoff_hour is
# the latest clock hour (24h, local to start_time) a NEW stop may still
# be scheduled at — after that, only protected backbone slots keep
# their place; ordinary trailing Personal slots are dropped instead of
# rolling into the small hours or past midnight.
_TIME_PROTECTED_ROLES = {
    SlotRole.GROUNDING, SlotRole.SIGNATURE, SlotRole.ANCHOR,
    SlotRole.LOCAL_SECRET, SlotRole.TOURIST_PICK,
}
DEFAULT_SAME_DAY_CUTOFF_HOUR = 23  # 11pm — generous, but never "tomorrow"


class WeatherScheduler:
    # Fallback only used when transit_minutes isn't supplied (e.g. older
    # callers/tests) — kept purely for backward compatibility. Previously
    # this flat 15 minutes was standing in for BOTH real travel time AND
    # a settle/parking buffer, which is why displayed clock times could
    # drift arbitrarily far from the transport time shown for the same
    # hop (blueprint 5.5's transport tagging ran independently of this
    # schedule and never fed back into it). transit_minutes below closes
    # that gap; SETTLE_BUFFER_MINUTES is the small, separate allowance
    # this flat constant used to also cover.
    SETTLE_BUFFER_MINUTES = 5

    def schedule(
        self,
        slots: list[AssembledSlot],
        places_by_id: dict[str, Place],
        start_time: datetime,
        forecast: list[HourlyForecast],
        dwell_gap_minutes: int = 15,
        transit_minutes: list[int] | None = None,
        enforce_same_day: bool = True,
        same_day_cutoff_hour: int = DEFAULT_SAME_DAY_CUTOFF_HOUR,
    ) -> list[ScheduledSlot]:
        """transit_minutes[i], when given, is the real travel time (from
        TransportTagger/routing_service — the same estimate shown to the
        tourist for that hop) from slot i to slot i+1, so the clock time
        shown for a stop actually reflects how long it takes to get
        there, not a flat placeholder. len(transit_minutes) must be
        len(slots) - 1. Omit it (or pass None) to keep the previous flat-
        gap behavior, e.g. for a caller with no transport estimator.

        enforce_same_day (on by default): trailing, non-protected slots
        that would only fit at or after same_day_cutoff_hour, OR on a
        later calendar date than start_time, are dropped rather than
        scheduled into the night or the next day. Protected backbone
        roles (see _TIME_PROTECTED_ROLES) are always kept regardless."""
        rain_hours = {f.timestamp.hour for f in forecast if f.is_rain}

        # First pass: naive sequential scheduling by current slot order
        naive_schedule: list[tuple[AssembledSlot, datetime]] = []
        cursor = start_time
        for i, slot in enumerate(slots):
            place = places_by_id.get(slot.scored_place.place_id)
            dwell = place.dwell_time_typical_minutes if place else 45
            naive_schedule.append((slot, cursor))
            if transit_minutes is not None and i < len(transit_minutes):
                gap = transit_minutes[i] + self.SETTLE_BUFFER_MINUTES
            else:
                gap = dwell_gap_minutes
            cursor = cursor + timedelta(minutes=dwell + gap)

        # Same-day cap: drop trailing, non-protected slots that only fit
        # after a sane same-day cutoff or that spilled onto a later
        # calendar date. Filtered post-hoc (not during the walk above) so
        # dwell/gap accumulation stays a single, simple pass — a known,
        # documented edge case is that a protected slot kept past the cap
        # can still show a later time than the cap, because the walk
        # above still counted time spent on whatever was dropped ahead
        # of it.
        if enforce_same_day:
            same_day_end = start_time.replace(
                hour=same_day_cutoff_hour, minute=0, second=0, microsecond=0
            )
            naive_schedule = [
                (slot, t) for slot, t in naive_schedule
                if (t.date() == start_time.date() and t < same_day_end)
                or slot.role in _TIME_PROTECTED_ROLES
            ]

        if not rain_hours:
            return [ScheduledSlot(slot=s, scheduled_at=t, weather_adjusted=False, weather_note=None) for s, t in naive_schedule]

        # Second pass: swap outdoor slots landing in a rain hour with the
        # nearest indoor-eligible slot scheduled outside a rain hour.
        outdoor_in_rain = [
            i for i, (s, t) in enumerate(naive_schedule)
            if places_by_id.get(s.scored_place.place_id) and places_by_id[s.scored_place.place_id].is_outdoor()
            and t.hour in rain_hours
        ]
        indoor_clear = [
            i for i, (s, t) in enumerate(naive_schedule)
            if places_by_id.get(s.scored_place.place_id)
            and not places_by_id[s.scored_place.place_id].is_outdoor()
            and t.hour not in rain_hours
        ]

        adjusted_indices: set[int] = set()
        for outdoor_idx in outdoor_in_rain:
            if not indoor_clear:
                break
            swap_idx = indoor_clear.pop(0)
            naive_schedule[outdoor_idx], naive_schedule[swap_idx] = (
                naive_schedule[swap_idx],
                naive_schedule[outdoor_idx],
            )
            adjusted_indices.update({outdoor_idx, swap_idx})

        result = []
        for i, (slot, t) in enumerate(naive_schedule):
            adjusted = i in adjusted_indices
            note = "rescheduled around forecast rain" if adjusted else None
            result.append(ScheduledSlot(slot=slot, scheduled_at=t, weather_adjusted=adjusted, weather_note=note))
        return result
