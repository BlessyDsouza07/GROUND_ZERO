import pytest

from layer2.application.feedback_service import ItineraryFeedbackService
from layer2.domain.feedback_entities import ConfirmedItinerary, ItineraryItem, ItineraryStatus, PlaceFeedbackSignal
from layer2.domain.feedback_repositories import ItineraryFeedbackRepository


class FakeItineraryFeedbackRepository(ItineraryFeedbackRepository):
    def __init__(self):
        self.itineraries: dict[str, ConfirmedItinerary] = {}
        self.signals: dict[str, PlaceFeedbackSignal] = {}

    async def get_by_profile_id(self, profile_id: str):
        return self.itineraries.get(profile_id)

    async def save(self, itinerary: ConfirmedItinerary) -> ConfirmedItinerary:
        self.itineraries[itinerary.profile_id] = itinerary
        return itinerary

    async def get_signal(self, place_id: str):
        return self.signals.get(place_id)

    async def upsert_signal(self, signal: PlaceFeedbackSignal) -> PlaceFeedbackSignal:
        self.signals[signal.place_id] = signal
        return signal

    async def list_all_signals(self) -> list[PlaceFeedbackSignal]:
        return list(self.signals.values())


def _items(*place_ids: str) -> list[ItineraryItem]:
    return [ItineraryItem(place_id=pid, place_name=pid, role="personal", order_index=idx) for idx, pid in enumerate(place_ids)]


@pytest.mark.asyncio
async def test_first_save_captures_original_order():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    itinerary = await service.save_draft("profile-1", _items("a", "b", "c"), [], [], {}, None)

    assert itinerary.original_order == ["a", "b", "c"]
    assert itinerary.status == ItineraryStatus.DRAFT


@pytest.mark.asyncio
async def test_subsequent_draft_saves_preserve_original_order():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    await service.save_draft("profile-1", _items("a", "b", "c"), [], [], {}, None)
    # tourist reorders — b now first
    itinerary = await service.save_draft("profile-1", _items("b", "a", "c"), [], [], {}, None)

    assert itinerary.original_order == ["a", "b", "c"]  # unchanged — baseline, not the latest edit
    assert [i.place_id for i in itinerary.items] == ["b", "a", "c"]


@pytest.mark.asyncio
async def test_confirm_without_prior_save_raises():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    with pytest.raises(ValueError):
        await service.confirm("profile-never-saved")


@pytest.mark.asyncio
async def test_confirm_applies_removed_added_and_rating_signals():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    await service.save_draft(
        "profile-1", _items("a", "b"),
        removed_place_ids=["c"], added_place_ids=["d"],
        place_ratings={"a": "up", "b": "down"}, overall_rating=4,
    )
    await service.confirm("profile-1")

    assert (await repo.get_signal("c")).times_removed == 1
    assert (await repo.get_signal("d")).times_manually_added == 1
    assert (await repo.get_signal("a")).thumbs_up == 1
    assert (await repo.get_signal("b")).thumbs_down == 1


@pytest.mark.asyncio
async def test_confirm_applies_reorder_signals_against_original_order():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    await service.save_draft("profile-1", _items("a", "b", "c"), [], [], {}, None)
    # tourist moves c to the front (earlier), a to the back (later); b unchanged
    await service.save_draft("profile-1", _items("c", "b", "a"), [], [], {}, None)
    await service.confirm("profile-1")

    assert (await repo.get_signal("c")).times_moved_earlier == 1
    assert (await repo.get_signal("a")).times_moved_later == 1
    signal_b = await repo.get_signal("b")
    assert signal_b is not None
    assert signal_b.times_moved_earlier == 0
    assert signal_b.times_moved_later == 0


@pytest.mark.asyncio
async def test_confirm_is_idempotent_does_not_double_count():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    await service.save_draft("profile-1", _items("a"), removed_place_ids=["x"], added_place_ids=[], place_ratings={}, overall_rating=None)
    await service.confirm("profile-1")
    await service.confirm("profile-1")  # calling confirm again must not double-apply signals

    assert (await repo.get_signal("x")).times_removed == 1


@pytest.mark.asyncio
async def test_confirmed_itinerary_status_and_timestamp_set():
    repo = FakeItineraryFeedbackRepository()
    service = ItineraryFeedbackService(repo)

    await service.save_draft("profile-1", _items("a"), [], [], {}, None)
    confirmed = await service.confirm("profile-1")

    assert confirmed.status == ItineraryStatus.CONFIRMED
