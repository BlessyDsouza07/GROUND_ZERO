# -*- coding: utf-8 -*-
"""
Layer 3 HTTP API (FastAPI).

Run standalone:   python run_layer3.py --serve            (default port 8004)
Mount elsewhere:  from layer3_api import router, attach_layer3
                  app.include_router(router); attach_layer3(app)

Interactive docs: http://localhost:8004/docs
"""
from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from layer3_config import LAYER3_VERSION, SERVICE_NAME, Settings, get_settings
from layer3_models import LayerError
from layer3_orchestrator import Layer3Orchestrator
from layer3_utils import get_logger

log = get_logger("layer3.api")

# SECURITY NOTE (audit response, Oct 2026): every /l3/* endpoint below
# used to have no user authentication at all — not even the shared
# X-API-Key middleware, which only `create_app()` wires in for the
# fully-standalone `run_layer3.py --serve` deployment; the COMBINED app
# (main.py, what the Flutter product actually talks to) mounts the bare
# `router` with none of that. Since this module is also imported in that
# standalone mode (its own sys.path, no `auth`/`trips` packages on it —
# see run_layer3.py), the imports below are defensive: in the combined
# app they resolve to the real thing; standalone, they fall back to a
# permissive no-op so isolated layer3 testing/demo usage (which has no
# `users` table to check against at all) keeps working exactly as
# before. This mirrors the same compromise already made for layer1's
# standalone app elsewhere in this codebase.
try:
    from auth.dependencies import get_current_user
    from auth.models import User
    from layer0.api.dependencies import get_db_session
    from trips.models import Trip
    from sqlalchemy import select

    _AUTH_AVAILABLE = True
except ImportError:  # standalone layer3 (run_layer3.py --serve), no combined app around it
    _AUTH_AVAILABLE = False

    class User:  # type: ignore[no-redef]
        id = None

    async def get_current_user() -> User:  # type: ignore[no-redef]
        log.warning(
            "layer3_api running without the combined app's `auth` package on sys.path — "
            "/l3/* endpoints are NOT authenticated in this standalone deployment."
        )
        return User()

    async def get_db_session():  # type: ignore[no-redef]
        yield None


async def _session_owner_user_id(db, session_id: str):
    """Returns the owning user's id for a layer3 session_id, by looking
    it up against `trips.models.Trip.layer3_session_id` (set once in
    trips/routes.py::confirm_trip, which is how the real Flutter product
    actually starts every layer3 session — it never calls
    POST /l3/session/start directly). Returns None if no Trip links to
    this session_id yet (e.g. a session started via this parallel public
    API rather than through /trips/{id}/confirm) — same "no record, no
    restriction beyond being signed in" trust boundary used elsewhere in
    this codebase (see shared/ownership.py)."""
    if not _AUTH_AVAILABLE:
        return None
    result = await db.execute(select(Trip.user_id).where(Trip.layer3_session_id == session_id).limit(1))
    return result.scalar_one_or_none()


async def _check_session_ownership_or_403(db, session_id: str, user: "User") -> None:
    if not _AUTH_AVAILABLE:
        return
    owner_id = await _session_owner_user_id(db, session_id)
    if owner_id is not None and owner_id != user.id:
        raise LayerError("This session does not belong to your account.", 403, "forbidden")


# ---------------------------------------------------------------------------
# request models
# ---------------------------------------------------------------------------
class StartSessionBody(BaseModel):
    profile_id: Optional[str] = Field(None, description="Layer 1 profile id (loaded from Layer 1's profiles folder / API)")
    profile: Optional[Dict[str, Any]] = Field(None, description="Inline TouristProfile (alternative to profile_id)")
    itinerary: Optional[Any] = Field(None, description="Layer 2 CompleteItinerary JSON. If omitted, Layer 3 calls POST {layer2}/hive/generate")
    queue: Optional[List[Dict[str, Any]]] = Field(None, description="Already-flattened slot queue (role + place_id per slot)")
    session_id: Optional[str] = None
    device_id: Optional[str] = None
    language: Optional[str] = Field(None, description="en | kn | kok | hi (defaults to the profile's companion_language)")
    voice: Optional[str] = Field(None, description="warm | historian | witty")
    group_session_id: Optional[str] = None
    wallet_remaining: Optional[int] = None


