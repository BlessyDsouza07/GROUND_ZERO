from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ItineraryItemIn(BaseModel):
    place_id: str
    place_name: str
    role: str


class SaveItineraryIn(BaseModel):
    # Full current desired order, post-edits — index in this list is the
    # order shown/experienced. Removed places aren't in here at all;
    # they're listed separately in removed_place_ids instead.
    items: list[ItineraryItemIn]
    removed_place_ids: list[str] = []
    added_place_ids: list[str] = []  # places the tourist added themselves, by id — see /places/custom
    place_ratings: dict[str, str] = {}  # place_id -> "up" | "down"
    overall_rating: int | None = Field(default=None, ge=1, le=5)


class ItineraryItemOut(BaseModel):
    place_id: str
    place_name: str
    role: str
    order_index: int


class ConfirmedItineraryOut(BaseModel):
    profile_id: str
    items: list[ItineraryItemOut]
    removed_place_ids: list[str]
    added_place_ids: list[str]
    place_ratings: dict[str, str]
    overall_rating: int | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None
    confirmed_at: datetime | None
