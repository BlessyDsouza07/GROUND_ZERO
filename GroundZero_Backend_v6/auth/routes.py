from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete

from auth.models import User
from auth.security import create_token, decode_token, hash_password, verify_password
from layer0.infrastructure.db.session import get_session_factory

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def get_db():
    async with get_session_factory()() as session:
        yield session


async def _get_current_user_dep(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> User:
    """Thin wrapper that imports auth.dependencies.get_current_user
    lazily (module-level, at first call, not at import time) so this
    module and auth.dependencies — which imports `get_db` from here —
    don't form a circular import. FastAPI resolves this dependency
    graph the same as calling get_current_user directly."""
    from auth.dependencies import get_current_user

    return await get_current_user(authorization, db)


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class RegisterIn(Credentials):
    """Sign-up also needs two explicit confirmations (recorded with a
    timestamp): the person has read the Terms and Privacy Policy, and is 18+."""
    accepted_terms: bool = False
    adult_confirmed: bool = False


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, display_name=user.display_name)


def _clean_email(raw: str) -> str:
    email = raw.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    return email


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not body.accepted_terms:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please accept the Terms and Privacy Policy to create an account.")
    if not body.adult_confirmed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "GroundZero accounts are for people aged 18 or over.")
    email = _clean_email(body.email)
    user = User(email=email, password_hash=hash_password(body.password), display_name=body.display_name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    from hive2.service import set_consent
    await set_consent(db, user.id, "terms", True)
    await set_consent(db, user.id, "adult", True)
    return TokenOut(access_token=create_token(str(user.id)), user=_out(user))


@router.post("/login", response_model=TokenOut)
async def login(body: Credentials, db: AsyncSession = Depends(get_db)) -> TokenOut:
    email = _clean_email(body.email)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return TokenOut(access_token=create_token(str(user.id)), user=_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(_get_current_user_dep)) -> UserOut:
    # Audit fix: this used to re-implement bearer-token parsing + the
    # uuid.UUID(user_id) call inline instead of depending on the one
    # canonical auth.dependencies.get_current_user every other router
    # uses — two copies of the same logic that could silently drift
    # (and this copy was missing the malformed-token 500->401 guard
    # that get_current_user now has). Imported lazily below to avoid a
    # circular import (auth.dependencies imports get_db from this
    # module).
    return _out(user)


@router.delete("/me")
async def delete_account(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    """Settings -> Data -> Delete account. Distinct from logout (which
    doesn't touch any data). Trips/places/journal entries cascade via
    the ORM relationship on Trip (cascade="all, delete-orphan" in
    trips/models.py); trip_events and contribution_records have no such
    relationship (they're an honest standalone log / a submission
    record, not trip children) so they're cleared explicitly first to
    avoid a foreign-key violation on the user row itself."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")
    user_id = decode_token(authorization[7:].strip())
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists.")

    from sqlalchemy.orm import selectinload

    from trips.models import Trip, TripEvent
    from hive2.models import ConsentRecord, ContentReport, GeofenceState, TravellerEvent, TravellerProfile
    for model in (TravellerEvent, GeofenceState, TravellerProfile, ConsentRecord, ContentReport):
        await db.execute(delete(model).where(model.user_id == uid))
    try:
        from personal.models import ContributionRecord, SavedPlace
        await db.execute(delete(ContributionRecord).where(ContributionRecord.user_id == uid))
        # SECURITY/FEATURE FIX (final-release-hardening pass, Oct 2026):
        # saved_places didn't exist when this handler was written; cleared
        # explicitly for the same belt-and-suspenders reason as
        # contribution_records just above, even though its FK already has
        # ondelete="CASCADE".
        await db.execute(delete(SavedPlace).where(SavedPlace.user_id == uid))
    except ImportError:
        pass
    await db.execute(delete(TripEvent).where(TripEvent.user_id == uid))
    trips = (
        await db.execute(
            select(Trip).options(selectinload(Trip.places), selectinload(Trip.journal_entries))
            .where(Trip.user_id == uid)
        )
    ).scalars().all()
    for trip in trips:
        await db.delete(trip)
    await db.flush()
    await db.delete(user)
    await db.commit()
    return {"deleted": True}
