"""
Test DB isolation (real bug, confirmed: tests were writing into the same
Postgres database as your dev server, with no separate test DB and no
cleanup — this is exactly how "HTTP Flow Test Kitchen" ended up as a real,
permanent row in your Master Data Core, winning real recommendation slots).

Two-part fix:

1. Every test now runs against DATABASE_URL's database name + "_test"
   (groundzero -> groundzero_test) instead of your dev database, set here
   BEFORE any test module or `main`/`shared.config` gets imported — both
   of those cache Settings via functools.lru_cache, so this only works if
   it happens first, which is why it's at module level in a ROOT
   conftest.py (pytest always loads conftest.py before collecting test
   files in that directory tree).

2. An autouse fixture truncates every app table after each test function
   that touches the DB — cheap for a schema this size, and doesn't
   require rewriting every existing test file to use a shared
   transaction-rollback fixture.

One-time setup (run once, on your machine, with Postgres already running):

    createdb -U groundzero groundzero_test
    # then run your normal migration command against it, e.g.:
    DATABASE_URL=postgresql+asyncpg://groundzero:groundzero@localhost:5432/groundzero_test alembic upgrade head

After that, `pytest` always targets groundzero_test — your dev database
(and whatever `python walkthrough.py` writes to it) is never touched by
the test suite again.
"""
from __future__ import annotations

import os
import re

# --- Part 1: repoint DATABASE_URL before anything else imports it ---
_default_dev_url = "postgresql+asyncpg://groundzero:groundzero@localhost:5432/groundzero"
_raw_url = os.environ.get("DATABASE_URL", _default_dev_url)

if not _raw_url.rstrip("/").endswith("_test"):
    _test_url = re.sub(r"/([^/]+)$", lambda m: f"/{m.group(1)}_test", _raw_url)
else:
    _test_url = _raw_url

os.environ["DATABASE_URL"] = _test_url
os.environ.setdefault("TEST_DATABASE_URL", _test_url)

import pytest  # noqa: E402


# --- Part 2: cleanup safety net for whatever a test actually writes ---
@pytest.fixture(autouse=True)
async def _truncate_app_tables_after_test():
    yield
    try:
        from layer0.infrastructure.db.session import Base, get_engine
    except Exception:
        return  # DB layer not importable in this test's context — nothing to clean up

    try:
        engine = get_engine()
        table_names = [t.name for t in Base.metadata.sorted_tables]
        if not table_names:
            return
        async with engine.begin() as conn:
            from sqlalchemy import text
            quoted = ", ".join(f'"{name}"' for name in table_names)
            await conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    except Exception:
        # Best-effort: a test that never touched the DB (no engine created
        # yet, DB not running for this particular test run) shouldn't fail
        # the whole suite over cleanup. DB-touching tests that genuinely
        # need Postgres up will already have failed on their own assertions
        # if it wasn't reachable.
        pass
