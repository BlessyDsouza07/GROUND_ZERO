"""
API-level tests using httpx.AsyncClient(transport=ASGITransport) against
the real app object (main.app). An architectural audit found 0% test
coverage on every routes.py/dependencies.py/schemas.py file across all
three layers — this is real, executable coverage of the HTTP layer, not
just the application/domain logic underneath it.

Uses httpx's ASGI transport directly rather than FastAPI's
TestClient/starlette TestClient: TestClient wraps each synchronous call
in its own thread-portal event loop, which caused a real, reproducible
"attached to a different loop" RuntimeError against this app's pooled
async SQLAlchemy engine (confirmed by hitting it directly — GET requests
that issued multiple queries per request failed while single-query
requests happened to succeed). ASGITransport runs entirely within
pytest-asyncio's single event loop per test, which is both correct for
testing an async app and avoids that class of bug entirely.

These tests require Postgres and Redis to actually be running —
consistent with this codebase's established pattern of live-verifying
DB-touching code rather than mocking the database away.
"""
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://groundzero:groundzero@localhost:5432/groundzero")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ["ADMIN_API_KEY"] = "test-admin-key-do-not-use-in-production"
# Same safety net auth/tests/test_auth.py uses: this file now calls
# /auth/register + /auth/login (see the auth_headers fixture below), and
# create_token needs AUTH_SECRET_KEY set — setdefault so a real .env value
# (if one happens to already be loaded) still wins.
os.environ.setdefault("AUTH_SECRET_KEY", "x" * 48)

from shared.config import get_settings  # noqa: E402

get_settings.cache_clear()

import main  # noqa: E402

ADMIN_KEY = "test-admin-key-do-not-use-in-production"


