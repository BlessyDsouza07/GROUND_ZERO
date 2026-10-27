"""
Feedback loop for the tourist-editable itinerary. Two operations:

save_draft() — called every time the tourist reorders/adds/removes/rates
while still deciding; just persists the current state, no counters touched.
Saving repeatedly while someone is still fiddling with the order shouldn't
inflate "moved earlier" counts.

confirm() — called once, when the tourist locks in the plan and is about
to go experience it. THIS is when PlaceFeedbackSignal counters get
updated, exactly once (guarded against double-confirm), comparing the
final confirmed order against original_order (captured on the very first
save). This is the actual, bounded, explainable mechanism that closes the
loop back into the dataset — see bias_signal_estimator.refine_with_community_feedback
and scripts/apply_community_feedback.py for how these counters go on to
nudge bias_index at the next maintenance run. No opaque "the AI learns" —
specific counters, specific formula, specific script, all inspectable.
"""
from __future__ import annotations

from datetime import datetime, timezone

from layer2.domain.feedback_entities import ConfirmedItinerary, ItineraryItem, ItineraryStatus, PlaceFeedbackSignal
from layer2.domain.feedback_repositories import ItineraryFeedbackRepository


class ItineraryFeedbackService:
    def __init__(self, repository: ItineraryFeedbackRepository):
        self.repository = repository

    async def get(self, profile_id: str) -> ConfirmedItinerary | None:
        return await self.repository.get_by_profile_id(profile_id)

    async def save_draft(
        self,
        profile_id: str,
        items: list[ItineraryItem],
        removed_place_ids: list[str],
        added_place_ids: list[str],
        place_ratings: dict[str, str],
        overall_rating: int | None,
    ) -> ConfirmedItinerary:
        existing = await self.repository.get_by_profile_id(profile_id)
        original_order = existing.original_order if existing else [i.place_id for i in items]

        itinerary = ConfirmedItinerary(
            profile_id=profile_id,
            items=items,
            original_order=original_order,
            removed_place_ids=removed_place_ids,
            added_place_ids=added_place_ids,
            overall_rating=overall_rating,
            place_ratings=place_ratings,
            status=ItineraryStatus.DRAFT,
            created_at=existing.created_at if existing else datetime.now(timezone.utc),
        )
        return await self.repository.save(itinerary)

    async def confirm(self, profile_id: str) -> ConfirmedItinerary:
        existing = await self.repository.get_by_profile_id(profile_id)
        if existing is None:
            raise ValueError(f"No saved itinerary draft for profile {profile_id} — call save first")
        if existing.status == ItineraryStatus.CONFIRMED:
            return existing  # already confirmed — don't double-count signals

        await self._apply_feedback_signals(existing)

        existing.status = ItineraryStatus.CONFIRMED
        return await self.repository.save(existing)

    async def _apply_feedback_signals(self, itinerary: ConfirmedItinerary) -> None:
        original_index = {place_id: idx for idx, place_id in enumerate(itinerary.original_order)}
        final_index = {item.place_id: item.order_index for item in itinerary.items}

        touched_place_ids = set(
            itinerary.original_order
            + [i.place_id for i in itinerary.items]
            + itinerary.removed_place_ids
            + itinerary.added_place_ids
            + list(itinerary.place_ratings.keys())
        )

        for place_id in touched_place_ids:
            signal = await self.repository.get_signal(place_id) or PlaceFeedbackSignal(place_id=place_id)

            if place_id in itinerary.removed_place_ids:
                signal.times_removed += 1
            if place_id in itinerary.added_place_ids:
                signal.times_manually_added += 1

            rating = itinerary.place_ratings.get(place_id)
            if rating == "up":
                signal.thumbs_up += 1
            elif rating == "down":
                signal.thumbs_down += 1

            if place_id in original_index and place_id in final_index:
                if final_index[place_id] < original_index[place_id]:
                    signal.times_moved_earlier += 1
                elif final_index[place_id] > original_index[place_id]:
                    signal.times_moved_later += 1

            await self.repository.upsert_signal(signal)
