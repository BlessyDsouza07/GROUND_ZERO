"""Explore's application service. Composes:
  - layer0 PlaceRepository (place data + tags — unchanged)
  - layer1 CuriosityExtractor / TouristProfile (unchanged — a mood
    becomes a synthetic, lightweight TouristProfile instead of a full
    9-question survey, so a signed-out tourist gets real personal-fit
    reasoning without ever being forced through the survey)
  - layer2 PersonalFitScoreService (unchanged — exact same formula/
    weights chunk 2 uses, see FitBreakdown)
  - layer0 OpeningHoursParser + FreshnessService (unchanged — "is this
    place actually open/current right now")
  - explore/context_service.py (new, this chunk) for weather/tide/sunset
  - live_events' own DB (unchanged service, read directly here)

Nothing here re-implements ranking, bias, or weather/tide logic that
already exists elsewhere in this backend.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from layer0.application.freshness import FreshnessService
from layer0.application.opening_hours_parser import OpeningHoursParser
from explore.hours import EAT, STAY, TRANSIT, open_info
from layer0.domain.entities import CrowdLevel, Place
from layer0.domain.repositories import PlaceRepository
from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.domain.entities import (
    CrowdTolerance,
    CuriosityVector,
    EnergyBand,
    GroupConfig,
    Purpose,
    StartTimePreference,
    TouristProfile,
    TripDuration,
)
from layer2.application.personal_fit_score import FitBreakdown, PersonalFitScoreService

from .context_service import ExploreContextService, RightNow
from .mood_profiles import EXPERIENCE_CATEGORIES, MOOD_LABELS, MOOD_TAG_WEIGHTS, MOOD_TAGLINES

_OUTDOOR_TAGS = {"beach", "park", "garden", "viewpoint", "lake", "trail"}
_SUNSET_BEST_TIMES = {"sunset", "evening"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _mood_profile(mood: str, now_hour: int) -> TouristProfile:
    """A mood is not a full Soul Survey — it's a deliberately lightweight
    stand-in so a signed-out tourist gets real Personal Fit reasoning
    (not a fabricated score) without the 9-question survey. Energy/crowd
    defaults below are the mood's own character, not guesses about a
    specific person."""
    weights = MOOD_TAG_WEIGHTS.get(mood, {})
    low_key = {"slow", "quiet", "nature"}
    high_key = {"adventure"}
    energy = EnergyBand.LOW if mood in low_key else (EnergyBand.HIGH if mood in high_key else EnergyBand.MODERATE)
    crowd = CrowdTolerance.PREFER_QUIET if mood in {"slow", "quiet"} else CrowdTolerance.FINE
    return TouristProfile(
        id=None,
        purpose=Purpose.UNDECIDED,
        energy_band=energy,
        crowd_tolerance=crowd,
        budget=100000.0,  # Explore has no real budget constraint pre-trip; Personal Fit Score doesn't use it anyway
        group_config=GroupConfig.SOLO,
        curiosity_vector=CuriosityVector(weights=dict(weights)),
        trip_duration_hours=TripDuration.FULL_DAY,
        start_time_preference=StartTimePreference.FLEXIBLE,
    )


# Things that are useful but are not "experiences": never shown in the
# experience rows, however their tags happen to match.
NOT_EXPERIENCES = {"lodging", "transit_point", "bus_stand", "railway", "pharmacy", "fire_station", "ev_charger", "uncategorized", "hospital", "atm", "fuel"}

# Global chains are not "local life" or "hidden" finds. They stay searchable.
CHAIN_NAMES = ("domino", "kfc", "mcdonald", "pizza hut", "subway", "burger king", "starbucks", "cafe coffee day",
               "baskin", "dunkin", "haldiram", "wow! momo", "wow momo", "faasos", "box8", "bata ", "reliance", "d mart", "dmart")


def _is_chain(name: str) -> bool:
    n = (name or "").lower()
    return any(c in n for c in CHAIN_NAMES)


@dataclass
class ExploreService:
    place_repository: PlaceRepository
    fit_score: PersonalFitScoreService
    context_service: ExploreContextService
    opening_hours_parser: OpeningHoursParser
    freshness_service: FreshnessService
    mangaluru_center: tuple[float, float]

    # ---- shared helpers -------------------------------------------------

    async def _candidates(self, lat: Optional[float], lon: Optional[float]) -> tuple[list[Place], float, float]:
        center_lat = lat if lat is not None else self.mangaluru_center[0]
        center_lon = lon if lon is not None else self.mangaluru_center[1]
        places = await self.place_repository.list_all()
        now = datetime.now(timezone.utc)
        survivors = [
            p for p in places
            if not p.temporarily_unavailable
            and self.freshness_service.is_fresh_enough(p, 0.2, now=now)
        ]
        return survivors, center_lat, center_lon

    def _open(self, place: Place):
        return open_info(place, self.opening_hours_parser)

    def _is_open_now(self, place: Place) -> Optional[bool]:
        st = self._open(place).state
        return True if st == "open" else (False if st == "closed" else None)

    def _recommendable(self, places: list[Place], night_strict: bool = True) -> list[Place]:
        """Drop what is closed right now. After 9 pm also drop places whose
        hours we know nothing about, rather than sending someone to a locked gate."""
        hour = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).hour
        late = hour >= 21 or hour < 5
        out = []
        junk = ("pharmacy", "charging", "fire station", "petrol", "atm", "police", "hospital", "clinic", "bank")
        for p in places:
            if p.category == "uncategorized" or any(j in (p.name or "").lower() for j in junk):
                continue
            info = self._open(p)
            if info.state == "closed":
                continue
            if info.state == "unknown" and late and night_strict:
                continue
            out.append(p)
        return out

    def _why_now(self, place: Place, right_now: RightNow) -> tuple[str, list[str]]:
        reasons: list[str] = []
        headline = "GOOD TO VISIT NOW"

        is_outdoor = place.is_outdoor() or bool(_OUTDOOR_TAGS & set(place.tags))
        if (place.best_time in _SUNSET_BEST_TIMES or is_outdoor) and 0 < right_now.minutes_to_sunset <= 90:
            headline = f"SUNSET IN {right_now.minutes_to_sunset} MINUTES"
            reasons.append("Good light for photos as the sun gets lower")
        elif is_outdoor and right_now.weather_available and right_now.is_rain:
            headline = "RAIN NEARBY RIGHT NOW"
            reasons.append("This is an outdoor spot — conditions may not be ideal")
        elif is_outdoor and right_now.weather_available and not right_now.is_rain:
            reasons.append("Clear conditions right now")

        if place.tide_dependency and right_now.tide_available:
            reasons.append(f"Tide is currently {right_now.tide_state}")

        if place.crowd_level in (CrowdLevel.LOW,):
            reasons.append("Lower crowd than most listed places")

        info = self._open(place)
        if info.state == "open":
            reasons.append("Open now" if info.source == "listed" else info.label)
        elif info.state == "closed":
            reasons.append(info.label + " — check before you go")

        if not reasons:
            reasons.append(f"Fits the current time of day ({right_now.now_local.strftime('%H:%M')})")
        return headline, reasons

    def _provenance(self, place: Place) -> str:
        from layer0.domain.entities import DataSource

        return "community" if DataSource.COMMUNITY_SUBMISSION in place.source or DataSource.TOURIST_ADDED in place.source else "verified"

    def _card(self, place: Place, right_now: RightNow, center_lat: float, center_lon: float) -> dict:
        headline, reasons = self._why_now(place, right_now)
        return dict(
            place_id=place.id or "",
            name=place.name,
            category=place.category,
            tags=place.tags,
            latitude=place.coordinates.latitude,
            longitude=place.coordinates.longitude,
            price_band=place.price_band.value,
            estimated_cost=place.estimated_cost,
            dwell_minutes=place.dwell_time_typical_minutes,
            crowd_level=place.crowd_level.value,
            best_time=place.best_time,
            grade=place.grade.value if place.grade else None,
            media_mentions=place.bias_signals.media_mentions,
            provenance=self._provenance(place),
            image_url=None,  # see README_EXPLORE.md — no real photo field exists in this dataset yet
            distance_km=round(haversine_km(center_lat, center_lon, place.coordinates.latitude, place.coordinates.longitude), 2),
            why_now=dict(headline=headline, reasons=reasons),
            open_state=(info := self._open(place)).state,
            open_label=info.label,
            open_source=info.source,
        )

    # ---- "right now" context --------------------------------------------

    async def right_now(self, lat: Optional[float], lon: Optional[float], events_today_count: Optional[int]) -> dict:
        center_lat = lat if lat is not None else self.mangaluru_center[0]
        center_lon = lon if lon is not None else self.mangaluru_center[1]
        rn = await self.context_service.right_now(center_lat, center_lon, events_today_count)

        hour = rn.now_local.hour
        if rn.minutes_to_sunset > 0 and rn.minutes_to_sunset <= 60:
            headline = "SUNSET IS GETTING CLOSE"
        elif hour < 11:
            headline = "A GOOD MORNING IN MANGALURU"
        elif hour < 17:
            headline = "YOU HAVE THE AFTERNOON"
        elif rn.minutes_to_sunset > 0:
            headline = "SUNSET IS GETTING CLOSE"
        else:
            headline = "MANGALURU AFTER DARK"

        weather_note = None
        if rn.weather_available and rn.is_rain:
            weather_note = "Rain moving in — maybe skip the exposed coast. Try indoor culture, food, or heritage instead."
        elif rn.weather_available and rn.condition == "Clear":
            weather_note = "Clearing, good conditions to be outside — coast, nature, or a sunset spot."

        tide_note = None
        if rn.tide_available:
            if rn.tide_state == "rising":
                tide_note = "Tide rising — good conditions for a waterfront walk or photography."
            elif rn.tide_state == "falling":
                tide_note = "Tide falling — more of the shore is exposed right now."

        return dict(
            headline=headline,
            now_local=rn.now_local.isoformat(),
            weather_available=rn.weather_available,
            temperature_celsius=rn.temperature_celsius,
            condition=rn.condition,
            is_rain=rn.is_rain,
            tide_available=rn.tide_available,
            tide_state=rn.tide_state,
            tide_source=rn.tide_source,
            sunset_local=rn.sunset_local.isoformat(),
            minutes_to_sunset=rn.minutes_to_sunset,
            events_today_count=rn.events_today_count,
            weather_note=weather_note,
            tide_note=tide_note,
        )


    # ---- "Where am I, what do I need?" ---------------------------------------

    async def situation(self, lat: float, lon: float, approx: bool = False, accuracy: Optional[float] = None) -> dict:
        """Reads the person's surroundings from their real coordinates and
        the clock: at a bus stand/station they may need a rest stop or a
        stay; already inside a stay they need neither; otherwise suggest
        what is open and near. Nothing is shown for places that are closed."""
        places, _, _ = await self._candidates(lat, lon)
        right_now = await self.context_service.right_now(lat, lon, None)
        hour = right_now.now_local.hour
        late = hour >= 21 or hour < 5

        def dist(p):
            return haversine_km(lat, lon, p.coordinates.latitude, p.coordinates.longitude)

        near = sorted(places, key=dist)
        at, near_name = "outdoors", None
        # How close counts as "at" depends on how accurate the device fix is.
        # A laptop's Wi-Fi/IP location can be off by hundreds of metres, and then
        # claiming a specific building would be a guess, so we don't.
        vague = accuracy is not None and accuracy > 200
        slack = max(0.0, min((accuracy or 0) / 1000.0, 0.2))
        if vague:
            approx = True if accuracy > 1500 else approx
        # With no real location the coordinates are just the city centre, so we
        # must not claim the person is "at" anything.
        for p in ([] if (approx or vague) else near[:12]):
            d = dist(p)
            if p.category in STAY and d <= max(0.05, slack) + 0.03:
                at, near_name = "stay", p.name
                break
            if p.category in TRANSIT and d <= max(0.08, slack) + 0.07:
                at, near_name = "transit", p.name
                break
        if not approx and not vague and at == "outdoors" and near and dist(near[0]) <= max(0.04, slack) + 0.02:
            at, near_name = "place", near[0].name

        open_places = self._recommendable(places)
        if at == "stay":
            wanted = [p for p in open_places if p.category in EAT and dist(p) <= 2.0]
            headline = f"You're at {near_name}"
            detail = "No need to look for a room. Here is food that's open close by." if wanted else "You're settled in. Ask the Guide what to do tomorrow."
            kind = "food"
        elif at == "transit":
            if late:
                wanted = [p for p in open_places if p.category in STAY and dist(p) <= 5.0]
                headline = f"It's late, and you're at {near_name}"
                detail = "Rooms that are open near you:"
                kind = "stay"
            else:
                wanted = [p for p in open_places if (p.category in EAT or p.category in STAY) and dist(p) <= 2.5]
                headline = f"You're at {near_name}"
                detail = "A place to sit, eat or rest nearby:"
                kind = "rest"
        else:
            if late:
                wanted = [p for p in open_places if (p.category in STAY or p.category in EAT) and dist(p) <= 4.0]
                headline = "It's late in Mangaluru"
                detail = "Only places that are open now:"
                kind = "stay"
            else:
                wanted = [p for p in open_places if p.category not in (STAY | TRANSIT) and dist(p) <= 4.0]
                headline = "Open in central Mangaluru" if approx else ("Open around your area" if vague else "Open near you right now")
                detail = "Closest first. Closed places are left out."
                kind = "explore"
        wanted.sort(key=dist)
        cards = [self._card(p, right_now, lat, lon) for p in wanted[:4]]
        if vague and not approx:
            detail = f"Your device's location is only accurate to about {int(accuracy)} m, so these are approximate. " + detail
        return dict(situation=at, near_name=near_name, accuracy_m=accuracy, headline=headline, detail=detail, kind=kind,
                    now_local=right_now.now_local.isoformat(), suggestions=cards)

    # ---- GroundZero Picks (mood-based) ----------------------------------

    async def picks(self, mood: str, lat: Optional[float], lon: Optional[float], limit: int = 12) -> list[dict]:
        places, center_lat, center_lon = await self._candidates(lat, lon)
        places = self._recommendable(places)
        right_now = await self.context_service.right_now(center_lat, center_lon, None)
        profile = _mood_profile(mood, right_now.now_local.hour)
        mood_tags = set(MOOD_TAG_WEIGHTS.get(mood, {}).keys())

        scored: list[tuple[FitBreakdown, Place]] = []
        for place in places:
            matches_mood = bool(mood_tags & set(place.tags)) or place.category in mood_tags
            if not matches_mood:
                continue
            breakdown = self.fit_score.score(place, profile, scheduled_hour=right_now.now_local.hour)
            scored.append((breakdown, place))

        def _rank(pair):
            br, pl = pair
            dist = haversine_km(center_lat, center_lon, pl.coordinates.latitude, pl.coordinates.longitude)
            bonus = 0.05 if self._open(pl).source == "listed" else 0.0
            return br.personal_fit + bonus - 0.012 * min(dist, 25)

        scored.sort(key=_rank, reverse=True)

        out = []
        for breakdown, place in scored[:limit]:
            card = self._card(place, right_now, center_lat, center_lon)
            is_open = self._is_open_now(place)
            suitable_conditions = True
            is_outdoor = place.is_outdoor() or bool({"beach", "park", "garden", "viewpoint", "lake"} & set(place.tags))
            if is_outdoor and right_now.weather_available and right_now.is_rain:
                suitable_conditions = False
            card["fit_percent"] = round(breakdown.personal_fit * 100)
            card["why_this_pick"] = dict(
                matches_selected_mood=True,
                fits_available_time=place.dwell_time_typical_minutes <= 240,
                suitable_current_conditions=suitable_conditions,
                lower_expected_crowd=place.crowd_level in (CrowdLevel.LOW,),
            )
            out.append(card)
        return out

    # ---- Beyond the Obvious ---------------------------------------------

    async def beyond_the_obvious(self, lat: Optional[float], lon: Optional[float], limit: int = 10) -> list[dict]:
        places, center_lat, center_lon = await self._candidates(lat, lon)
        right_now = await self.context_service.right_now(center_lat, center_lon, None)

        places = self._recommendable(places)
        candidates = [p for p in places if p.bias_signals.media_mentions <= 3]
        candidates = [p for p in candidates if p.category not in (STAY | TRANSIT | NOT_EXPERIENCES) and not _is_chain(p.name)]
        candidates.sort(key=lambda p: (p.bias_signals.media_mentions, p.bias_index if p.bias_index is not None else 1.0))

        out = []
        for place in candidates[:limit]:
            card = self._card(place, right_now, center_lat, center_lon)
            if place.bias_signals.media_mentions == 0:
                why_found = "Verified in GroundZero's data, but almost never mentioned online."
            else:
                why_found = f"Only {place.bias_signals.media_mentions} known media mentions — far below the city's well-known spots."
            card["why_found_this"] = why_found
            out.append(card)
        return out

    # ---- Explore by Experience -------------------------------------------

    async def experience_categories(self, lat: Optional[float], lon: Optional[float], preview_count: int = 6) -> list[dict]:
        places, center_lat, center_lon = await self._candidates(lat, lon)
        places = [p for p in self._recommendable(places) if p.category not in NOT_EXPERIENCES]
        right_now = await self.context_service.right_now(center_lat, center_lon, None)

        out = []
        for exp in EXPERIENCE_CATEGORIES:
            matched = [
                p for p in places
                if (set(exp.tags) & set(p.tags) or p.category in exp.categories)
                and not (exp.slug in ("local_life", "culture_heritage", "quiet_places") and _is_chain(p.name))
            ]
            matched.sort(key=lambda p: (-p.bias_signals.tourist_popularity + 0.4 * haversine_km(center_lat, center_lon, p.coordinates.latitude, p.coordinates.longitude)))
            preview = [self._card(p, right_now, center_lat, center_lon) for p in matched[:preview_count]]
            out.append(dict(slug=exp.slug, label=exp.label, preview=preview, total_count=len(matched)))
        return out

    async def experience_category(self, slug: str, lat: Optional[float], lon: Optional[float], limit: int = 40) -> list[dict]:
        exp = next((e for e in EXPERIENCE_CATEGORIES if e.slug == slug), None)
        if exp is None:
            return []
        places, center_lat, center_lon = await self._candidates(lat, lon)
        places = [p for p in self._recommendable(places) if p.category not in NOT_EXPERIENCES]
        right_now = await self.context_service.right_now(center_lat, center_lon, None)
        matched = [
            p for p in places
            if (set(exp.tags) & set(p.tags) or p.category in exp.categories)
            and not (exp.slug in ("local_life", "culture_heritage", "quiet_places") and _is_chain(p.name))
        ]
        matched.sort(key=lambda p: (-p.bias_signals.tourist_popularity + 0.4 * haversine_km(center_lat, center_lon, p.coordinates.latitude, p.coordinates.longitude)))
        return [self._card(p, right_now, center_lat, center_lon) for p in matched[:limit]]

    # ---- Search -----------------------------------------------------------

    async def search(
        self, query: str, lat: Optional[float], lon: Optional[float],
        category: Optional[str] = None, max_distance_km: Optional[float] = None,
        open_now: bool = False, limit: int = 30,
    ) -> list[dict]:
        places, center_lat, center_lon = await self._candidates(lat, lon)
        right_now = await self.context_service.right_now(center_lat, center_lon, None)

        q = query.strip().lower()
        results = []
        for place in places:
            if q and q not in place.name.lower() and not any(q in t for t in place.tags):
                continue
            if category and place.category != category and category not in place.tags:
                continue
            distance = haversine_km(center_lat, center_lon, place.coordinates.latitude, place.coordinates.longitude)
            if max_distance_km is not None and distance > max_distance_km:
                continue
            if open_now and self._is_open_now(place) is False:
                continue
            results.append(place)

        results.sort(key=lambda p: (self._open(p).state == 'closed', haversine_km(center_lat, center_lon, p.coordinates.latitude, p.coordinates.longitude)))
        return [self._card(p, right_now, center_lat, center_lon) for p in results[:limit]]

    # ---- Place detail -------------------------------------------------------

    async def place_detail(self, place_id: str, lat: Optional[float], lon: Optional[float]) -> Optional[dict]:
        place = await self.place_repository.get_by_id(place_id)
        if place is None:
            return None
        center_lat = lat if lat is not None else self.mangaluru_center[0]
        center_lon = lon if lon is not None else self.mangaluru_center[1]
        right_now = await self.context_service.right_now(center_lat, center_lon, None)
        headline, reasons = self._why_now(place, right_now)

        good_for = []
        if place.family_friendly:
            good_for.append("Families")
        if place.kid_friendly:
            good_for.append("Kids")
        if place.photography_allowed:
            good_for.append("Photography")
        if place.pet_friendly:
            good_for.append("Pets")
        if place.accessibility.wheelchair:
            good_for.append("Wheelchair access")
        if not good_for:
            good_for.append(place.category.replace("_", " ").title())

        tagline = f"{place.tags[0].replace('_', ' ').title()}, Mangaluru" if place.tags else "Mangaluru"
        why_go = place.wiki_summary or place.description or (
            f"{place.name} is a {(place.tags[0] if place.tags else place.category).replace('_', ' ').lower()} in Mangaluru, "
            f"listed in GroundZero's verified place data."
        )

        return dict(
            place_id=place.id or "",
            name=place.name,
            category=place.category,
            tags=place.tags,
            tagline=tagline,
            latitude=place.coordinates.latitude,
            longitude=place.coordinates.longitude,
            why_go=why_go,
            good_for=good_for,
            why_now=dict(headline=headline, reasons=reasons),
            price_band=place.price_band.value,
            estimated_cost=place.estimated_cost,
            opening_hours_raw=place.opening_hours.raw,
            etiquette_tag=place.etiquette_tag,
            grade=place.grade.value if place.grade else None,
            provenance=self._provenance(place),
            image_url=None,
        )
