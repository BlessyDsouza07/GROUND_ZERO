import os
from pathlib import Path
from dotenv import load_dotenv

# This module is mounted inside the combined Ground Zero backend (see
# ../../main.py), which has its own top-level `.env` and its own
# (differently-typed, asyncpg/Postgres) DATABASE_URL. Two fixes keep this
# module's settings from ever being confused with that one, matching the
# isolation convention the previous live_events module used:
#   1. EVENTS_ prefix -- this module's env vars are EVENTS_DATABASE_URL,
#      EVENTS_ADMIN_API_KEY, etc., never the bare names main.py's own
#      config (shared/config.py) reads.
#   2. The .env file is anchored to THIS module's own directory (not the
#      process cwd), so `uvicorn main:app` run from the repo root reads
#      live_events/.env, not the repo root .env. override=False (the
#      load_dotenv default) means this never clobbers a real environment
#      variable the process was already started with.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE)

# SECURITY FIX (final-release-hardening pass, Oct 2026): an audit found
# two production-readiness gaps here, both silent: EVENTS_DATABASE_URL
# falling back to a local SQLite file with no warning, and
# EVENTS_ADMIN_API_KEY falling back to the literal string
# "change-this-before-deployment" — a real, guessable admin key that
# would protect admin_refresh (see main.py) in name only if a deployment
# ever forgot to set the real one. Both now fail closed outside explicit
# local development, mirroring main.py's own CORS_ALLOWED_ORIGINS="*"
# check and layer3_config.py's identical SQLite-fallback fix: ENVIRONMENT
# (shared with the combined app's own .env, since this module is mounted
# inside that same process) defaults to "development", where both
# fallbacks still work exactly as before for local/test use; anything
# else must set both explicitly or refuse to start.
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_explicit_database_url = os.getenv("EVENTS_DATABASE_URL")
if _explicit_database_url:
    DATABASE_URL = _explicit_database_url
elif ENVIRONMENT == "development":
    DATABASE_URL = "sqlite:///./live_events/data_output/groundzero_events.db"
else:
    raise RuntimeError(
        "EVENTS_DATABASE_URL is not set and ENVIRONMENT is not 'development' "
        f"(got '{ENVIRONMENT}') — refusing to fall back to a local SQLite file "
        "in production. Set EVENTS_DATABASE_URL to a real Postgres URL."
    )

ADMIN_API_KEY = os.getenv("EVENTS_ADMIN_API_KEY")
if not ADMIN_API_KEY:
    if ENVIRONMENT == "development":
        ADMIN_API_KEY = "change-this-before-deployment"  # loudly fake — dev/test only, never a real secret
    else:
        raise RuntimeError(
            "EVENTS_ADMIN_API_KEY is not set and ENVIRONMENT is not 'development' "
            f"(got '{ENVIRONMENT}') — refusing to run with the well-known default "
            "admin key in production. Set EVENTS_ADMIN_API_KEY to a real secret."
        )
REFRESH_INTERVAL_MINUTES = int(os.getenv("EVENTS_REFRESH_INTERVAL_MINUTES", "30"))
MAX_EVENT_AGE_HOURS = int(os.getenv("EVENTS_MAX_EVENT_AGE_HOURS", "36"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("EVENTS_REQUEST_TIMEOUT_SECONDS", "20"))
USER_AGENT = os.getenv("EVENTS_USER_AGENT", "GroundZeroEvents/1.0 (+project contact required)")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_FILE = os.path.join(BASE_DIR, "data", "sources.json")
