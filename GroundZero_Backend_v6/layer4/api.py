from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from layer0.api.dependencies import get_db_session
from layer4.navigation import shortest_priority_route
from trips.models import Trip

router = APIRouter(prefix="/layer4", tags=["Layer 4 — Live Guidance"])

# SECURITY FIX (4th audit response, Oct 2026): GET /layer4/session/{id}
# returned personal trip/session data (status, current slot, wallet
# remaining, queue) to anyone, no auth at all. Same ownership link as
# Layer 3 already uses -- Trip.layer3_session_id -- since Layer 4's
# session_id is the same id as the Layer 3 session it supervises.


class Waypoint(BaseModel):
    place_id: str
    place_name: Optional[str] = None
    lat: float
    lng: float
    status: str = "pending"
    role: Optional[str] = None
    priority: int = 0


class RouteRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    waypoints: List[Waypoint] = Field(default_factory=list)


@router.post("/navigation/route")
async def navigation_route(body: RouteRequest) -> Dict[str, Any]:
    pending = [w.model_dump() for w in body.waypoints if w.status not in {"visited", "skipped", "dropped", "replaced"}]
    pending.sort(key=lambda x: (x.get("priority", 0),))
    return await shortest_priority_route((body.origin_lat, body.origin_lng), pending)


@router.get("/session/{session_id}")
async def layer4_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    # BUG FIX (5th audit response, Oct 2026): this was fail-OPEN —
    # `if owner_id is not None and owner_id != user.id` let a
    # session_id with NO matching Trip row through unchecked. That's
    # not the same "unrestricted" gray area shared/ownership.py has for
    # tourist_profiles (where legacy profiles can genuinely predate the
    # TripEvent ownership log) -- every real Layer 4 session_id is
    # created by /trips/{id}/confirm, which always sets
    # Trip.layer3_session_id in the same transaction. So a session_id
    # with no owning Trip at all is never a legitimate case here; it's
    # either a typo/garbage id or someone guessing, and should 404, not
    # fall through to "allowed."
    owner_id = (
        await db.execute(select(Trip.user_id).where(Trip.layer3_session_id == session_id).limit(1))
    ).scalar_one_or_none()
    if owner_id is None:
        raise HTTPException(404, "Session not found.")
    if owner_id != user.id:
        raise HTTPException(403, "This session does not belong to your account.")

    orch = getattr(request.app.state, "layer3", None)
    if orch is None:
        raise HTTPException(503, "Layer 3 session authority is unavailable")
    session = orch.get_session(session_id)
    return {
        "session_id": session_id,
        "status": session.get("status"),
        "current_slot_index": session.get("current_slot_index"),
        "wallet_remaining": session.get("wallet_remaining"),
        "queue": session.get("queue", []),
    }
