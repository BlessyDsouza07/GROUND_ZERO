"""
Ground Zero — combined backend entrypoint.

Runs Layers 0, 1, 2, 3 and 5, plus the Live Mangaluru Events module, as one
FastAPI application (one Postgres database, per blueprint Table 12), while
each layer's code remains independently organized and independently
testable/runnable (see layer0/main.py, layer1/main.py, layer2/main.py,
layer3/run_layer3.py for standalone per-layer apps used in isolated
development/testing).

Layer 3 and the Live Events module are each mounted defensively: if either
fails to import (e.g. a dependency genuinely missing from the environment),
the rest of the app still starts, and /health reports exactly what did and
didn't come up — a broken add-on layer should never take down Layers 0-2/5.

Run with: uvicorn main:app --reload
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from auth.routes import router as auth_router
from layer0.api.admin import router as layer0_admin_router
from layer0.api.routes import router as layer0_places_router
from layer0.api.security_middleware import add_security_middleware
from layer1.api.routes import router as layer1_survey_router
from layer2.api.feedback_routes import router as layer2_itinerary_feedback_router
from layer2.api.routes import router as layer2_hive_router
from layer5.api.routes import router as layer5_companion_router
from layer4.api import router as layer4_router
from layer4.supervisor import Layer4Supervisor
from trips.routes import router as trips_router
from explore.routes import router as explore_router
from guide.routes import router as guide_router
from media.routes import router as media_router
from hive2.routes import router as hive2_router
from privacy.routes import router as privacy_router
from personal.routes import router as personal_router
from shared.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("groundzero.main")

settings = get_settings()

# Layer 3 reads GROQ_API_KEY etc. straight from os.environ (it only loads its
# OWN layer3/.env). pydantic's env_file never exports to os.environ either, so
# a key placed in the backend's root .env was invisible to Layer 3. Export the
# root .env here (real environment variables still win: override=False).
try:
    from dotenv import load_dotenv as _load_root_env

    _load_root_env(Path(__file__).resolve().parent / ".env", override=False)
except Exception:  # pragma: no cover - never block startup on this
    logger.warning("Could not export root .env into the process environment")

REPO_ROOT = Path(__file__).resolve().parent

# --- Layer 3 wiring --------------------------------------------------------
# layer3/*.py use flat, non-package imports by design (`from layer3_config
# import ...`, matching its standalone `cd layer3 && python run_layer3.py
# --serve` usage documented in layer3/README.md) — this is the supported
# way to host it inside another app (see layer3/layer3_api.py's own
# module docstring: "Mount elsewhere: from layer3_api import router,
# attach_layer3"), so we add layer3/ to sys.path rather than editing its
# imports to be relative.
sys.path.insert(0, str(REPO_ROOT / "layer3"))

# LAYER1_BASE_URL / LAYER2_BASE_URL default to layer3_config.py's own
# fully-separated-microservices ports (8002/8003), which don't exist in
# this combined deployment — Layers 0/1/2/5 all run on this one app.
# Setting these (only if not already set) BEFORE layer3_config.Settings()
# is first constructed points Layer 3's Layer1Client/Layer2Client at this
# same app instead. GROUNDZERO_BASE_URL overrides both at once if this app
# is deployed behind a different host/port.
_gz_base_url = os.environ.get("GROUNDZERO_BASE_URL", "http://localhost:8000")
os.environ.setdefault("LAYER1_BASE_URL", _gz_base_url)
os.environ.setdefault("LAYER2_BASE_URL", _gz_base_url)
# Layer 1 persists profiles in Postgres, not JSON files, and its /survey
# router has no plain GET /profile/{id} — bridge the already-resolved DB URL
# so layer3_bridge.ProfileStore can read `tourist_profiles` directly instead
# of relying only on that dead HTTP route (psycopg's sync driver needs a
# plain postgresql:// scheme, not SQLAlchemy's +asyncpg one).
os.environ.setdefault(
    "LAYER3_POSTGRES_DSN",
    settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://"),
)

layer3_available = False
try:
    from layer3_api import attach_layer3
    from layer3_api import router as layer3_router
    from layer3_models import LayerError as Layer3Error

    from integration.layer2_layer3_bridge import router as layer2_layer3_bridge_router
    from scripts.export_layer3_master_core import export_layer3_master_core

    layer3_available = True
except Exception:  # pragma: no cover - defensive: Layer 3 must never block Layers 0/1/2/5
    logger.exception("Layer 3 failed to import — the app will start WITHOUT it (see /health)")

# --- Live Mangaluru Events wiring ------------------------------------------
events_available = False
try:
    import live_events.app.main as events_app_module
    from scripts.export_layer3_events_cache import export_layer3_events_cache

    events_available = True
except Exception:  # pragma: no cover - defensive: same policy as Layer 3 above
    logger.exception("Live Events module failed to import — the app will start WITHOUT it (see /health)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Layer 0's real export -> the flattened shape Layer 3's bridge code
    # reads (see scripts/export_layer3_master_core.py for exactly why this
    # is needed: Layer 0 nests coordinates/bias/accessibility one level
    # deeper than Layer 3's field readers look for). Cheap (~700 places);
    # safe to just re-run on every boot so it's always in sync with
    # data/master_data_core.json.
    if layer3_available:
        try:
            stats = export_layer3_master_core()
            logger.info("Layer 3 master-data bridge refreshed: %s", stats)
        except FileNotFoundError as exc:
            logger.warning(
                "%s — Layer 3 will report zero places until data/master_data_core.json "
                "exists (run import_master_data.py / the ETL pipeline first).",
                exc,
            )
        except Exception:
            logger.exception("Layer 3 master-data bridge export failed (non-fatal)")

    if events_available:
        # Reuses the Live Events module's OWN lifespan unmodified (DB init,
        # seed, APScheduler start/shutdown) — see live_events/app/main.py.
        # Starlette does not auto-propagate a mounted sub-app's lifespan,
        # so it's driven explicitly here rather than relying on app.mount().
        async with events_app_module.lifespan(events_app_module.app):
            try:
                stats = export_layer3_events_cache()
                logger.info("Layer 3 events-cache bridge refreshed: %s", stats)
            except Exception:
                logger.exception("Layer 3 events-cache bridge export failed (non-fatal)")
            if layer3_available:
                # Keep Layer 3's nearby_events signal in sync with whatever
                # the Events module's own scheduler refreshes, on the same
                # scheduler instance it already started above. First run is
                # a couple minutes out (giving the initial real scrape —
                # triggered immediately above via next_run_time — a chance
                # to land first), then every 20 minutes thereafter.
                events_app_module.scheduler.add_job(
                    export_layer3_events_cache,
                    "interval",
                    minutes=20,
                    id="layer3-events-cache-sync",
                    replace_existing=True,
                    next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
                )
            yield
    else:
        yield


app = FastAPI(
    title="Ground Zero",
    description=(
        "A Human-Centric & Necessity-Driven Intelligence for Tourism — "
        "Layers 0, 1, 2, 3, 4, 5 + Live Mangaluru Events."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Layer 4 is the live-trip supervisor. It is deliberately in-process so the
# project remains runnable from VS Code with one uvicorn process; Redis remains
# available for future multi-worker coordination.
app.state.layer4 = Layer4Supervisor()

# Inbound rate limiting (security audit finding: this app previously had
# no rate limiting protecting its OWN API — only the reactive handling
# ResilientHttpClient does for calls this app makes outbound to external
# services). Per-client-IP, applies globally; see shared.config.Settings
# .rate_limit_per_minute to tune it.
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS (security audit finding: previously allow_origins=["*"]
# unconditionally, with a "tighten before production" comment that was
# never acted on). "*" is only accepted in development; anywhere else,
# CORS_ALLOWED_ORIGINS must be set to a real comma-separated origin list,
# or the app refuses to start with permissive CORS silently.
_cors_origins_raw = settings.cors_allowed_origins.strip()
if _cors_origins_raw == "*":
    if settings.environment != "development":
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS is '*' but ENVIRONMENT is not 'development' — refusing to start "
            "with wide-open CORS outside development. Set CORS_ALLOWED_ORIGINS to a real "
            "comma-separated list of allowed origins."
        )
    _cors_origins = ["*"]
    logger.warning("CORS is wide open (allow_origins=['*']) — acceptable in development only.")
else:
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

def _root_causes(exc: BaseException):
    seen, stack = set(), [exc]
    while stack:
        e = stack.pop()
        if id(e) in seen:
            continue
        seen.add(id(e))
        yield e
        stack.extend(x for x in (e.__cause__, e.__context__) if x is not None)
        stack.extend(getattr(e, "exceptions", ()) or ())


@app.middleware("http")
async def _json_error_guard(request: Request, call_next):
    """Turn unhandled exceptions into JSON responses that still pass through
    CORSMiddleware (added right after this, so it wraps this). Starlette's
    default 500 is produced OUTSIDE CORS and carries no
    Access-Control-Allow-Origin header, so a browser app (Flutter web)
    reports any server-side crash as a generic network failure
    ("can't reach the server") instead of showing the real problem."""
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        causes = list(_root_causes(exc))
        names = {type(c).__name__ for c in causes}
        text = " ".join(str(c) for c in causes)
        if ("does not exist" in text and ("relation" in text or "table" in text)) or "no such table" in text:
            return JSONResponse({"detail": "The database has no tables yet. Run: alembic upgrade head"}, status_code=503)
        if "AUTH_SECRET_KEY" in text:
            return JSONResponse({"detail": "The server is missing AUTH_SECRET_KEY. Add it to the backend .env file and restart."}, status_code=500)
        if names & {"ConnectionRefusedError", "OperationalError", "InterfaceError", "CannotConnectNowError"} or any(
            isinstance(c, OSError) for c in causes
        ):
            return JSONResponse(
                {"detail": "GroundZero's database isn't running. Start it (docker compose up -d in the backend folder) and try again."},
                status_code=503,
            )
        return JSONResponse({"detail": "Something went wrong on the server. Please try again."}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 2: Add security middleware (request validation, headers, input sanitization)
add_security_middleware(app)

app.include_router(auth_router)
app.include_router(layer0_places_router)
app.include_router(layer0_admin_router)
app.include_router(layer1_survey_router)
app.include_router(layer2_hive_router)
app.include_router(layer2_itinerary_feedback_router)
# Bug fixed: Layer 5 (chatbot, geofencing, multilingual, voice guide) had
# no router at all and was never included here, so none of it was ever
# reachable over HTTP despite the classes existing. See
# layer5/api/routes.py's module docstring for the full story.
app.include_router(layer5_companion_router)
app.include_router(layer4_router)
app.include_router(trips_router)
app.include_router(explore_router)
app.include_router(personal_router)
app.include_router(guide_router)
app.include_router(media_router)
app.include_router(hive2_router)
app.include_router(privacy_router)

if layer3_available:
    app.include_router(layer3_router)  # prefix "/l3" — Context Engine / Silence Filter / Ask Engine
    app.include_router(layer2_layer3_bridge_router)  # additive POST /hive/generate alias, see integration/layer2_layer3_bridge.py
    attach_layer3(app)
    app.state.layer4.orchestrator = app.state.layer3

    @app.exception_handler(Layer3Error)
    async def _layer3_error_handler(_: Request, exc: Layer3Error) -> JSONResponse:
        # Mirrors layer3_api.create_app()'s own handler so /l3/* errors keep
        # the same {"error": {"code", "message"}} shape whether Layer 3 runs
        # standalone (python run_layer3.py --serve) or mounted here.
        return JSONResponse({"error": {"code": exc.code, "message": str(exc)}}, status_code=exc.status_code)

if events_available:
    # A full, separate FastAPI app (its own DB, scheduler, routes) mounted
    # under one prefix. Its own routes are unprefixed (/health, /events,
    # /events/today, /events/upcoming, /events/itinerary-safe, /events/{id},
    # /sources, /admin/refresh) so mounted here they become e.g.
    # /events-live/events/today. CORS/rate-limiting/security headers added
    # to `app` below still apply (Starlette middleware wraps the whole
    # ASGI pipeline, including dispatch into mounted sub-apps).
    app.mount("/events-live", events_app_module.app)


@app.get("/health")
async def health() -> dict:
    layers = ["layer0", "layer1", "layer2", "layer4", "layer5"]
    if layer3_available:
        layers.append("layer3")
    if events_available:
        layers.append("live_events")
    return {
        "status": "ok",
        "layers": layers,
        "layer3_available": layer3_available,
        "live_events_available": events_available,
    }
