from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from layer0.api.dependencies import get_community_submission_service, get_place_repository
from layer0.application.community_workflow import CommunitySubmissionService
from layer0.domain.repositories import PlaceRepository
from trips.dependencies import get_db_session, get_trips_service
from trips.service import TripsService

from .service import PersonalService


def get_personal_service(
    db: AsyncSession = Depends(get_db_session),
    submission_service: CommunitySubmissionService = Depends(get_community_submission_service),
    trips_service: TripsService = Depends(get_trips_service),
    place_repository: PlaceRepository = Depends(get_place_repository),
) -> PersonalService:
    return PersonalService(db, submission_service, trips_service, place_repository)