@pytest.fixture
async def client():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client):
    """SECURITY FIX (final-release-hardening pass, Oct 2026): every route
    this fixture is used against (/survey/*, /places/submissions) already
    required a signed-in user before this round — see layer1/api/
    routes.py's SECURITY NOTE — but this test file predated that and was
    never updated to send a bearer token, so it's been failing with 401
    since whichever earlier round added that auth requirement. Registers
    + logs in a throwaway user per test (unique email) and returns
    ready-to-use Authorization headers."""
    email = f"api-test-{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPass123!"
    await client.post("/auth/register", json={"email": email, "password": password, "accepted_terms": True, "adult_confirmed": True, "name": "API Test User"})
    login = await client.post("/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_endpoint_needs_no_auth(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_endpoint_without_key_returns_401(client):
    response = await client.get("/admin/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_with_wrong_key_returns_403(client):
    response = await client.get("/admin/stats", headers={"X-Admin-Api-Key": "wrong-key"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_endpoint_with_correct_key_succeeds(client):
    response = await client.get("/admin/stats", headers={"X-Admin-Api-Key": ADMIN_KEY})
    assert response.status_code == 200
    assert "total_places" in response.json()


@pytest.mark.asyncio
async def test_admin_pipeline_run_requires_auth(client):
    response = await client.post("/admin/pipeline/run")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_submissions_pending_requires_auth(client):
    response = await client.get("/admin/submissions/pending")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_approve_requires_auth(client):
    response = await client.post("/admin/submissions/some-id/approve", json={"reviewed_by": "someone"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_admin_api_key_setting_fails_closed(client, monkeypatch):
    """If ADMIN_API_KEY is unset, every admin request must be REJECTED,
    not silently allowed through with no auth — that's the exact bug
    this whole module exists to fix."""
    monkeypatch.setenv("ADMIN_API_KEY", "")
    get_settings.cache_clear()
    try:
        response = await client.get("/admin/stats", headers={"X-Admin-Api-Key": "anything"})
        assert response.status_code == 500
    finally:
        monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
        get_settings.cache_clear()


def test_openapi_schema_includes_all_expected_routes():
    schema = main.app.openapi()
    paths = set(schema["paths"].keys())
    expected = {
        "/health", "/places", "/places/submissions", "/places/{place_id}",
        "/admin/pipeline/run", "/admin/stats", "/admin/submissions/pending",
        "/admin/submissions/{submission_id}/approve", "/admin/submissions/{submission_id}/reject",
        "/survey/start", "/survey/{session_id}", "/survey/{session_id}/answer",
        "/survey/{session_id}/finalize", "/survey/group/{group_session_id}/members",
        "/hive/recommendations", "/hive/recommendations/multi-day",
    }
    missing = expected - paths
    assert not missing, f"Expected routes missing from the app: {missing}"


@pytest.mark.asyncio
async def test_survey_start_endpoint_works_end_to_end(client, auth_headers):
    response = await client.post("/survey/start", json={"device_id": "test-device"}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    # "opening_prompt" (not "q1_purpose") has been the real first step
    # since the "Talk to Your Guide" opener was added — see SurveyStep in
    # layer1/application/survey_service.py. This assertion was stale.
    assert body["current_step"] == "opening_prompt"
    assert body["is_complete"] is False


@pytest.mark.asyncio
async def test_places_list_endpoint_works(client):
    response = await client.get("/places")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_places_submission_endpoint_works(client, auth_headers):
    response = await client.post(
        "/places/submissions",
        json={
            "name": f"API Test Place {uuid.uuid4().hex[:8]}", "category": "cafe",
            "latitude": 12.9, "longitude": 74.85, "estimated_cost": 100,
            "price_band": "budget", "submitter_note": "an API-level test submission",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_nonexistent_place_returns_404(client):
    response = await client.get("/places/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_full_admin_moderation_flow_through_the_http_api(client, auth_headers):
    """Submit -> pending -> approve, entirely through real HTTP requests
    (not direct service calls), with real admin auth on the protected
    steps. This is the fullest HTTP-level proof the community pipeline
    actually works end-to-end through the API surface a client would
    really use."""
    unique_name = f"HTTP Flow Test Kitchen {uuid.uuid4().hex[:8]}"
    submit_response = await client.post(
        "/places/submissions",
        json={
            "name": unique_name, "category": "local_kitchen",
            "latitude": 12.88, "longitude": 74.85, "estimated_cost": 80,
            "price_band": "budget", "submitter_note": "full HTTP flow test",
        },
        headers=auth_headers,
    )
    assert submit_response.status_code == 201
    submission_id = submit_response.json()["id"]

    pending_response = await client.get("/admin/submissions/pending", headers={"X-Admin-Api-Key": ADMIN_KEY})
    assert pending_response.status_code == 200
    assert any(s["id"] == submission_id for s in pending_response.json())

    approve_response = await client.post(
        f"/admin/submissions/{submission_id}/approve",
        json={"reviewed_by": "http-flow-test"},
        headers={"X-Admin-Api-Key": ADMIN_KEY},
    )
    assert approve_response.status_code == 200
    body = approve_response.json()
    assert body["grade"] == "authentic"  # community default local_percentage clears the bar

    place_id = body["place_id"]
    place_response = await client.get(f"/places/{place_id}")
    assert place_response.status_code == 200
    assert place_response.json()["name"] == unique_name


@pytest.mark.asyncio
async def test_mark_visited_endpoint_fixes_return_visitor_check(client, auth_headers):
    """API-level proof of the visited_log fix: previously
    get_visited_place_ids had no write path anywhere in the codebase, so
    Return Visitor Check always resolved to an empty exclusion list in
    production. This exercises the real fix through the actual HTTP
    endpoint a client app would call."""
    start_response = await client.post(
        "/survey/start", json={"device_id": f"visited-test-{uuid.uuid4().hex[:8]}"}, headers=auth_headers
    )
    session_id = start_response.json()["session_id"]

    answers = [
        "foodie", "moderate", "fine", 1200, ["veg"], "solo", [],
        "authentic local food", "full_day", "morning", "english", False, "warm_local_friend",
    ]
    for answer in answers:
        await client.post(f"/survey/{session_id}/answer", json={"answer": answer}, headers=auth_headers)

    finalize_response = await client.post(f"/survey/{session_id}/finalize", headers=auth_headers)
    assert finalize_response.status_code == 200
    profile_id = finalize_response.json()["id"]

    mark_response = await client.post(
        f"/survey/profile/{profile_id}/visited", json={"place_ids": ["place-x", "place-y"]}, headers=auth_headers
    )
    assert mark_response.status_code == 200
    assert set(mark_response.json()["visited_place_ids"]) == {"place-x", "place-y"}
