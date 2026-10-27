"""Privacy, consent, data export, content reports, and the legal documents."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from auth.routes import get_db
from hive2 import service
from hive2.models import TravellerEvent

router = APIRouter(tags=["privacy"])
LEGAL_DIR = Path(__file__).resolve().parent.parent / "legal"
DOCS = {"privacy": "privacy_policy.md", "terms": "terms.md", "safety": "safety.md"}

EMERGENCY = [
    {"label": "All emergencies", "number": "112"}, {"label": "Ambulance", "number": "108"},
    {"label": "Police", "number": "100"}, {"label": "Tourist helpline", "number": "1363"},
    {"label": "Women's helpline", "number": "1091"},
]


@router.get("/legal/{doc}")
async def legal_doc(doc: str) -> dict:
    name = DOCS.get(doc)
    if not name:
        raise HTTPException(404, "Unknown document.")
    return {"doc": doc, "version": service.POLICY_VERSION, "markdown": (LEGAL_DIR / name).read_text(encoding="utf-8"),
            "draft": True}


@router.get("/safety")
async def safety() -> dict:
    return {"emergency": EMERGENCY, "markdown": (LEGAL_DIR / "safety.md").read_text(encoding="utf-8")}


@router.get("/privacy/consents")
async def consents(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"consents": await service.get_consents(db, user.id), "policy_version": service.POLICY_VERSION}


class ConsentIn(BaseModel):
    kind: Literal["location", "personalization", "photos"]   # terms/adult are given at sign-up
    granted: bool


@router.put("/privacy/consents")
async def put_consent(body: ConsentIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"consents": await service.set_consent(db, user.id, body.kind, body.granted), "policy_version": service.POLICY_VERSION}


@router.get("/privacy/export")
async def export(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Everything GroundZero holds about the person, as JSON."""
    out: dict = {"account": {"id": str(user.id), "email": user.email, "display_name": user.display_name},
                 "consents": await service.get_consents(db, user.id),
                 "personalisation": await service.profile_view(db, user.id)}
    evs = (await db.execute(select(TravellerEvent).where(TravellerEvent.user_id == user.id))).scalars().all()
    out["feedback_events"] = [{"place_id": e.place_id, "kind": e.kind, "reason": e.reason, "rating": e.rating,
                               "at": e.created_at.isoformat() if e.created_at else None} for e in evs]
    try:
        from personal.models import ContributionRecord, SavedPlace
        sp = (await db.execute(select(SavedPlace).where(SavedPlace.user_id == user.id))).scalars().all()
        out["saved_places"] = [{c.name: str(getattr(s, c.name)) for c in SavedPlace.__table__.columns} for s in sp]
        cr = (await db.execute(select(ContributionRecord).where(ContributionRecord.user_id == user.id))).scalars().all()
        out["contributions"] = [{c.name: str(getattr(s, c.name)) for c in ContributionRecord.__table__.columns} for s in cr]
    except Exception:
        out["saved_places"], out["contributions"] = [], []
    try:
        from trips.models import Trip
        tr = (await db.execute(select(Trip).where(Trip.user_id == user.id))).scalars().all()
        out["trips"] = [{c.name: str(getattr(t, c.name)) for c in Trip.__table__.columns} for t in tr]
    except Exception:
        out["trips"] = []
    return out


class ReportIn(BaseModel):
    target_kind: Literal["photo", "place", "tip", "story"]
    target_ref: str = Field(min_length=1, max_length=500)
    reason: Literal["privacy", "unsafe", "inaccurate", "inappropriate", "other"]
    detail: str | None = Field(default=None, max_length=1000)


@router.post("/privacy/report", status_code=201)
async def report(body: ReportIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rid = await service.add_report(db, user.id, body.target_kind, body.target_ref, body.reason, body.detail)
    return {"id": rid, "status": "open", "message": "Thanks. We'll review this. For immediate danger call 112."}
