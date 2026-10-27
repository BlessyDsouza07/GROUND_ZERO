"""Shared "who is making this request" dependency, factored out of
auth/routes.py's /me handler so other routers (trips/routes.py) can
require a signed-in user without re-implementing bearer-token parsing."""
from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User
from auth.security import decode_token
from auth.routes import get_db


async def get_current_user(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")
    user_id = decode_token(authorization[7:].strip())
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        # Audit fix: a malformed/tampered token whose `sub` claim isn't a
        # real UUID used to blow up uuid.UUID() uncaught -> an unhandled
        # 500 instead of the 401 a bad-credentials case should return.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists.")
    return user
