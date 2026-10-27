from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from layer1.domain.entities import TouristProfile


class TouristProfileRepository(ABC):
    @abstractmethod
    async def save(self, profile: TouristProfile) -> TouristProfile:
        ...

    @abstractmethod
    async def get_by_id(self, profile_id: str) -> Optional[TouristProfile]:
        ...

    @abstractmethod
    async def get_prior_session_for_device(self, device_id: str) -> Optional[TouristProfile]:
        """Supports the Return Visitor check (blueprint 4.5): looking up
        whether this device has a prior completed session."""
        ...

    @abstractmethod
    async def get_visited_place_ids(self, profile_id: str) -> list[str]:
        """The prior session's visited_log, per blueprint 4.5, used to
        populate return_visitor_exclusions."""
        ...

    @abstractmethod
    async def mark_visited(self, profile_id: str, place_ids: list[str]) -> list[str]:
        """Appends to a profile's visited_log — the write side of
        get_visited_place_ids above. An architectural audit found this
        had no write path anywhere in the codebase: the column existed,
        the read method existed, but nothing ever called it, so Return
        Visitor Check always resolved to an empty exclusion list in
        production. Returns the full, de-duplicated visited_log after
        the update."""
        ...

    @abstractmethod
    async def list_by_group_session(self, group_session_id: str) -> list[TouristProfile]:
        """All TouristProfiles sharing a group_session_id (blueprint 4.7 —
        Couple/Family/Friends group members who joined via the shared
        code). Each member has their own separate TouristProfile and
        curiosity_vector; this just links them for Group Sync (Layer 4,
        out of current scope) to consume later."""
        ...
