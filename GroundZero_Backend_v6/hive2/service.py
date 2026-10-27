"""DB-backed pieces of HIVE 2: profile, consents, feedback, geofence state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import learning
from .geofence import PlaceState
from .models import ConsentRecord, ContentReport, GeofenceState, TravellerEvent, TravellerProfile
from .ranker import Profile

POLICY_VERSION = "2026-10-draft-1"
CONSENT_KINDS = ("terms", "adult", "location", "personalization", "photos")
FEEDBACK_KINDS = {"shown", "opened", "saved", "dismissed", "navigated", "visited", "rated"}
REASONS = {"not_interested", "closed", "no_time", "too_far", "seen_it", "other"}
ALLOWED_CONSTRAINT_KEYS = {"dietary", "accessibility", "accessibility_strict", "max_spend_per_place",
                           "companions", "kids", "avoid", "excluded_categories"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- consents ----------
async def get_consents(db: AsyncSession, uid: uuid.UUID) -> dict:
    rows = (await db.execute(select(ConsentRecord).where(ConsentRecord.user_id == uid))).scalars().all()
    out = {k: {"granted": False, "granted_at": None, "withdrawn_at": None, "policy_version": None} for k in CONSENT_KINDS}
    for r in rows:
        out[r.kind] = {"granted": bool(r.granted), "granted_at": r.granted_at.isoformat() if r.granted_at else None,
                       "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
                       "policy_version": r.policy_version}
    return out


async def has_consent(db: AsyncSession, uid: uuid.UUID, kind: str) -> bool:
    r = (await db.execute(select(ConsentRecord).where(ConsentRecord.user_id == uid, ConsentRecord.kind == kind))).scalar_one_or_none()
    return bool(r and r.granted)


async def set_consent(db: AsyncSession, uid: uuid.UUID, kind: str, granted: bool) -> dict:
    if kind not in CONSENT_KINDS:
        raise ValueError("unknown consent kind")
    r = (await db.execute(select(ConsentRecord).where(ConsentRecord.user_id == uid, ConsentRecord.kind == kind))).scalar_one_or_none()
    now = _now()
    if r is None:
        r = ConsentRecord(user_id=uid, kind=kind, granted=granted, policy_version=POLICY_VERSION,
                          granted_at=now if granted else None, withdrawn_at=None if granted else now)
        db.add(r)
    else:
        r.granted, r.policy_version = granted, POLICY_VERSION
        if granted:
            r.granted_at, r.withdrawn_at = now, None
        else:
            r.withdrawn_at = now
    if not granted and kind == "personalization":
        await wipe_personal_data(db, uid, keep_consents=True)   # withdrawing = memory is removed
    if not granted and kind == "location":
        await db.execute(delete(GeofenceState).where(GeofenceState.user_id == uid))
    await db.commit()
    return await get_consents(db, uid)


# ---------- profile ----------
async def _profile_row(db: AsyncSession, uid: uuid.UUID, create=True) -> Optional[TravellerProfile]:
    row = await db.get(TravellerProfile, uid)
    if row is None and create:
        row = TravellerProfile(user_id=uid, affinities={}, constraints={}, visited_place_ids=[], dismissed_place_ids=[])
        db.add(row)
        await db.flush()
    return row


async def load_profile(db: AsyncSession, uid: uuid.UUID, personalised: bool) -> Profile:
    if not personalised:
        return Profile()
    row = await _profile_row(db, uid, create=False)
    shown: dict = {}
    ev = (await db.execute(select(TravellerEvent.place_id).where(TravellerEvent.user_id == uid, TravellerEvent.kind == "shown"))).scalars().all()
    for pid in ev:
        shown[pid] = shown.get(pid, 0) + 1
    if row is None:
        return Profile(shown_counts=shown)
    return Profile(affinities=learning.decayed(row.affinities or {}), constraints=dict(row.constraints or {}),
                   visited=set(row.visited_place_ids or []), dismissed=set(row.dismissed_place_ids or []), shown_counts=shown)


async def profile_view(db: AsyncSession, uid: uuid.UUID) -> dict:
    row = await _profile_row(db, uid, create=False)
    cons = await get_consents(db, uid)
    if row is None:
        return {"affinities": {}, "constraints": {}, "visited_count": 0, "dismissed_count": 0, "consents": cons}
    return {"affinities": learning.decayed(row.affinities or {}), "constraints": row.constraints or {},
            "visited_count": len(row.visited_place_ids or []), "dismissed_count": len(row.dismissed_place_ids or []),
            "consents": cons}


async def update_profile(db: AsyncSession, uid: uuid.UUID, constraints: Optional[dict], stated: Optional[dict], remove: Optional[list]) -> dict:
    row = await _profile_row(db, uid)
    if constraints is not None:
        clean = {k: v for k, v in constraints.items() if k in ALLOWED_CONSTRAINT_KEYS}
        row.constraints = clean
    aff = dict(row.affinities or {})
    for key, w in (stated or {}).items():
        if key.startswith(("exp:", "cat:")):
            learning.set_stated(aff, key, float(w))
    for key in remove or []:
        aff.pop(key, None)
    row.affinities = aff
    row.version = (row.version or 1) + 1
    await db.commit()
    return await profile_view(db, uid)


async def wipe_personal_data(db: AsyncSession, uid: uuid.UUID, keep_consents: bool = True) -> None:
    await db.execute(delete(TravellerEvent).where(TravellerEvent.user_id == uid))
    await db.execute(delete(GeofenceState).where(GeofenceState.user_id == uid))
    await db.execute(delete(TravellerProfile).where(TravellerProfile.user_id == uid))
    if not keep_consents:
        await db.execute(delete(ConsentRecord).where(ConsentRecord.user_id == uid))
    await db.flush()


# ---------- feedback ----------
async def record_feedback(db: AsyncSession, uid: uuid.UUID, place, kind: str, reason: Optional[str], rating: Optional[int], context: Optional[dict]) -> dict:
    if kind not in FEEDBACK_KINDS:
        raise ValueError("unknown feedback kind")
    if reason is not None and reason not in REASONS:
        raise ValueError("unknown reason")
    safe_ctx = {k: v for k, v in (context or {}).items() if k in ("time_of_day", "with_kids", "mode", "weather") and isinstance(v, (str, bool, int, float))}
    db.add(TravellerEvent(user_id=uid, place_id=str(place.id), kind=kind, reason=reason, rating=rating, context=safe_ctx))
    row = await _profile_row(db, uid)
    aff = dict(row.affinities or {})
    learning.apply_event(aff, place, kind, reason, rating)
    row.affinities = aff
    if kind == "visited":
        row.visited_place_ids = sorted(set(row.visited_place_ids or []) | {str(place.id)})
    if kind == "dismissed" and reason in ("not_interested", "seen_it"):
        row.dismissed_place_ids = sorted(set(row.dismissed_place_ids or []) | {str(place.id)})
    await db.commit()
    return {"ok": True}


# ---------- geofence state ----------
async def load_states(db: AsyncSession, uid: uuid.UUID, place_ids: list[str]) -> dict:
    rows = (await db.execute(select(GeofenceState).where(GeofenceState.user_id == uid, GeofenceState.place_id.in_(place_ids)))).scalars().all()
    return {r.place_id: PlaceState(r.inside, r.entered_at, r.last_notified_at, r.notify_count) for r in rows}


async def save_states(db: AsyncSession, uid: uuid.UUID, states: dict) -> None:
    for pid, st in states.items():
        row = (await db.execute(select(GeofenceState).where(GeofenceState.user_id == uid, GeofenceState.place_id == pid))).scalar_one_or_none()
        if row is None:
            if not st.inside and not st.last_notified_at:
                continue
            db.add(GeofenceState(user_id=uid, place_id=pid, inside=st.inside, entered_at=st.entered_at,
                                 last_notified_at=st.last_notified_at, notify_count=st.notify_count))
        else:
            row.inside, row.entered_at, row.last_notified_at, row.notify_count = st.inside, st.entered_at, st.last_notified_at, st.notify_count
    await db.commit()


# ---------- reports ----------
async def add_report(db: AsyncSession, uid: uuid.UUID, kind: str, ref: str, reason: str, detail: Optional[str]) -> str:
    r = ContentReport(user_id=uid, target_kind=kind, target_ref=ref[:500], reason=reason, detail=(detail or "")[:1000], status="open")
    db.add(r)
    await db.commit()
    return str(r.id)
