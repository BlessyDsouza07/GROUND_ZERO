"""
Ground Zero — Layer 3 (Context Engine + Silence Filter + Ask Engine)
Configuration.

Every tunable lives in the `Settings` dataclass. Values come from (highest first):
  1. explicit constructor overrides (used by the tests)
  2. environment variables (LAYER3_*, GROQ_*, REDIS_URL ...)
  3. a `.env` file next to this file
  4. the defaults below

Nothing in here imports any other Ground Zero layer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:  # python-dotenv is a listed dependency, but never crash if it is missing
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

LAYER3_ROOT = Path(__file__).resolve().parent
if load_dotenv is not None:
    load_dotenv(LAYER3_ROOT / ".env", override=False)

SERVICE_NAME = "ground-zero-layer3"
LAYER3_VERSION = "3.0.0"
DEFAULT_PORT = 8004  # Layer 1 = 8002, Layer 2 = 8003, Layer 3 = 8004

# ---------------------------------------------------------------------------
# Static vocabulary (blueprint-defined, not env-tunable)
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = ("en", "kn", "kok", "hi")
SUPPORTED_VOICES = ("warm", "historian", "witty")
ENERGY_BANDS = ("low", "medium", "high")

# Blueprint Section 6.1 — Tier B signals and their default weights (sum = 1.0).
# If a signal is not applicable (e.g. tide for an inland place) or its data
# source is down, it is dropped and the remaining weights are re-normalised.
TIER_B_WEIGHTS: Dict[str, float] = {
    "time_of_day": 0.14,
    "weather": 0.14,
    "crowd_level": 0.13,
    "energy_compatibility": 0.13,
    "mood_compatibility": 0.10,
    "season_day_type": 0.06,
    "tide_state": 0.12,
    "nearby_events": 0.09,
    "dwell_history": 0.09,
}

# Hour-of-day suitability per category: (start_hour, end_hour, score)
TIME_SUITABILITY: Dict[str, List[Tuple[float, float, float]]] = {
    "SPIRITUAL": [(5, 11, 1.0), (11, 16, 0.6), (16, 20, 0.95), (20, 24, 0.3), (0, 5, 0.2)],
    "NATURE": [(6, 10, 1.0), (10, 16, 0.6), (16, 19.5, 1.0), (19.5, 24, 0.15), (0, 6, 0.15)],
    "EXPLORE": [(8, 17, 1.0), (17, 19, 0.7), (19, 24, 0.25), (0, 8, 0.3)],
    "SHOPPING": [(10, 20, 1.0), (8, 10, 0.5), (20, 22, 0.5), (22, 24, 0.1), (0, 8, 0.1)],
    "LOCAL_LIFE": [(6, 11, 1.0), (11, 20, 0.85), (20, 22, 0.5), (22, 24, 0.2), (0, 6, 0.3)],
    "EVENTS": [(8, 22, 0.9), (22, 24, 0.5), (0, 8, 0.4)],
    "FOOD": [(7, 10.5, 1.0), (10.5, 12, 0.6), (12, 15, 1.0), (15, 16, 0.5),
             (16, 18, 0.8), (18, 19, 0.6), (19, 22, 1.0), (22, 24, 0.3), (0, 7, 0.2)],
    "DEFAULT": [(8, 20, 0.9), (20, 22, 0.5), (22, 24, 0.2), (0, 8, 0.3)],
}

# Mangaluru seasons (month -> season)
SEASON_BY_MONTH = {
    6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon",
    10: "post_monsoon", 11: "post_monsoon",
    12: "winter", 1: "winter", 2: "winter",
    3: "summer", 4: "summer", 5: "summer",
}

# Fixed-date public holidays that matter for crowd estimation (festivals with
# moving dates come from the live events cache instead).
FIXED_HOLIDAYS = {(1, 26), (5, 1), (8, 15), (10, 2), (11, 1), (12, 25)}

SEVERE_WEATHER_CODES = {95, 96, 99}           # WMO thunderstorm codes
RAIN_WEATHER_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
DRIZZLE_WEATHER_CODES = {51, 53, 55, 56, 57}

BIG_EVENT_KEYWORDS = (
    "festival", "jatre", "jatra", "utsav", "utsava", "mela", "procession", "rathotsava",
    "ratotsava", "dasara", "dussehra", "kambala", "kambla", "carnival", "fair", "urs",
    "feast", "mahotsav", "marathon", "concert",
)

ADVISORY_SEVERITY_KEYWORDS = (
    "red alert", "orange alert", "warning", "cyclone", "flood", "tsunami", "high wave",
    "storm surge", "thunderstorm", "landslide", "heavy rain", "swell surge", "advisory",
)
ADVISORY_REGION_KEYWORDS_DEFAULT = (
    "mangalore", "mangaluru", "dakshina kannada", "udupi", "coastal karnataka",
    "karnataka", "karavali", "kanara",
)

TTS_LOCALE = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN", "kok": "hi-IN"}  # kok: no widely-available voice, Devanagari read by hi-IN


# ---------------------------------------------------------------------------
# env helpers
# ---------------------------------------------------------------------------
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on", "y")


def _first_existing(*candidates: Optional[Path]) -> Optional[Path]:
    for c in candidates:
        if c is not None and Path(c).exists():
            return Path(c)
    return None


def _discover_master_core() -> Path:
    explicit = _env("LAYER0_MASTER_CORE_PATH")
    if explicit:
        return Path(explicit)
    parent = LAYER3_ROOT.parent
    found = _first_existing(
        parent / "layer0_fixed" / "data_output" / "master_data_core.json",
        parent / "layer0" / "data_output" / "master_data_core.json",
        parent / "data" / "master_data_core.json",
        parent / "data_output" / "master_data_core.json",
    )
    return found or (parent / "layer0_fixed" / "data_output" / "master_data_core.json")


def _discover_layer0_dir(master_core: Path) -> Path:
    explicit = _env("LAYER0_DATA_DIR")
    return Path(explicit) if explicit else master_core.parent


def _discover_layer0_db(l0_dir: Path) -> Path:
    explicit = _env("LAYER0_DB_PATH")
    return Path(explicit) if explicit else l0_dir / "ground_zero.db"


def _discover_profiles_dir() -> Path:
    explicit = _env("LAYER1_PROFILES_DIR")
    if explicit:
        return Path(explicit)
    parent = LAYER3_ROOT.parent
    found = _first_existing(
        parent / "layer1" / "data_output" / "profiles",
        parent / "layer1_fixed" / "data_output" / "profiles",
    )
    return found or (parent / "layer1" / "data_output" / "profiles")


def _default_db_url() -> str:
    # SECURITY FIX (final-release-hardening pass, Oct 2026): an audit
    # found Layer 3 silently falling back to a local SQLite file whenever
    # LAYER3_DATABASE_URL wasn't set — including in a real production
    # deployment of the combined app, since nothing here ever checked
    # which environment it was running in. SQLite in production means no
    # concurrent-worker safety (same reasoning as RedisSurveySessionStore
    # vs. InMemorySurveySessionStore's own docstring) and a session store
    # that isn't actually backed up or monitored like the rest of the
    # stack. Mirrors the fail-closed pattern main.py already uses for
    # CORS_ALLOWED_ORIGINS="*": SQLite is fine — expected, even — for
    # ENVIRONMENT=development (the default, and what layer3's own
    # standalone test/dev usage needs with no Postgres around at all),
    # but anything else must set LAYER3_DATABASE_URL explicitly or refuse
    # to start, rather than quietly becoming the single-worker, no-backup
    # SQLite file none of production's tooling knows about.
    explicit = _env("LAYER3_DATABASE_URL")
    if explicit:
        return explicit

    environment = _env("ENVIRONMENT", "development")
    if environment != "development":
        raise RuntimeError(
            "LAYER3_DATABASE_URL is not set and ENVIRONMENT is not 'development' "
            f"(got '{environment}') — refusing to fall back to a local SQLite file "
            "in production. Set LAYER3_DATABASE_URL to a real Postgres URL."
        )

    if _env_bool("LAYER3_SHARE_GROUND_ZERO_DB", False):
        return "sqlite:///" + str(_discover_layer0_db(_discover_layer0_dir(_discover_master_core())).as_posix())
    return "sqlite:///" + (LAYER3_ROOT / "data_output" / "layer3.db").as_posix()


@dataclass(frozen=True)
class Settings:
    # --- service -----------------------------------------------------------
    host: str = field(default_factory=lambda: _env("LAYER3_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("LAYER3_PORT", DEFAULT_PORT))
    timezone: str = field(default_factory=lambda: _env("LAYER3_TIMEZONE", "Asia/Kolkata"))
    default_language: str = field(default_factory=lambda: _env("LAYER3_DEFAULT_LANGUAGE", "en"))
    log_level: str = field(default_factory=lambda: _env("LAYER3_LOG_LEVEL", "INFO"))
    api_key: Optional[str] = field(default_factory=lambda: _env("LAYER3_API_KEY"))
    admin_token: Optional[str] = field(default_factory=lambda: _env("LAYER3_ADMIN_TOKEN"))
    cors_origins: Tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in (_env("LAYER3_CORS_ORIGINS", "*") or "*").split(",") if o.strip())
    )
    allow_time_override: bool = field(default_factory=lambda: _env_bool("LAYER3_ALLOW_TIME_OVERRIDE", False))

    # --- storage -----------------------------------------------------------
    database_url: str = field(default_factory=_default_db_url)
    data_output_dir: Path = field(default_factory=lambda: Path(_env("LAYER3_DATA_OUTPUT_DIR", str(LAYER3_ROOT / "data_output"))))

    # --- upstream layers (read-only) ----------------------------------------
    master_core_path: Path = field(default_factory=_discover_master_core)
    layer0_data_dir: Path = field(default_factory=lambda: _discover_layer0_dir(_discover_master_core()))
    layer0_db_path: Path = field(default_factory=lambda: _discover_layer0_db(_discover_layer0_dir(_discover_master_core())))
    layer1_profiles_dir: Path = field(default_factory=_discover_profiles_dir)
    layer1_base_url: str = field(default_factory=lambda: _env("LAYER1_BASE_URL", "http://localhost:8002"))
    # DSN for ProfileStore's direct, read-only fallback into Layer 1's own
    # `tourist_profiles` table when mounted inside the monolith (see
    # layer3_bridge.ProfileStore._from_postgres). Bridged from main.py's
    # already-resolved settings.database_url — never set by hand.
    postgres_dsn: Optional[str] = field(default_factory=lambda: _env("LAYER3_POSTGRES_DSN"))
    layer2_base_url: str = field(default_factory=lambda: _env("LAYER2_BASE_URL", "http://localhost:8003"))
    upstream_timeout_s: float = field(default_factory=lambda: _env_float("LAYER3_UPSTREAM_TIMEOUT_S", 20.0))
    use_layer0_db_flags: bool = field(default_factory=lambda: _env_bool("LAYER3_USE_LAYER0_DB_FLAGS", True))

    # --- redis (optional; Layer 4 workers write, Layer 3 reads) ----------------
    redis_url: Optional[str] = field(default_factory=lambda: _env("REDIS_URL"))
    redis_prefix: str = field(default_factory=lambda: _env("LAYER3_REDIS_PREFIX", "gz"))
    redis_max_age_s: int = field(default_factory=lambda: _env_int("LAYER3_REDIS_MAX_AGE_S", 900))

    # --- live data sources (all free, no key) -----------------------------------
    open_meteo_url: str = field(default_factory=lambda: _env("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"))
    open_meteo_marine_url: str = field(default_factory=lambda: _env("OPEN_METEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine"))
    live_http_timeout_s: float = field(default_factory=lambda: _env_float("LAYER3_LIVE_HTTP_TIMEOUT_S", 6.0))
    weather_cache_ttl_s: int = field(default_factory=lambda: _env_int("LAYER3_WEATHER_TTL_S", 300))
    tide_cache_ttl_s: int = field(default_factory=lambda: _env_int("LAYER3_TIDE_TTL_S", 900))
    live_tide_cache_file: str = field(default_factory=lambda: _env("LAYER3_TIDE_CACHE_FILE", "live_tide_cache.json"))
    live_events_cache_file: str = field(default_factory=lambda: _env("LAYER3_EVENTS_CACHE_FILE", "live_events_cache.json"))
    advisory_feed_url: Optional[str] = field(default_factory=lambda: _env("LAYER3_ADVISORY_FEED_URL"))
    advisory_cache_ttl_s: int = field(default_factory=lambda: _env_int("LAYER3_ADVISORY_TTL_S", 600))
    advisory_max_age_h: int = field(default_factory=lambda: _env_int("LAYER3_ADVISORY_MAX_AGE_H", 24))
    advisory_region_keywords: Tuple[str, ...] = field(
        default_factory=lambda: tuple(k.strip().lower() for k in (_env("LAYER3_ADVISORY_REGIONS") or ",".join(ADVISORY_REGION_KEYWORDS_DEFAULT)).split(",") if k.strip())
    )
    severe_rain_mm_h: float = field(default_factory=lambda: _env_float("LAYER3_SEVERE_RAIN_MM_H", 20.0))
    severe_gust_kmh: float = field(default_factory=lambda: _env_float("LAYER3_SEVERE_GUST_KMH", 70.0))
    thunder_lookahead_h: int = field(default_factory=lambda: _env_int("LAYER3_THUNDER_LOOKAHEAD_H", 1))
    event_radius_m: float = field(default_factory=lambda: _env_float("LAYER3_EVENT_RADIUS_M", 1500.0))

    # --- LLM (Ask Engine) -----------------------------------------------------
    llm_provider: str = field(default_factory=lambda: (_env("LAYER3_LLM_PROVIDER", "groq") or "groq").lower())  # groq | none
    groq_api_key: Optional[str] = field(default_factory=lambda: _env("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.1-8b-instant"))
    groq_base_url: str = field(default_factory=lambda: _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    llm_timeout_s: float = field(default_factory=lambda: _env_float("LAYER3_LLM_TIMEOUT_S", 20.0))
    llm_max_tokens: int = field(default_factory=lambda: _env_int("LAYER3_LLM_MAX_TOKENS", 260))
    voice_use_llm: bool = field(default_factory=lambda: _env_bool("LAYER3_VOICE_USE_LLM", False))
    ask_max_question_chars: int = 500

    # --- geofence / Silence Filter (Blueprint §6) ---------------------------------
    geofence_radius_m: float = field(default_factory=lambda: _env_float("LAYER3_GEOFENCE_RADIUS_M", 300.0))
    place_boundary_m: float = field(default_factory=lambda: _env_float("LAYER3_PLACE_BOUNDARY_M", 60.0))
    place_release_m: float = field(default_factory=lambda: _env_float("LAYER3_PLACE_RELEASE_M", 120.0))
    retry_after_s: int = field(default_factory=lambda: _env_int("LAYER3_RETRY_AFTER_S", 90))
    fatigue_gap_min: int = field(default_factory=lambda: _env_int("LAYER3_FATIGUE_GAP_MIN", 8))
    fatigue_gap_after_dismissals_min: int = field(default_factory=lambda: _env_int("LAYER3_FATIGUE_GAP_LONG_MIN", 15))
    dismissal_streak: int = 2
    movement_max_kmh: float = field(default_factory=lambda: _env_float("LAYER3_MOVEMENT_MAX_KMH", 1.0))
    movement_window_s: int = field(default_factory=lambda: _env_int("LAYER3_MOVEMENT_WINDOW_S", 120))
    movement_max_ping_age_s: int = field(default_factory=lambda: _env_int("LAYER3_MOVEMENT_MAX_PING_AGE_S", 90))
    movement_jitter_cap_m: float = 25.0
    tier_b_threshold: float = field(default_factory=lambda: _env_float("LAYER3_TIER_B_THRESHOLD", 0.75))
    tier_b_min_signals: int = field(default_factory=lambda: _env_int("LAYER3_TIER_B_MIN_SIGNALS", 5))
    enforce_open_hours: bool = field(default_factory=lambda: _env_bool("LAYER3_ENFORCE_OPEN_HOURS", False))
    safety_repeat_min: int = field(default_factory=lambda: _env_int("LAYER3_SAFETY_REPEAT_MIN", 10))
    group_ping_fresh_min: int = field(default_factory=lambda: _env_int("LAYER3_GROUP_PING_FRESH_MIN", 10))
    ping_retention_min: int = 240

    # --- replan -----------------------------------------------------------------
    replan_max_distance_km: float = field(default_factory=lambda: _env_float("LAYER3_REPLAN_MAX_KM", 4.0))
    replan_min_freshness: float = 0.0
    place_flag_ttl_h: int = field(default_factory=lambda: _env_int("LAYER3_PLACE_FLAG_TTL_H", 12))

    def with_overrides(self, **kw) -> "Settings":
        return replace(self, **kw)

    def public_dict(self) -> dict:
        """Safe-to-return view (no secrets)."""
        return {
            "host": self.host, "port": self.port, "timezone": self.timezone,
            "database_url": _redact(self.database_url),
            "master_core_path": str(self.master_core_path),
            "layer0_data_dir": str(self.layer0_data_dir),
            "layer1_profiles_dir": str(self.layer1_profiles_dir),
            "layer1_base_url": self.layer1_base_url, "layer2_base_url": self.layer2_base_url,
            "redis_enabled": bool(self.redis_url),
            "llm_provider": self.llm_provider, "groq_model": self.groq_model,
            "groq_key_configured": bool(self.groq_api_key),
            "advisory_feed_configured": bool(self.advisory_feed_url),
            "geofence_radius_m": self.geofence_radius_m, "tier_b_threshold": self.tier_b_threshold,
            "fatigue_gap_min": self.fatigue_gap_min, "movement_max_kmh": self.movement_max_kmh,
            "api_key_required": bool(self.api_key),
        }


def _redact(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        return scheme + "://***@" + rest.split("@", 1)[1]
    return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
