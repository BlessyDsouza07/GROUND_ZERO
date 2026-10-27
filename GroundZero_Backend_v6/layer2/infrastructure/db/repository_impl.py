from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from layer2.domain.feedback_entities import ConfirmedItinerary, ItineraryItem, ItineraryStatus, PlaceFeedbackSignal
from layer2.domain.feedback_repositories import ItineraryFeedbackRepository
from layer2.infrastructure.db.models import ConfirmedItineraryModel, PlaceFeedbackSignalModel


def _itinerary_to_model(itinerary: ConfirmedItinerary, existing: ConfirmedItineraryModel | None) -> ConfirmedItineraryModel:
    model = existing or ConfirmedItineraryModel(id=uuid.uuid4(), profile_id=itinerary.profile_id)
    model.items = [
        {"place_id": i.place_id, "place_name": i.place_name, "role": i.role, "order_index": i.order_index}
        for i in itinerary.items
    ]
    model.original_order = itinerary.original_order
    model.removed_place_ids = itinerary.removed_place_ids
    model.added_place_ids = itinerary.added_place_ids
    model.overall_rating = itinerary.overall_rating
    model.place_ratings = itinerary.place_ratings
    model.status = itinerary.status.value
    if itinerary.status == ItineraryStatus.CONFIRMED and model.confirmed_at is None:
        model.confirmed_at = datetime.now(timezone.utc)
    return model


def _itinerary_to_domain(model: ConfirmedItineraryModel) -> ConfirmedItinerary:
    return ConfirmedItinerary(
        profile_id=model.profile_id,
        items=[ItineraryItem(**item) for item in model.items],
        original_order=model.original_order,
        removed_place_ids=model.removed_place_ids,
        added_place_ids=model.added_place_ids,
        overall_rating=model.overall_rating,
        place_ratings=model.place_ratings,
        status=ItineraryStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        confirmed_at=model.confirmed_at,
    )


def _signal_to_domain(model: PlaceFeedbackSignalModel) -> PlaceFeedbackSignal:
    return PlaceFeedbackSignal(
        place_id=model.place_id,
        thumbs_up=model.thumbs_up,
        thumbs_down=model.thumbs_down,
        times_removed=model.times_removed,
        times_manually_added=model.times_manually_added,
        times_moved_earlier=model.times_moved_earlier,
        times_moved_later=model.times_moved_later,
        last_updated_at=model.last_updated_at,
    )


class PostgresItineraryFeedbackRepository(ItineraryFeedbackRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_profile_id(self, profile_id: str) -> ConfirmedItinerary | None:
        result = await self.session.execute(
            select(ConfirmedItineraryModel).where(ConfirmedItineraryModel.profile_id == profile_id)
        )
        model = result.scalar_one_or_none()
        return _itinerary_to_domain(model) if model else None

    async def save(self, itinerary: ConfirmedItinerary) -> ConfirmedItinerary:
        result = await self.session.execute(
            select(ConfirmedItineraryModel).where(ConfirmedItineraryModel.profile_id == itinerary.profile_id)
        )
        existing = result.scalar_one_or_none()
        model = _itinerary_to_model(itinerary, existing)
        if existing is None:
            self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return _itinerary_to_domain(model)

    async def get_signal(self, place_id: str) -> PlaceFeedbackSignal | None:
        result = await self.session.execute(
            select(PlaceFeedbackSignalModel).where(PlaceFeedbackSignalModel.place_id == place_id)
        )
        model = result.scalar_one_or_none()
        return _signal_to_domain(model) if model else None

    async def upsert_signal(self, signal: PlaceFeedbackSignal) -> PlaceFeedbackSignal:
        result = await self.session.execute(
            select(PlaceFeedbackSignalModel).where(PlaceFeedbackSignalModel.place_id == signal.place_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            model = PlaceFeedbackSignalModel(place_id=signal.place_id)
            self.session.add(model)
        model.thumbs_up = signal.thumbs_up
        model.thumbs_down = signal.thumbs_down
        model.times_removed = signal.times_removed
        model.times_manually_added = signal.times_manually_added
        model.times_moved_earlier = signal.times_moved_earlier
        model.times_moved_later = signal.times_moved_later
        await self.session.commit()
        await self.session.refresh(model)
        return _signal_to_domain(model)

    async def list_all_signals(self) -> list[PlaceFeedbackSignal]:
        result = await self.session.execute(select(PlaceFeedbackSignalModel))
        return [_signal_to_domain(m) for m in result.scalars().all()]
