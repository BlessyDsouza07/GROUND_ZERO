from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from layer2.domain.feedback_entities import ConfirmedItinerary, PlaceFeedbackSignal


class ItineraryFeedbackRepository(ABC):
    @abstractmethod
    async def get_by_profile_id(self, profile_id: str) -> Optional[ConfirmedItinerary]:
        ...

    @abstractmethod
    async def save(self, itinerary: ConfirmedItinerary) -> ConfirmedItinerary:
        ...

    @abstractmethod
    async def get_signal(self, place_id: str) -> Optional[PlaceFeedbackSignal]:
        ...

    @abstractmethod
    async def upsert_signal(self, signal: PlaceFeedbackSignal) -> PlaceFeedbackSignal:
        ...

    @abstractmethod
    async def list_all_signals(self) -> list[PlaceFeedbackSignal]:
        ...