class QueueBody(BaseModel):
    queue: Optional[List[Dict[str, Any]]] = None
    itinerary: Optional[Any] = None


class StateBody(BaseModel):
    status: Optional[str] = Field(None, description="survey | active | paused | ended_early | completed")
    energy_band: Optional[str] = Field(None, description="low | medium | high (mid-trip mood check-in)")
    wallet_remaining: Optional[int] = None
    language: Optional[str] = None
    voice: Optional[str] = None
    group_session_id: Optional[str] = None
    now: Optional[str] = None


class PingBody(BaseModel):
    session_id: str
    lat: float
    lng: float
    accuracy_m: Optional[float] = None
    speed_mps: Optional[float] = None
    timestamp: Optional[str] = None


class EvaluateBody(BaseModel):
    session_id: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy_m: Optional[float] = None
    speed_mps: Optional[float] = None
    timestamp: Optional[str] = None
    manual_trigger: bool = Field(False, description="The tourist tapped 'I'm here' — bypasses ONLY the geofence trigger")
    target_place_id: Optional[str] = None
    recent_pings: Optional[List[Dict[str, Any]]] = Field(None, description="Optional location history [{lat,lng,timestamp,accuracy_m?,speed_mps?}]")
    dry_run: bool = Field(False, description="Evaluate without persisting anything (simulation)")
    now: Optional[str] = Field(None, description="ISO time override — honoured only if LAYER3_ALLOW_TIME_OVERRIDE=true")
    energy_band: Optional[str] = None
    visited_place_ids: Optional[List[str]] = None


class NotifBody(BaseModel):
    session_id: str
    notification_id: str
    action: str = "tapped"


class TellMoreBody(BaseModel):
    session_id: str
    notification_id: Optional[str] = None
    place_id: Optional[str] = None
    language: Optional[str] = None


class AskBody(BaseModel):
    question: str
    session_id: Optional[str] = None
    place_id: Optional[str] = None
    language: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class QuietBody(BaseModel):
    session_id: str
    minutes: Optional[float] = Field(None, description="0 / null clears Quiet Hours")


class SosBody(BaseModel):
    session_id: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class VisitBody(BaseModel):
    session_id: str
    place_id: str
    arrived_at: Optional[str] = None
    exited_at: Optional[str] = None
    dwell_minutes: Optional[float] = None
    satisfaction: Optional[str] = Field(None, description="up | down | skip")


class UnavailableBody(BaseModel):
    place_id: str
    unavailable: bool = True
    reason: str = ""
    ttl_hours: Optional[float] = None
    # reported_by deliberately removed (5th audit response, Oct 2026):
    # this used to be a client-supplied string accepted as-is and
    # written straight into the report record -- an authenticated
    # caller could claim to be reporting on behalf of anyone. The
    # reporting identity is never something the client gets to assert;
    # see report_unavailable() below, which now uses str(user.id) from
    # the verified bearer token instead.


class AdvisoryBody(BaseModel):
    title: str
    severity: str = "warning"
    area: Optional[str] = None
    ttl_hours: Optional[float] = 12


# ---------------------------------------------------------------------------
# wiring
# ---------------------------------------------------------------------------
def get_orch(request: Request) -> Layer3Orchestrator:
    orch = getattr(request.app.state, "layer3", None)
    if orch is None:
        orch = Layer3Orchestrator()
        request.app.state.layer3 = orch
    return orch


