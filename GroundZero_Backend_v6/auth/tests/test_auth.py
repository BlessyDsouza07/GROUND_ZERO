import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("AUTH_SECRET_KEY", "x" * 48)

from auth import routes, security  # noqa: E402
from auth.models import User  # noqa: E402
from hive2 import models as hive2_models  # noqa: E402,F401


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all, tables=[User.__table__, hive2_models.ConsentRecord.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _db():
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def test_password_roundtrip():
    h = security.hash_password("correct horse")
    assert security.verify_password("correct horse", h)
    assert not security.verify_password("wrong", h)


def test_token_tamper_and_expiry():
    t = security.create_token("abc")
    assert security.decode_token(t) == "abc"
    assert security.decode_token(t[:-2] + "xx") is None
    assert security.decode_token(security.create_token("abc", ttl_seconds=-5)) is None


@pytest.mark.asyncio
async def test_register_login_me(client):
    r = await client.post("/auth/register", json={"email": "A@x.com", "password": "password1", "accepted_terms": True, "adult_confirmed": True})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "a@x.com"
    dup = await client.post("/auth/register", json={"email": "a@x.com", "password": "password1", "accepted_terms": True, "adult_confirmed": True})
    assert dup.status_code == 409
    bad = await client.post("/auth/login", json={"email": "a@x.com", "password": "nope-nope"})
    assert bad.status_code == 401
    ok = await client.post("/auth/login", json={"email": "a@x.com", "password": "password1", "accepted_terms": True, "adult_confirmed": True})
    tok = ok.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["email"] == "a@x.com"
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.post("/auth/register", json={"email": "bad", "password": "password1", "accepted_terms": True, "adult_confirmed": True})).status_code == 422
