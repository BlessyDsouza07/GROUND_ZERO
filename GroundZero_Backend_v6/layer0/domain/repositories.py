"""
Repository interfaces (ports) for Layer 0.

Application-layer services depend on these abstractions, never on SQLAlchemy
directly. `infrastructure/db/repository_impl.py` provides the real Postgres
implementation; a test can provide an in-memory fake without touching the
application logic at all. This is the Repository Pattern + Dependency
Inversion the blueprint's tech-stack table asks for.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from layer0.domain.entities import CommunitySubmission, Place


class PlaceRepository(ABC):
    @abstractmethod
    async def get_by_id(self, place_id: str) -> Optional[Place]:
        ...

    @abstractmethod
    async def find_duplicates(self, place: Place, radius_meters: float = 75.0) -> list[Place]:
        """Geo + name-similarity candidate lookup, used by the dedup step."""
        ...

    @abstractmethod
    async def upsert(self, place: Place) -> Place:
        ...

    @abstractmethod
    async def bulk_upsert(self, places: list[Place]) -> list[Place]:
        """Batch version of upsert: one transaction for the whole list
        rather than one per place. See PostgresPlaceRepository for the
        real implementation and the reasoning (an ETL run ingesting
        hundreds/thousands of places previously did one commit per
        place)."""
        ...

    @abstractmethod
    async def list_all(self, category: Optional[str] = None) -> list[Place]:
        ...

    @abstractmethod
    async def list_stale(self, older_than_days: int) -> list[Place]:
        ...

    @abstractmethod
    async def delete(self, place_id: str) -> None:
        ...

    @abstractmethod
    async def record_visit(self, place_id: str) -> None:
        """Record that a user has visited this place.
        
        Used by Layer 1's Return Visitor Check to remember which places
        the user has already visited, so subsequent HIVE recommendations
        can exclude them.
        
        Args:
            place_id: UUID of the place being marked visited
            
        Raises:
            ValueError: If place_id does not exist
        """
        ...


class CommunitySubmissionRepository(ABC):
    @abstractmethod
    async def create(self, submission: CommunitySubmission) -> CommunitySubmission:
        ...

    @abstractmethod
    async def get_by_id(self, submission_id: str) -> Optional[CommunitySubmission]:
        ...

    @abstractmethod
    async def list_pending(self) -> list[CommunitySubmission]:
        ...

    @abstractmethod
    async def update_status(
        self, submission_id: str, status: str, reviewed_by: str, resulting_place_id: str | None = None
    ) -> CommunitySubmission:
        ...
