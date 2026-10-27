"""HIVE 2 HTTP API. Auth required. Personalisation and location features
only work when the person has consented; without consent HIVE still answers
(non-personalised) and stores nothing about them."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.models import User
from auth.routes import get_db
from explore.hours import open_info
from layer0.application.opening_hours_parser import OpeningHoursParser
from layer0.domain.repositories import PlaceRepository
from layer2.api.dependencies import get_place_repository

from . import service
from .experience import classify
from .geofence import evaluate
from .intent import parse_intent
from .ranker import Context, rank, order_route

logger = logging.getLogger("groundzero.hive2")
router = APIRouter(prefix="/hive", tags=["hive2"])
IST = ZoneInfo("Asia/Kolkata")
_PARSER = OpeningHoursParser()
MANGALURU = (12.9141, 74.8560)


def _open_fn(p, now):
    i = open_info(p, _PARSER, now)
    return i.state, i.source, i.label


class PlanIn(BaseModel):
    text: str = Field(default="", max_length=400)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    mode: Optional[Literal["surprise", "slow", "less_touristy"]] = None
    minutes: Optional[int] = Field(default=None, ge=10, le=720)
    limit: int = Field(default=6, ge=1, le=10)
    rain: Optional[bool] = None
    temp_c: Optional[float] = Field(default=None, ge=-10, le=55)


def _card(s, route_index: Optional[int] = None) -> dict:
    k, ev = s.k, s.k.evidence
    return {
        "place_id": k.place_id, "name": k.name, "category": k.category, "lat": k.lat, "lng": k.lon,
        "role": s.role, "distance_km": s.dist_km, "travel_min": s.travel_min,
        "open_state": s.open_state, "open_label": s.open_label, "open_source": s.open_source,
        "experiences": [{"key": e, "strength": v, "basis": k.experience_basis.get(e)} for e, v in sorted(k.experiences.items(), key=lambda x: -x[1])],
        "why": s.reasons, "caveats": s.caveats,
        "less_touristy_evidence": s.less_touristy_evidence, "hidden_gem": s.hidden_gem,
        "evidence": {
            "confidence": s.confidence_label, "verification": ev.verification, "verification_note": ev.verification_note,
            "sources": ev.sources, "authenticity_basis": ev.authenticity_basis, "commercial_signals": ev.commercial_signals,
            "crowd": ev.crowd, "kid_friendly": ev.kid_friendly, "wheelchair": ev.wheelchair,
            "dwell_minutes": ev.dwell_minutes, "price_band": ev.price_band, "etiquette": ev.etiquette,
        },
        "scores": s.components,
        "stop": route_index,
    }


@router.post("/plan")
async def plan(body: PlanIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
               repo: PlaceRepository = Depends(get_place_repository)) -> dict:
    personalised = await service.has_consent(db, user.id, "personalization")
    profile = await service.load_profile(db, user.id, personalised)
    intent = parse_intent(body.text)
    now = datetime.now(IST)
    ctx = Context(lat=body.lat if body.lat is not None else MANGALURU[0], lon=body.lng if body.lng is not None else MANGALURU[1],
                  now=now, minutes=body.minutes or intent.minutes, rain=body.rain, temp_c=body.temp_c,
                  mode=body.mode, limit=body.limit, intent=intent)
    places = await repo.list_all()
    res = rank(places, ctx, profile, _open_fn)
    route = order_route(res.items, ctx)
    cards = [_card(s, i + 1) for i, s in enumerate(route)]
    if personalised and cards:
        # impressions are logged as impressions only (never as likes)
        from .models import TravellerEvent
        for c in cards:
            db.add(TravellerEvent(user_id=user.id, place_id=c["place_id"], kind="shown", context={"time_of_day": f"{now.hour:02d}h", "mode": body.mode or intent.mode or ""}))
        await db.commit()
    return {
        "understood": res.understood, "message": res.message, "cards": cards,
        "personalised": personalised and not profile.cold,
        "located": body.lat is not None,
        "constraints_relaxed": [],           # constraints are never silently loosened
        "dropped": dict(sorted(res.dropped.items(), key=lambda kv: -kv[1])[:6]),
        "generated_at": now.isoformat(),
        "note": "Rankings use fixed, explainable rules, not a trained model. Hours marked 'typical' are not confirmed.",
    }


class FeedbackIn(BaseModel):
    place_id: str = Field(max_length=64)
    kind: Literal["shown", "opened", "saved", "dismissed", "navigated", "visited", "rated"]
    reason: Optional[Literal["not_interested", "closed", "no_time", "too_far", "seen_it", "other"]] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    context: Optional[dict] = None


@router.post("/feedback")
async def feedback(body: FeedbackIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                   repo: PlaceRepository = Depends(get_place_repository)) -> dict:
    if not await service.has_consent(db, user.id, "personalization"):
        return {"ok": True, "stored": False, "detail": "Personalisation is off, so nothing was saved."}
    place = await repo.get_by_id(body.place_id)
    if place is None:
        place = next((p for p in await repo.list_all() if str(p.id) == body.place_id), None)
    if place is None:
        raise HTTPException(404, "Place not found.")
    out = await service.record_feedback(db, user.id, place, body.kind, body.reason, body.rating, body.context)
    return {**out, "stored": True}


@router.get("/profile")
async def get_profile(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return await service.profile_view(db, user.id)


class ProfileUpdateIn(BaseModel):
    constraints: Optional[dict] = None
    stated: Optional[dict[str, float]] = None
    remove: Optional[list[str]] = None


@router.put("/profile")
async def put_profile(body: ProfileUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    if not await service.has_consent(db, user.id, "personalization"):
        raise HTTPException(409, "Turn on personalisation first to save preferences.")
    return await service.update_profile(db, user.id, body.constraints, body.stated, body.remove)


@router.delete("/profile")
async def delete_profile(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    await service.wipe_personal_data(db, user.id, keep_consents=True)
    await db.commit()
    return {"deleted": True}


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, le=100000)
    quiet: bool = False


@router.post("/location")
async def location(body: LocationIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                   repo: PlaceRepository = Depends(get_place_repository)) -> dict:
    """Foreground check-in. Coordinates are used for this one decision and
    are NOT stored."""
    if not await service.has_consent(db, user.id, "location"):
        raise HTTPException(409, "Location consent is off.")
    profile = await service.load_profile(db, user.id, await service.has_consent(db, user.id, "personalization"))
    now = datetime.now(IST)
    places = await repo.list_all()
    near = []
    deg = 0.0035  # ~390 m box
    for p in places:
        c = p.coordinates
        if abs(c.latitude - body.lat) > deg or abs(c.longitude - body.lng) > deg:
            continue
        k = classify(p, now)
        if k.role == "utility" or p.category == "uncategorized":
            continue
        st = _open_fn(p, now)[0]
        near.append((str(p.id), p.name, c.latitude, c.longitude, st, str(p.id) in profile.visited or str(p.id) in profile.dismissed))
    states = await service.load_states(db, user.id, [n[0] for n in near])
    res = evaluate(near, body.lat, body.lng, body.accuracy_m, states, now, quiet=body.quiet)
    await service.save_states(db, user.id, states)
    n = res["notify"]
    out = {"reason": res["reason"], "notify": None}
    if n:
        p = next(p for p in places if str(p.id) == n["place_id"])
        k = classify(p, now)
        top = max(k.experiences, key=k.experiences.get, default=None)
        out["notify"] = {**n, "category": p.category, "title": f"You're near {n['name']}",
                         "body": (f"{n['name']} is right here" + (f" — good for {top.replace('_', ' ')}." if top else ".")),
                         "caveat": "Opening hours are typical, not confirmed." if _open_fn(p, now)[1] != "listed" else None}
    return out


@router.get("/events")
async def events(days: int = 7) -> dict:
    """Living events. 'confirmed' only when the source record is active and was
    re-verified in the last 7 days. Nothing is inferred from last year."""
    days = max(1, min(days, 30))
    try:
        import live_events.app.main as m
        from live_events.app.models import Event
    except Exception:
        return {"events": [], "note": "Events feed not available."}
    db = m.SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.query(Event).filter(Event.start_at >= now - timedelta(hours=3), Event.start_at < now + timedelta(days=days),
                                      Event.status == "ACTIVE").order_by(Event.start_at.asc()).limit(40).all()
        out = []
        for e in rows:
            lv = e.last_verified_at
            if lv is not None and lv.tzinfo is None:
                lv = lv.replace(tzinfo=timezone.utc)
            confirmed = bool(e.source_url) and e.start_at is not None and lv is not None and (now - lv) <= timedelta(days=7)
            out.append({"id": e.id, "title": e.title, "start_at": e.start_at.isoformat() if e.start_at else None,
                        "venue": e.venue, "address": e.address, "source_url": e.source_url,
                        "last_verified_at": lv.isoformat() if lv else None,
                        "status": "confirmed" if confirmed else "tentative"})
        return {"events": out, "note": "Tentative = not re-verified recently. Check the source before you travel."}
    except Exception:
        logger.exception("events read failed")
        return {"events": [], "note": "Events feed temporarily unavailable."}
    finally:
        db.close()