def attach_layer3(app: FastAPI, orchestrator: Optional[Layer3Orchestrator] = None) -> Layer3Orchestrator:
    """For a host app (e.g. a future combined server): call once at start-up."""
    app.state.layer3 = orchestrator or Layer3Orchestrator()
    return app.state.layer3


def _is_loopback(host: Optional[str]) -> bool:
    if not host:
        return False
    if host in ("localhost", "testclient"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_admin(request: Request, x_admin_token: Optional[str] = Header(None)) -> None:
    token = get_orch(request).s.admin_token
    if token:
        if x_admin_token != token:
            raise LayerError("Admin token required (X-Admin-Token header)", 403, "admin_required")
    elif not _is_loopback(request.client.host if request.client else None):
        raise LayerError("Admin endpoints are limited to localhost unless LAYER3_ADMIN_TOKEN is set", 403, "admin_required")


router = APIRouter(prefix="/l3", tags=["Layer 3 — Context / Silence / Ask"])


# SECURITY (audit response, Oct 2026): every endpoint below now requires
# a signed-in user (`user`), and every one that takes a `session_id`
# checks it against the owning Trip via `_check_session_ownership_or_403`
# (see that function's docstring above for exactly what it can and can't
# verify). In standalone layer3 deployments (`_AUTH_AVAILABLE` False)
# both checks are no-ops, unchanged from before this pass.
#
# SECURITY FIX (final-release-hardening pass, Oct 2026): POST
# /l3/session/start is now additionally gated behind `require_admin`
# (the same X-Admin-Token / loopback-only guard already used for
# /l3/safety/advisory below). The real Flutter product never calls this
# HTTP endpoint at all — trips/routes.py::confirm_trip starts every real
# session by calling the orchestrator in-process and stamping the result
# onto Trip.layer3_session_id, which is how /l3/session/{id} and every
# other endpoint below can enforce ownership in the first place. Before
# this fix, this endpoint had no ownership check (by necessity — a brand
# new session has no owning Trip yet) and only required *being* signed
# in, not being the right caller: any authenticated tourist could mint an
# arbitrary number of Layer 3 sessions from an arbitrary profile_id or
# inline profile that wasn't theirs, each one a full live-guidance
# session with no Trip record and so no ownership check ever applying to
# it again. Restricting it to admin/service callers closes that without
# touching the real tourist flow, which never goes through here.


# ---- sessions ---------------------------------------------------------------------
@router.post(
    "/session/start",
    summary="[internal/admin] Start a Layer 3 session directly from a Layer 1 profile + Layer 2 itinerary",
    dependencies=[Depends(require_admin)],
)
async def session_start(
    body: StartSessionBody, request: Request,
    user: User = Depends(get_current_user),
    o: Layer3Orchestrator = Depends(get_orch),
):
    # No ownership check possible here: this mints a brand-new session_id
    # with no Trip row pointing to it yet (see this module's docstring
    # above). Gated to admin/service callers by `require_admin` above —
    # the real tourist flow starts sessions via POST /trips/{id}/confirm,
    # which never reaches this HTTP endpoint (see the SECURITY FIX note
    # above `router = APIRouter(...)`).
    result = o.start_session(**body.model_dump())
    supervisor = getattr(request.app.state, "layer4", None)
    if supervisor is not None and result.get("status") == "active":
        supervisor.start(result["session_id"])
    return result


@router.get("/session/{session_id}", summary="Session state incl. the slot queue")
async def session_get(
    session_id: str, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, session_id, user)
    return o.get_session(session_id)


@router.put("/session/{session_id}/queue", summary="Layer 4 syncs the authoritative queue (Pace Coach / Resume Evaluation)")
async def session_queue(
    session_id: str, body: QueueBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, session_id, user)
    return o.set_queue(session_id, itinerary=body.itinerary, queue=body.queue)


@router.put("/session/{session_id}/state", summary="Pause / resume / end, mood-check energy, wallet, language, voice")
async def session_state(
    session_id: str, body: StateBody, request: Request,
    user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, session_id, user)
    result = o.update_state(session_id, **body.model_dump())
    supervisor = getattr(request.app.state, "layer4", None)
    status = result.get("status")
    if supervisor is not None:
        if status == "active":
            supervisor.start(session_id)
        elif status in {"paused", "ended_early", "completed"}:
            supervisor.stop(session_id)
    return result


# ---- location + the decision ---------------------------------------------------------
@router.post("/location/ping", summary="Store a GPS ping (needed for the 'stopped for 2 minutes' check)")
async def location_ping(
    body: PingBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.ping(**body.model_dump())


@router.post("/context/evaluate", summary="THE decision: should the app speak now? (Tier A + Tier B + Silence Filter)")
async def context_evaluate(
    body: EvaluateBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    d = body.model_dump()
    sid = d.pop("session_id")
    await _check_session_ownership_or_403(db, sid, user)
    return o.evaluate(sid, **d)


@router.get("/conditions", summary="Live weather / tide / events / advisories snapshot")
def conditions(lat: float, lng: float, place_id: Optional[str] = None, o: Layer3Orchestrator = Depends(get_orch)):
    # Deliberately left public: a read-only weather/tide/events snapshot
    # for a lat/lng, no session, profile, or user data involved.
    return o.conditions(lat, lng, place_id)


# ---- notification feedback --------------------------------------------------------------
@router.post("/notify/dismiss", summary="Tourist dismissed a notification (feeds the fatigue gap)")
async def notify_dismiss(
    body: NotifBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.dismiss(body.session_id, body.notification_id)


@router.post("/notify/engage", summary="Tourist engaged with a notification (resets the dismissal streak)")
async def notify_engage(
    body: NotifBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.engage(body.session_id, body.notification_id, body.action)


@router.post("/notify/tell-more", summary="Tell me more — exactly one stored Wikipedia/Wikidata sentence")
async def notify_tell_more(
    body: TellMoreBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.tell_more(body.session_id, body.notification_id, body.place_id, body.language)


# ---- Ask Engine ------------------------------------------------------------------------------
@router.post("/ask", summary="Ask Engine — answers ONLY from the place's stored record (+ live data for 'right now' questions)")
async def ask(
    body: AskBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    if body.session_id:
        await _check_session_ownership_or_403(db, body.session_id, user)
    return o.ask(body.question, session_id=body.session_id, place_id=body.place_id, language=body.language, lat=body.lat, lng=body.lng)


# ---- controls -----------------------------------------------------------------------------------
@router.post("/quiet", summary="Quiet Hours — mute for N minutes (0 clears). Only safety can break through.")
async def quiet(
    body: QuietBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.set_quiet(body.session_id, body.minutes)


@router.post("/sos", summary="Manual SOS / Help button (safety source #3)")
async def sos(
    body: SosBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    # Signed-in + same ownership check as every other session_id
    # endpoint here — a safety-sensitive action must not be an
    # unauthenticated state mutation (the exact gap an audit flagged).
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.sos(body.session_id, body.lat, body.lng)


@router.post("/sos/clear", summary="Clear an SOS state")
async def sos_clear(
    body: SosBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    return o.clear_sos(body.session_id)


@router.post("/visit", summary="Record a visit (arrival/exit/dwell/👍👎). Marks the slot visited and frees the geofence lock")
async def visit(
    body: VisitBody, user: User = Depends(get_current_user), db=Depends(get_db_session),
    o: Layer3Orchestrator = Depends(get_orch),
):
    await _check_session_ownership_or_403(db, body.session_id, user)
    d = body.model_dump()
    sid, pid = d.pop("session_id"), d.pop("place_id")
    return o.record_visit(sid, pid, **d)


@router.get("/visits/{device_id}", summary="Places a device has visited (for Layer 1's Return Visitor check)")
async def visits(device_id: str, user: User = Depends(get_current_user), o: Layer3Orchestrator = Depends(get_orch)):
    # Signed-in required; no per-device ownership model exists yet to
    # check further (device_id isn't linked to a user anywhere in this
    # schema) — tracked as a roadmap item, not silently ignored.
    return o.visits_for_device(device_id)


@router.post("/place/report-unavailable", summary="Community report: place closed / reopened (Layer 3 overlay only)")
async def report_unavailable(body: UnavailableBody, user: User = Depends(get_current_user), o: Layer3Orchestrator = Depends(get_orch)):
    # BUG FIX (5th audit response, Oct 2026): reported_by now always
    # comes from the verified bearer token (str(user.id)), never from
    # the request body -- see UnavailableBody's comment above.
    return o.report_place_unavailable(body.place_id, body.unavailable, body.reason, str(user.id), body.ttl_hours)


@router.post("/safety/advisory", summary="[admin] Publish a local-authority advisory (safety source #2 mirror)", dependencies=[Depends(require_admin)])
def add_advisory(body: AdvisoryBody, o: Layer3Orchestrator = Depends(get_orch)):
    return o.add_advisory(body.title, body.severity, body.area, body.ttl_hours)


@router.delete("/safety/advisory/{advisory_id}", summary="[admin] Clear an advisory", dependencies=[Depends(require_admin)])
def clear_advisory(advisory_id: int, o: Layer3Orchestrator = Depends(get_orch)):
    return o.clear_advisory(advisory_id)


@router.get("/health", summary="Health check (DB, master data core, Redis, LLM)")
def health(o: Layer3Orchestrator = Depends(get_orch)):
    return o.health()


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith(self.DOC_PATHS):   # Swagger UI needs its CDN assets — no CSP there
            resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return resp


class ApiKeyMiddleware(BaseHTTPMiddleware):
    OPEN = ("/health", "/healthcheck", "/docs", "/redoc", "/openapi.json", "/l3/health")

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.method != "OPTIONS" and not request.url.path.startswith(self.OPEN):
            if request.headers.get("x-api-key") != self.api_key:
                return JSONResponse({"error": {"code": "unauthorized", "message": "Missing or invalid X-API-Key"}}, status_code=401)
        return await call_next(request)


def create_app(orchestrator: Optional[Layer3Orchestrator] = None, settings: Optional[Settings] = None) -> FastAPI:
    s = settings or (orchestrator.s if orchestrator else get_settings())
    app = FastAPI(title="Ground Zero — Layer 3 (Context Engine + Silence Filter + Ask Engine)", version=LAYER3_VERSION,
                  description="Decides when the app speaks (and when it stays silent), delivers the companion voice, answers grounded questions.")
    if orchestrator is not None:
        app.state.layer3 = orchestrator
    if s.api_key:
        app.add_middleware(ApiKeyMiddleware, api_key=s.api_key)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=list(s.cors_origins), allow_methods=["*"], allow_headers=["*"],
                       allow_credentials=False)

    @app.exception_handler(LayerError)
    async def _layer_error(_: Request, exc: LayerError):
        return JSONResponse({"error": {"code": exc.code, "message": str(exc)}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse({"error": {"code": "validation_error", "message": "Invalid request",
                                       "details": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]}}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return JSONResponse({"error": {"code": "internal_error", "message": "Internal server error"}}, status_code=500)

    app.include_router(router)

    # root-level aliases, consistent with Layer 1's /status and /healthcheck
    @app.get("/health", include_in_schema=False)
    @app.get("/healthcheck", include_in_schema=False)
    def _health(request: Request):
        return get_orch(request).health()

    @app.get("/status", include_in_schema=False)
    def _status(request: Request):
        h = get_orch(request).health()
        return {"service": SERVICE_NAME, "version": LAYER3_VERSION, "status": h["status"], "master_data_core": h["master_data_core"]}

    return app


def asgi() -> FastAPI:  # `uvicorn layer3_api:asgi --factory --port 8004`
    return create_app()
