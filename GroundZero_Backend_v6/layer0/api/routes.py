from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from auth.models import User
from layer0.api.dependencies import get_community_submission_service, get_custom_place_service, get_place_repository
from layer0.api.schemas import (
    CommunitySubmissionIn,
    CommunitySubmissionOut,
    CustomPlaceIn,
    CustomPlaceOut,
    PlaceOut,
)
from layer0.application.community_workflow import CommunitySubmissionService
from layer0.application.custom_place_service import CustomPlaceService
from layer0.domain.entities import (
    AccessibilityInfo,
    BiasSignals,
    Coordinates,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.domain.repositories import PlaceRepository

router = APIRouter(prefix="/places", tags=["places"])

# Community submissions are, by construction, a local person flagging a
# place they know — presumptively authentic until the normal bias audit
# process (media mentions, admin review, eventual tourist feedback) says
# otherwise. Deliberately kept above
# layer2.application.slot_assembly.LOCAL_SECRET_MIN_LOCAL_PERCENTAGE (0.9):
# an earlier default of 0.85 sat below that threshold, meaning genuine
# community hidden-gem submissions could never qualify for the Local
# Secret slot they exist to feed. See
# layer2/tests/test_slot_assembly.py::test_community_submission_bias_default_clears_local_secret_threshold
# for the regression guard.
COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE = 0.92


# Return Visitor tracking endpoint (Phase 1 implementation, Aug 4 2026)
# Marks a place as visited by the user. Used by Layer 1 Return Visitor Check
# to exclude previously-visited places from recommendations.
#
# SECURITY NOTE (audit response, Oct 2026): this had no auth dependency
# at all — anyone could call it. In practice `record_visit` below is
# itself only a Phase-1 existence-check stub (see its own docstring in
# repository_impl.py: "the actual visit recording will be handled by
# Layer 1's TouristProfileRepository"), i.e. it writes no per-user data
# today — the real write path is layer1/api/routes.py's
# POST /survey/profile/{profile_id}/visited, which is now itself auth-
# gated and ownership-checked. Still, a public endpoint with this name
# and docstring is misleading and worth closing now rather than later,
# so it also requires a signed-in user.
@router.post("/{place_id}/mark-visited")
async def mark_place_visited(
    place_id: str,
    user: User = Depends(get_current_user),
    place_repo: PlaceRepository = Depends(get_place_repository)
) -> dict:
    """
    Mark a place as visited.

    Used by Layer 1's Return Visitor Check to remember which places
    the user has already visited, so subsequent HIVE recommendations
    can exclude them.

    Args:
        place_id: UUID of the place being marked visited

    Returns:
        {"status": "ok", "place_id": place_id}
    """
    try:
        await place_repo.record_visit(place_id)
        return {"status": "ok", "place_id": place_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _to_place_out(place: Place) -> PlaceOut:
    return PlaceOut(
        id=place.id or "",
        name=place.name,
        category=place.category,
        latitude=place.coordinates.latitude,
        longitude=place.coordinates.longitude,
        opening_hours=place.opening_hours.raw,
        days_open=place.opening_hours.days_open,
        estimated_cost=place.estimated_cost,
        price_band=place.price_band.value,
        tags=place.tags,
        local_percentage=place.bias_signals.local_percentage,
        media_mentions=place.bias_signals.media_mentions,
        bias_index=place.bias_index,
        grade=place.grade.value if place.grade else None,
        energy_requirement=place.energy_requirement.value,
        crowd_level=place.crowd_level.value,
        season_suitability=place.season_suitability,
        tide_dependency=place.tide_dependency,
        dwell_time_typical=place.dwell_time_typical_minutes,
        accessibility_tags=place.accessibility.tags,
        wheelchair=place.accessibility.wheelchair,
        stairs=place.accessibility.stairs,
        sensory_notes=place.accessibility.sensory_notes,
        parking=place.parking,
        washrooms=place.washrooms,
        food_available=place.food_available,
        pet_friendly=place.pet_friendly,
        family_friendly=place.family_friendly,
        kid_friendly=place.kid_friendly,
        photography_allowed=place.photography_allowed,
        best_time=place.best_time,
        freshness_score=place.freshness_score,
        last_verified_at=place.last_verified_at,
        temporarily_unavailable=place.temporarily_unavailable,
        etiquette_tag=place.etiquette_tag,
        source=[s.value for s in place.source],
        description=place.description,
        wiki_summary=place.wiki_summary,
        transport_access=place.transport_access,
    )



@router.get("", response_model=list[PlaceOut])
async def list_places(
    category: str | None = None,
    repo: PlaceRepository = Depends(get_place_repository),
) -> list[PlaceOut]:
    logger.info("GET places started: category=%r", category)

    try:
        places = await repo.list_all(category=category)
        logger.info("GET places database query succeeded: count=%d", len(places))

        places = [
            p for p in places
            if p.verification_status == "verified"
        ]
        result = [_to_place_out(p) for p in places]

        logger.info("GET places response conversion succeeded: count=%d", len(result))
        return result

    except Exception:
        logger.exception("GET places failed: category=%r", category)
        raise


@router.get("/nearby", response_model=list[PlaceOut])
async def search_nearby_places(
    latitude: float,
    longitude: float,
    radius_meters: float = 150.0,
    service: CustomPlaceService = Depends(get_custom_place_service),
) -> list[PlaceOut]:
    """The 'search the map' half of the tourist-added-place flow: shows
    what's already known near a pin the tourist dropped, closest first,
    so they can pick an existing place instead of creating a near-
    duplicate. Category-agnostic — see CustomPlaceService docstring."""
    places = await service.search_nearby(latitude, longitude, radius_meters)
    return [_to_place_out(p) for p in places]


@router.post("/custom", response_model=CustomPlaceOut, status_code=201)
async def add_custom_place(
    payload: CustomPlaceIn,
    service: CustomPlaceService = Depends(get_custom_place_service),
    user: User = Depends(get_current_user),
) -> CustomPlaceOut:
    """A tourist adds a place of their own choosing — one HIVE didn't
    recommend. If it's a genuine match for something already in the
    Master Data Core, that existing place is returned and reused
    (was_newly_created=False). Otherwise it's added right now, from the
    tourist's own info, no admin approval gate needed — see
    CustomPlaceService's module docstring for why this differs from
    /places/submissions (Community Submissions).

    Requires a signed-in user: this writes into the shared Master Data
    Core immediately (no moderation queue, by design — see
    CustomPlaceService's docstring), so it must not be reachable by an
    anonymous caller. Fixed per security audit, Oct 2026.

    The returned place.id is what the tourist's client should pass as a
    `pinned_place_id` to POST /hive/recommendations, so HIVE guarantees
    it lands in their itinerary."""
    try:
        result = await service.add_or_find(
            name=payload.name,
            lat=payload.latitude,
            lon=payload.longitude,
            category=payload.category,
            note=payload.note,
            estimated_cost=payload.estimated_cost,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return CustomPlaceOut(place=_to_place_out(result.place), was_newly_created=result.was_newly_created)


@router.get("/{place_id}", response_model=PlaceOut)
async def get_place(place_id: str, repo: PlaceRepository = Depends(get_place_repository)) -> PlaceOut:
    place = await repo.get_by_id(place_id)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place {place_id} not found")
    return _to_place_out(place)


@router.post("/submissions", response_model=CommunitySubmissionOut, status_code=201)
async def submit_place(
    payload: CommunitySubmissionIn,
    service: CommunitySubmissionService = Depends(get_community_submission_service),
    user: User = Depends(get_current_user),
) -> CommunitySubmissionOut:
    place = Place(
        id=None,
        name=payload.name,
        category=payload.category,
        coordinates=Coordinates(latitude=payload.latitude, longitude=payload.longitude),
        opening_hours=OpeningHours(raw=""),
        price_band=PriceBand(payload.price_band),
        estimated_cost=payload.estimated_cost,
        description=payload.description,
        bias_signals=BiasSignals(
            local_percentage=COMMUNITY_SUBMISSION_DEFAULT_LOCAL_PERCENTAGE,
            media_mentions=0,
        ),
        accessibility=AccessibilityInfo(),
    )
    # SECURITY FIX (final-release-hardening pass, Oct 2026): `user` was
    # already required here for the auth gate but previously unused beyond
    # that — now the real submitter is recorded on the row itself.
    submission = await service.submit(place, payload.submitter_note, submitter_user_id=str(user.id))
    return CommunitySubmissionOut(
        id=submission.id or "",
        status=submission.status,
        submitted_at=submission.submitted_at,
        place_name=submission.submitted_place.name,
    )
