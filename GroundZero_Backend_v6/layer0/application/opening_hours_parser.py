"""
OSM `opening_hours` tag parser (blueprint field: `days_open`, `opens_at`,
`closes_at`). Previously, ONLY the raw OSM string was ever stored — these
structured fields existed in the schema and were never populated by any
code path, meaning the Hard Filter's "closed places" check could never
actually trigger (see `layer2/application/hard_filters.py`). Fixed by
using `opening-hours-py`, a real, actively-maintained parser for the OSM
opening_hours micro-syntax (https://pypi.org/project/opening-hours-py/),
rather than hand-rolling a parser for a notoriously fiddly grammar.

Two things are provided:
  - `parse()`: a best-effort summary into the existing simple schema
    (days_open/opens_at/closes_at) — necessarily lossy for complex
    schedules (e.g. different hours on different days), since that schema
    only has room for one window. Documented as such below.
  - `is_open_at()`: the ACCURATE check, used by Hard Filters instead of
    the lossy summary fields — re-parses the raw string and asks the
    library directly whether the place is open at a specific moment, so
    complex real-world schedules (weekday/weekend splits, holiday
    exceptions, etc.) are handled correctly rather than approximated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import opening_hours

logger = logging.getLogger("groundzero.layer0.opening_hours_parser")

_WEEKDAY_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# All Ground Zero places are in Mangaluru — OSM opening_hours schedules
# are inherently local time, so any moment we check needs to be in this
# zone, not UTC. Also a hard compatibility requirement: the opening_hours
# library's Rust bindings reject datetime.timezone.utc outright (raises
# TypeError — confirmed directly) and only accept naive datetimes or
# zoneinfo.ZoneInfo-based tzinfo.
_MANGALURU_TZ = ZoneInfo("Asia/Kolkata")

# A fixed, arbitrary Monday used purely as the anchor for asking "what
# does a representative week look like" — OSM opening_hours schedules are
# usually week-periodic (holiday/seasonal exceptions aside), so any Monday
# works for extracting the summary fields.
_REFERENCE_MONDAY = datetime(2024, 1, 1)  # a real Monday


@dataclass(frozen=True)
class ParsedOpeningHours:
    days_open: list[str]
    opens_at: Optional[str]  # "HH:MM", best-effort single window start
    closes_at: Optional[str]  # "HH:MM", best-effort single window end
    parse_succeeded: bool


class OpeningHoursParser:
    def parse(self, raw: str) -> ParsedOpeningHours:
        """Best-effort summary for the simple days_open/opens_at/closes_at
        schema fields. LOSSY for schedules with different hours on
        different days (e.g. "Mo-Fr 08:00-20:00; Sa 09:00-13:00") — takes
        the FIRST open window found in a representative week as the
        summary opens_at/closes_at, while days_open still correctly lists
        every day that has *some* open window. The raw string always
        remains available on OpeningHours.raw for anything needing the
        full schedule; Hard Filters use is_open_at() below instead of
        these summary fields for exactly this reason."""
        if not raw or not raw.strip():
            return ParsedOpeningHours(days_open=[], opens_at=None, closes_at=None, parse_succeeded=False)

        try:
            oh = opening_hours.OpeningHours(raw)
        except Exception as exc:  # noqa: BLE001 — the OSM syntax corpus has real malformed entries
            logger.debug("Failed to parse opening_hours %r: %s", raw, exc)
            return ParsedOpeningHours(days_open=[], opens_at=None, closes_at=None, parse_succeeded=False)

        start = _REFERENCE_MONDAY
        days_open: set[str] = set()
        first_window: tuple[str, str] | None = None

        # Query one day at a time rather than the whole week in one
        # intervals() call. A single call spanning >24h lets a continuous
        # block (e.g. "24/7", or "Mo-Fr 00:00-24:00") produce ONE interval
        # that crosses day boundaries without being split — confirmed by
        # live-testing this exact case: "24/7" initially came back as
        # days=['mon'] only, opens=00:00 closes=00:00 (the time-of-day
        # component of a start/end that were actually a week apart).
        # Per-day querying sidesteps this entirely.
        for day_offset in range(7):
            day_start = start + timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)
            try:
                day_intervals = list(oh.intervals(day_start, day_end))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to evaluate intervals for opening_hours %r: %s", raw, exc)
                return ParsedOpeningHours(days_open=[], opens_at=None, closes_at=None, parse_succeeded=False)

            for interval_start, interval_end, state, _comment in day_intervals:
                if state != opening_hours.State.OPEN:
                    continue
                days_open.add(_WEEKDAY_ABBR[day_offset])
                if first_window is None:
                    # Clamp to this day's boundaries so a window that
                    # actually continues into the next day (overnight
                    # hours) still reports a sensible same-day closes_at
                    # for the summary fields; the raw string remains the
                    # source of truth for exact overnight behavior.
                    window_end = min(interval_end, day_end)
                    first_window = (interval_start.strftime("%H:%M"), window_end.strftime("%H:%M"))

        ordered_days = [d for d in _WEEKDAY_ABBR if d in days_open]
        opens_at, closes_at = first_window if first_window else (None, None)
        if opens_at == "00:00" and closes_at == "00:00":
            # A window clamped to exactly the day's boundaries (e.g. "24/7"
            # or "00:00-24:00") reads as zero-width/never-open if shown
            # literally — it's actually open the entire day. 23:59 is an
            # honest, non-misleading approximation for the summary display
            # fields; the raw string is still the source of truth.
            closes_at = "23:59"

        return ParsedOpeningHours(
            days_open=ordered_days, opens_at=opens_at, closes_at=closes_at, parse_succeeded=True
        )

    def is_open_at(self, raw: str, moment: datetime) -> Optional[bool]:
        """The accurate check. Returns None (unknown) rather than guessing
        if the string is empty or unparseable — callers should treat
        None as 'don't exclude on this signal,' matching the existing
        Hard Filter convention for unknown hours."""
        if not raw or not raw.strip():
            return None
        try:
            oh = opening_hours.OpeningHours(raw)
            # Convert to Mangaluru local time — see _MANGALURU_TZ above for
            # why this is required (both a library compatibility issue and
            # a correctness one: OSM hours are local time).
            if moment.tzinfo is not None:
                local_moment = moment.astimezone(_MANGALURU_TZ)
            else:
                local_moment = moment.replace(tzinfo=_MANGALURU_TZ)
            return bool(oh.is_open(local_moment))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to evaluate is_open for opening_hours %r: %s", raw, exc)
            return None
