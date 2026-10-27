"""
Tourist-Added Place service.

Real problem this solves: for a lot of genuinely local Mangaluru spots,
automated collection (OSM/Wikidata/Wikipedia) just doesn't have coverage
yet (see README's honesty note on this). Rather than making the tourist
wait for Layer 0 to "catch up," they can add a place they already have in
mind — by searching what's nearby first, or typing a name + dropping a
map pin if it's genuinely not in the system yet.

Two things both need to be true for this to be a real feature and not
just a wishlist button:

  1. The tourist actually gets taken there. HiveEngine accepts a
     `pinned_place_ids` list (see layer2/application/hive_engine.py) and
     forces those places into the Recommendation Queue as a protected
     `tourist_pick` slot — bypassing Hard Filters and budget trimming,
     because the tourist explicitly chose it, not HIVE.
  2. The Master Data Core actually grows from it, eventually, without
     ever trusting a stranger's self-reported data as "real" the moment
     they type it. If the place doesn't already exist, it IS stored right
     now (the tourist's own itinerary need can't wait on a human
     reviewer) — tagged distinctly (DataSource.TOURIST_ADDED) with
     conservative, clearly-self-reported bias signals — but as
     verification_status="pending", not "verified". A pending place is
     fully usable by the tourist who added it (HiveEngine resolves
     pinned_place_ids by id regardless of status, so "you'll be taken
     there" still holds) but is excluded from HIVE's general
     recommendation pool and from GET /places for everyone else until an
     admin promotes it via POST /admin/places/{id}/verify
     (layer0/api/admin.py) — the same human-review gate Community
     Submissions already has, just reached by a different door.
     SECURITY FIX (final-release-hardening pass, Oct 2026): before this,
     every tourist-added place went straight to "verified" with no
     review at all — an audit flagged this as letting any signed-in
     tourist write directly into shared, trusted Master Data.

Matching intentionally does NOT filter by exact category (unlike
`PlaceRepository.find_duplicates`, which an earlier audit flagged as a
real gap: a place OSM tags "cafe" and a human calls "restaurant" would
never be recognized as the same place). A tourist typing a category
guess is even less reliable than that, so this service does its own
geo+name matching over every place regardless of category.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from layer0.application.bias_audit import BiasAuditService
from layer0.application.dedup import DedupService, haversine_meters
from layer0.application.freshness import FreshnessService
from layer0.domain.entities import (
    BiasSignals,
    Coordinates,
    DataSource,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.domain.repositories import PlaceRepository

# A tourist adding their own place is, by construction, not chasing
# hype — they picked it themselves, off-list. Same self-reported
# convention already used for Community Submissions (local_percentage
# defaults toward "locally known") rather than the harsher all-zero
# default automated OSM ingestion gets.
DEFAULT_LOCAL_PERCENTAGE = 0.80
DEFAULT_SEARCH_RADIUS_METERS = 150.0


@dataclass
class CustomPlaceResult:
    place: Place
    was_newly_created: bool


class CustomPlaceService:
    def __init__(
        self,
        place_repository: PlaceRepository,
        dedup: DedupService,
        bias_audit: BiasAuditService,
        freshness: FreshnessService,
    ):
        self.place_repository = place_repository
        self.dedup = dedup
        self.bias_audit = bias_audit
        self.freshness = freshness

    async def search_nearby(
        self, lat: float, lon: float, radius_meters: float = DEFAULT_SEARCH_RADIUS_METERS
    ) -> list[Place]:
        """Powers the 'search the map' half of the flow — shows the
        tourist what's already known near the pin they dropped, so they
        can pick an existing place instead of accidentally creating a
        near-duplicate. Category-agnostic on purpose (see module
        docstring)."""
        all_places = await self.place_repository.list_all()
        nearby = [
            p for p in all_places
            if haversine_meters(
                lat, lon, p.coordinates.latitude, p.coordinates.longitude
            ) <= radius_meters
        ]
        nearby.sort(key=lambda p: haversine_meters(lat, lon, p.coordinates.latitude, p.coordinates.longitude))
        return nearby

    async def add_or_find(
        self,
        name: str,
        lat: float,
        lon: float,
        category: str | None = None,
        note: str | None = None,
        estimated_cost: float = 0.0,
    ) -> CustomPlaceResult:
        """The core of the feature: given what the tourist typed/picked,
        either reuse an existing place (a genuine dedup match) or create
        a brand-new one right now, from the tourist's own info — no
        admin approval gate, because this is their own itinerary, not a
        public claim awaiting review."""
        if not name or not name.strip():
            raise ValueError("Place name is required")

        candidate = Place(
            id=None,
            name=name.strip(),
            category=(category or "tourist_pick").strip().lower(),
            coordinates=Coordinates(latitude=lat, longitude=lon),
            opening_hours=OpeningHours(raw=""),
            price_band=PriceBand.FREE if estimated_cost <= 0 else PriceBand.BUDGET,
            estimated_cost=max(0.0, estimated_cost),
            tags=["tourist-added"],
            bias_signals=BiasSignals(media_mentions=0, local_percentage=DEFAULT_LOCAL_PERCENTAGE),
            description=note.strip() if note else None,
            source=[DataSource.TOURIST_ADDED],
            # pending until an admin reviews it — see module docstring.
            verification_status="pending",
        )

        nearby = await self.search_nearby(lat, lon)
        match = self.dedup.find_best_match(candidate, nearby)
        if match is not None:
            return CustomPlaceResult(place=match.existing, was_newly_created=False)

        now = datetime.now(timezone.utc)
        candidate.last_verified_at = now
        breakdown = self.bias_audit.compute(candidate.bias_signals)
        candidate.bias_index = breakdown.bias_index
        candidate.grade = self.bias_audit.grade_for(breakdown.bias_index)
        candidate.freshness_score = self.freshness.score(candidate, now=now)

        stored = await self.place_repository.upsert(candidate)
        return CustomPlaceResult(place=stored, was_newly_created=True)
