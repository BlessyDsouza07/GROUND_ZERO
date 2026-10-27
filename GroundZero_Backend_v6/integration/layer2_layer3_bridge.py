"""
Layer 2 <-> Layer 3 compatibility route.

Layer 3's own bridge code (layer3/layer3_bridge.py, class Layer2Client)
calls `POST {LAYER2_BASE_URL}/hive/generate` with `{"profile_id": ...}`
when a session is started with only a profile_id (no itinerary/queue
supplied directly) — see layer3/README.md §3 ("Layer 3 -> Layer 2:
POST /hive/generate"). Layer 2's actual, tested endpoint is
`POST /hive/recommendations` (layer2/api/routes.py), built independently
and with a different name/shape before Layer 3 existed — exactly the kind
of "Layers 0-2 evolve independently" seam layer3_bridge.py's own docstring
already anticipates and is deliberately tolerant of.

This module adds the missing endpoint rather than changing either side:
it is a thin, purely-additive alias that reuses Layer 2's real
dependency-injected HiveEngine/ProfileRepository (get_hive_engine,
get_profile_repository) and its own response-shaping (_queue_to_out) —
zero duplicated business logic, zero changes to layer2/api/routes.py.

In Ground Zero's normal flow the frontend already holds the itinerary
returned by /hive/recommendations by the time the tourist starts their
trip, and passes it straight into POST /l3/session/start as `itinerary`
(see frontend/src/screens/companion/CompanionScreen.js) — so this route
is a safety net / API-completeness fix for the profile_id-only path
(e.g. calling Layer 3 directly via /docs, or a future Layer 4), not
something the shipped app depends on for its main flow.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from layer0.api.security import require_admin_api_key
from layer1.domain.repositories import TouristProfileRepository
from layer2.api.dependencies import get_hive_engine, get_profile_repository
from layer2.api.routes import _queue_to_out
from layer2.api.schemas import RecommendationQueueOut
from layer2.application.hive_engine import HiveEngine

router = APIRouter(tags=["layer2-layer3-bridge"])

# SECURITY FIX (4th audit response, Oct 2026): this was fully public and
# accepted an arbitrary profile_id with zero auth or ownership check --
# the same bug class as /hive/recommendations had before the previous
# pass, missed then because this route lives outside layer2/api/routes.py.
# Unlike /hive/recommendations, this endpoint has no real end-user behind
# it: it exists only for Layer 3's own server-to-server bridge call (see
# module docstring) and layer3_bridge.py's Layer2Client never has (and
# shouldn't need) a tourist's bearer token to forward. A per-user
# ownership check is therefore the wrong tool here. Instead this is now
# gated the same way /admin/* already is -- a shared-secret
# X-Admin-Api-Key header, fails closed if ADMIN_API_KEY is unset -- and
# is no longer reachable by an anonymous public caller.
# layer3/layer3_bridge.py's Layer2Client now sends that header.


class HiveGenerateIn(BaseModel):
    profile_id: str


@router.post(
    "/hive/generate", response_model=RecommendationQueueOut, dependencies=[Depends(require_admin_api_key)]
)
async def hive_generate_compat(
    payload: HiveGenerateIn,
    engine: HiveEngine = Depends(get_hive_engine),
    profile_repo: TouristProfileRepository = Depends(get_profile_repository),
) -> RecommendationQueueOut:
    """Same behavior as POST /hive/recommendations with only a profile_id
    (no pinned places, no explicit start location) — just under the path
    name and request shape Layer 3's Layer2Client already calls."""
    profile = await profile_repo.get_by_id(payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"TouristProfile {payload.profile_id} not found")

    queue = await engine.build_recommendation_queue(profile, datetime.now(timezone.utc), None)
    return _queue_to_out(queue)
