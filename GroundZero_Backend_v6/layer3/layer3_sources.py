"""
Layer 3 live signal sources.

Read order for every signal (fast -> slow), matching Blueprint §8.1
("the Context Engine reads from cache, not from a live API at the moment a tourist walks up"):

    1. Redis            — written by Layer 4's background workers (optional)
    2. Layer 0 caches   — live_tide_cache.json / live_events_cache.json in Layer 0's data_output/
    3. Live free API    — Open-Meteo (weather + marine), optional advisory RSS/Atom/CAP feed
    4. SourceUnavailable — recorded honestly as a data gap; NEVER a fake "all clear"

Redis key contract (all values are JSON strings; `gz` is LAYER3_REDIS_PREFIX):
    gz:weather:current        -> weather snapshot (schema below)
    gz:tide:<place_id>        -> tide snapshot     {wave_height_m, tide_state, safe_for_swimming, fetched_at}
    gz:events:current         -> [{title, start, end, lat, lng, place, ...}]
    gz:crowd:<place_id>       -> {"level": "low|medium|high", "fetched_at": iso}

Weather snapshot schema (what Layer 3 itself produces, and what Layer 4 workers should write):
    {temperature_c, precipitation_mm, weather_code, wind_kmh, gust_kmh, is_day,
     is_rainy, is_drizzle, is_severe, severe_reason, severe_soon, outdoor_suitable,
     fetched_at, source}
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from layer3_config import (
    BIG_EVENT_KEYWORDS, DRIZZLE_WEATHER_CODES, FIXED_HOLIDAYS, RAIN_WEATHER_CODES,
    SEVERE_WEATHER_CODES, ADVISORY_SEVERITY_KEYWORDS, Settings,
)
from layer3_models import SourceUnavailable
from layer3_repository import AbstractLayer3Repository
from layer3_utils import (
    TTLCache, as_list, clamp, find_first, get_logger, haversine_m, hour_float, is_weekend, num,
    normalize_crowd_level, parse_dt, pget, place_category, place_id_of, place_latlng, place_name_of,
    place_tags, season_of, to_local, utcnow, iso,
)

log = get_logger("layer3.sources")

_COASTAL_RE = re.compile(r"\b(beach|beaches|coast|coastal|seashore|shore|seafront|sea face|harbou?r|estuary|backwaters?|lighthouse|tide)\b")


def is_coastal(place: Dict[str, Any]) -> bool:
    """Tide-dependent? Uses the explicit `tide_dependency` flag when the record has one,
    otherwise infers from name / subcategory / tags."""
    td = place.get("tide_dependency")
    if isinstance(td, bool):
        return td
    if isinstance(td, str) and td.strip().lower() in ("true", "1", "yes", "false", "0", "no"):
        return td.strip().lower() in ("true", "1", "yes")
    hay = " ".join([place_name_of(place), str(place.get("subcategory") or "")] + place_tags(place)).lower()
    return bool(_COASTAL_RE.search(hay))


# ---------------------------------------------------------------------------
# Redis (optional)
# ---------------------------------------------------------------------------
class RedisCache:
    def __init__(self, url: Optional[str], prefix: str, max_age_s: int):
        self.prefix = prefix
        self.max_age_s = max_age_s
        self._r = None
        self.enabled = False
        self._warned = False
        if url:
            try:
                import redis  # type: ignore
                self._r = redis.Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=1.5, decode_responses=True)
                self._r.ping()
                self.enabled = True
                log.info("Redis cache connected")
            except Exception as e:
                self._r = None
                log.warning("Redis configured but unreachable (%s) — continuing without it", e.__class__.__name__)

    def get_json(self, key: str) -> Any:
        if not self.enabled or self._r is None:
            return None
        try:
            raw = self._r.get(f"{self.prefix}:{key}")
            if not raw:
                return None
            val = json.loads(raw)
        except Exception as e:
            if not self._warned:
                log.warning("Redis read failed (%s) — falling back", e.__class__.__name__)
                self._warned = True
            return None
        fetched = parse_dt(val.get("fetched_at")) if isinstance(val, dict) else None
        if fetched and (utcnow() - fetched).total_seconds() > self.max_age_s:
            return None  # stale
        return val

    def set_json(self, key: str, value: Any, ttl_s: int = 900) -> None:
        if not self.enabled or self._r is None:
            return
        try:
            self._r.set(f"{self.prefix}:{key}", json.dumps(value, default=str), ex=ttl_s)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
class SignalSources:
    def __init__(self, settings: Settings, repo: AbstractLayer3Repository, http: Optional[httpx.Client] = None):
        self.s = settings
        self.repo = repo
        self.redis = RedisCache(settings.redis_url, settings.redis_prefix, settings.redis_max_age_s)
        self.cache = TTLCache()
        self.http = http or httpx.Client(timeout=settings.live_http_timeout_s, headers={"User-Agent": "GroundZero-Layer3/3.0"})

    # ------------------------------------------------------------------ weather
    def weather(self, lat: float, lng: float) -> Dict[str, Any]:
        cached = self.redis.get_json("weather:current")
        if isinstance(cached, dict) and "weather_code" in cached:
            return {**cached, "source": cached.get("source", "redis")}
        key = ("weather", round(lat, 2), round(lng, 2))
        hit = self.cache.get(key)
        if hit:
            return hit
        params = {
            "latitude": round(lat, 4), "longitude": round(lng, 4),
            "current": "temperature_2m,precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m,is_day",
            "hourly": "weather_code,precipitation",
            "forecast_hours": max(2, self.s.thunder_lookahead_h + 1),
            "timezone": "UTC",
        }
        try:
            r = self.http.get(self.s.open_meteo_url, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise SourceUnavailable("weather", f"Open-Meteo request failed ({e.__class__.__name__})")
        cur = data.get("current") or {}
        if "weather_code" not in cur:
            raise SourceUnavailable("weather", "Open-Meteo returned no current conditions")
        snap = self._weather_snapshot(cur, data.get("hourly") or {})
        self.cache.set(key, snap, self.s.weather_cache_ttl_s)
        self.redis.set_json("weather:current", snap, self.s.weather_cache_ttl_s)
        return snap

    def _weather_snapshot(self, cur: Dict[str, Any], hourly: Dict[str, Any]) -> Dict[str, Any]:
        code = int(num(cur.get("weather_code"), 0))
        precip = num(cur.get("precipitation"), 0.0)
        gust = num(cur.get("wind_gusts_10m"), 0.0)
        wind = num(cur.get("wind_speed_10m"), 0.0)
        temp = num(cur.get("temperature_2m"), 28.0)
        severe_reason = None
        if code in SEVERE_WEATHER_CODES:
            severe_reason = "thunderstorm"
        elif precip >= self.s.severe_rain_mm_h:
            severe_reason = "heavy_rain"
        elif gust >= self.s.severe_gust_kmh:
            severe_reason = "high_wind"
        severe_soon = None
        codes = hourly.get("weather_code") or []
        hrs = hourly.get("time") or []
        now = utcnow()
        for t, c in zip(hrs, codes):
            dt = parse_dt(t)
            if dt and c in SEVERE_WEATHER_CODES and timedelta(0) <= (dt - now) <= timedelta(hours=self.s.thunder_lookahead_h):
                severe_soon = "thunderstorm"
                break
        is_rainy = code in RAIN_WEATHER_CODES or precip >= 0.1
        return {
            "temperature_c": temp, "precipitation_mm": precip, "weather_code": code,
            "wind_kmh": wind, "gust_kmh": gust, "is_day": bool(cur.get("is_day", 1)),
            "is_rainy": bool(is_rainy),
            "is_drizzle": bool(code in DRIZZLE_WEATHER_CODES or (0.1 <= precip < 0.5)),
            "is_severe": severe_reason is not None, "severe_reason": severe_reason, "severe_soon": severe_soon,
            "outdoor_suitable": not (severe_reason or precip >= 2.5),
            "fetched_at": iso(utcnow()), "source": "open-meteo",
        }

    # ------------------------------------------------------------------ Layer 0 file caches
    def _read_l0_json(self, filename: str) -> Any:
        p = Path(self.s.layer0_data_dir) / filename
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------ tide / sea state
    def tide(self, place: Dict[str, Any]) -> Dict[str, Any]:
        pid = place_id_of(place) or "?"
        cached = self.redis.get_json(f"tide:{pid}")
        if isinstance(cached, dict) and cached:
            return {**cached, "source": cached.get("source", "redis")}
        raw = self._read_l0_json(self.s.live_tide_cache_file)
        if raw:
            snap = self._parse_tide(raw, pid)
            if snap:
                return snap
        ll = place_latlng(place)
        if not ll:
            raise SourceUnavailable("tide", "place has no coordinates")
        key = ("tide", round(ll[0], 2), round(ll[1], 2))
        hit = self.cache.get(key)
        if hit:
            return hit
        try:
            r = self.http.get(self.s.open_meteo_marine_url, params={
                "latitude": round(ll[0], 4), "longitude": round(ll[1], 4),
                "current": "wave_height,wave_period,sea_level_height_msl"})
            r.raise_for_status()
            cur = (r.json() or {}).get("current") or {}
        except Exception as e:
            raise SourceUnavailable("tide", f"Open-Meteo Marine failed ({e.__class__.__name__})")
        if cur.get("wave_height") is None:
            raise SourceUnavailable("tide", "no marine data for this coordinate")
        wave = num(cur.get("wave_height"))
        snap = {"wave_height_m": wave, "tide_state": None, "sea_level_m": cur.get("sea_level_height_msl"),
                "safe_for_swimming": wave < 1.5, "fetched_at": iso(utcnow()), "source": "open-meteo-marine"}
        self.cache.set(key, snap, self.s.tide_cache_ttl_s)
        return snap

    @staticmethod
    def _parse_tide(raw: Any, place_id: str) -> Optional[Dict[str, Any]]:
        scope = raw
        if isinstance(raw, dict):
            for holder in ("places", "by_place", "spots", "locations"):
                if isinstance(raw.get(holder), dict) and place_id in raw[holder]:
                    scope = raw[holder][place_id]
                    break
            else:
                if place_id in raw and isinstance(raw[place_id], dict):
                    scope = raw[place_id]
        wave = find_first(scope, ("wave_height_m", "wave_height", "swell_height_m", "wave_height_max", "swell_height"))
        state = find_first(scope, ("tide_state", "state", "sea_state", "tide", "tide_phase"))
        safe = find_first(scope, ("safe_for_swimming", "swim_safe", "is_safe", "safe"))
        if wave is None and state is None and safe is None:
            return None
        snap: Dict[str, Any] = {"wave_height_m": None if wave is None else num(wave), "tide_state": None if state is None else str(state),
                                "safe_for_swimming": safe if isinstance(safe, bool) else None,
                                "fetched_at": find_first(scope, ("fetched_at", "generated_at", "updated_at", "timestamp")),
                                "source": "layer0-live_tide_cache"}
        return snap

    # ------------------------------------------------------------------ events
    def _all_events(self) -> List[Dict[str, Any]]:
        cached = self.redis.get_json("events:current")
        if isinstance(cached, dict) and isinstance(cached.get("events"), list):
            return [e for e in cached["events"] if isinstance(e, dict)]
        if isinstance(cached, list):
            return [e for e in cached if isinstance(e, dict)]
        raw = self._read_l0_json(self.s.live_events_cache_file)
        if raw is None:
            raise SourceUnavailable("events", f"{self.s.live_events_cache_file} not found and Redis has no events")
        if isinstance(raw, dict):
            for k in ("events", "items", "data"):
                if isinstance(raw.get(k), list):
                    raw = raw[k]
                    break
        if not isinstance(raw, list):
            raise SourceUnavailable("events", "unrecognised events cache format")
        return [e for e in raw if isinstance(e, dict)]

    def events_near(self, place: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
        events = self._all_events()
        ll = place_latlng(place)
        name = place_name_of(place).lower()
        local = to_local(now, self.s.timezone)
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        out = []
        for e in events:
            title = str(pget(e, "title", "name", "summary", default=""))
            text = " ".join(str(pget(e, k, default="")) for k in ("title", "name", "summary", "description", "location", "place", "venue")).lower()
            start = parse_dt(pget(e, "start", "start_date", "date", "event_date", "starts_at"))
            end = parse_dt(pget(e, "end", "end_date", "ends_at")) or start
            if start:
                s_l, e_l = to_local(start, self.s.timezone), to_local(end, self.s.timezone)
                if e_l.date() == s_l.date() and e_l.hour == 0 and e_l.minute == 0:
                    e_l = e_l + timedelta(days=1)  # date-only end => whole day
                if not (s_l < day_end and e_l >= day_start):
                    continue
            else:
                pub = parse_dt(pget(e, "published", "fetched_at", "pub_date"))
                if not pub or (now - pub) > timedelta(hours=24):
                    continue
            near = False
            elat, elng = pget(e, "lat", "latitude"), pget(e, "lng", "lon", "longitude")
            if ll and elat is not None and elng is not None:
                near = haversine_m(ll[0], ll[1], float(elat), float(elng)) <= self.s.event_radius_m
            if not near and len(name) >= 4 and name in text:
                near = True
            if not near and pget(e, "place_id") is not None and str(e["place_id"]) == place_id_of(place):
                near = True
            if near:
                big = any(k in text for k in BIG_EVENT_KEYWORDS)
                out.append({"title": title, "big": big, "start": iso(start)})
        return out

    # ------------------------------------------------------------------ crowd
    def crowd(self, place: Dict[str, Any], now: datetime, weather: Optional[Dict[str, Any]], events: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        pid = place_id_of(place) or "?"
        cached = self.redis.get_json(f"crowd:{pid}")
        if isinstance(cached, dict) and normalize_crowd_level(cached.get("level")):
            return {"level": normalize_crowd_level(cached["level"]), "basis": "redis", "estimated": False}
        lvl = normalize_crowd_level(place.get("crowd_level"))
        if lvl:
            return {"level": lvl, "basis": "place_record", "estimated": False}
        return self.estimate_crowd(place, now, weather, events)

    def estimate_crowd(self, place: Dict[str, Any], now: datetime, weather: Optional[Dict[str, Any]], events: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Five combined signals — same idea as Layer 0's crowd_engine: time-of-day baseline,
        weekday/weekend, weather, season, live events."""
        local = to_local(now, self.s.timezone)
        h = hour_float(local)
        cat = place_category(place)
        if cat == "SPIRITUAL":
            base = 0.6 if 6 <= h < 9 or 17 <= h < 20 else (0.35 if 9 <= h < 17 else 0.15)
        elif cat == "FOOD":
            base = 0.75 if 12 <= h < 14.5 or 19 <= h < 21.5 else (0.4 if 8 <= h < 10 or 16 <= h < 18 else 0.2)
        elif cat == "NATURE":
            base = 0.8 if 16 <= h < 19 else (0.4 if 7 <= h < 10 else (0.3 if 10 <= h < 16 else 0.1))
        elif cat == "SHOPPING":
            base = 0.75 if 11 <= h < 14 or 17 <= h < 20 else (0.4 if 9 <= h < 11 else 0.15)
        else:
            base = 0.6 if 10 <= h < 17 else (0.35 if 8 <= h < 10 or 17 <= h < 19 else 0.1)
        idx = base
        signals = {"time_baseline": round(base, 2)}
        if is_weekend(local) or (local.month, local.day) in FIXED_HOLIDAYS:
            idx += 0.15
            signals["weekend_or_holiday"] = 0.15
        if weather and weather.get("is_rainy") and cat in ("NATURE", "EXPLORE"):
            idx -= 0.2
            signals["rain"] = -0.2
        if season_of(local) in ("post_monsoon", "winter"):
            idx += 0.05
            signals["peak_season"] = 0.05
        if events:
            bump = 0.25 if any(e.get("big") for e in events) else 0.12
            idx += bump
            signals["nearby_events"] = bump
        idx = clamp(idx)
        level = "low" if idx < 0.35 else ("medium" if idx < 0.65 else "high")
        return {"level": level, "index": round(idx, 2), "basis": "estimated", "estimated": True, "signals": signals}

    # ------------------------------------------------------------------ advisories (safety source #2)
    def advisories(self) -> List[Dict[str, Any]]:
        """Government / local-authority travel advisories.

        (a) advisories entered in Layer 3's own table by an admin (mirror of an authority notice), and
        (b) the configured public RSS / Atom / CAP feed (LAYER3_ADVISORY_FEED_URL), filtered to the region.
        Raises SourceUnavailable only when NOTHING could be checked (no feed configured AND no DB rows read).
        """
        items: List[Dict[str, Any]] = [
            {"title": a["title"], "severity": a.get("severity"), "source": f"admin:{a.get('source')}", "id": a["id"]}
            for a in self.repo.active_advisories()
        ]
        if self.s.advisory_feed_url:
            items.extend(self._feed_items())
        return items

    def advisory_feed_configured(self) -> bool:
        return bool(self.s.advisory_feed_url)

    def _feed_items(self) -> List[Dict[str, Any]]:
        key = ("advisory_feed", self.s.advisory_feed_url)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        try:
            r = self.http.get(self.s.advisory_feed_url)  # type: ignore[arg-type]
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            raise SourceUnavailable("advisory_feed", f"feed fetch/parse failed ({e.__class__.__name__})")
        out: List[Dict[str, Any]] = []
        cutoff = utcnow() - timedelta(hours=self.s.advisory_max_age_h)
        for el in root.iter():
            tag = el.tag.split("}")[-1].lower()
            if tag not in ("item", "entry", "alert", "info"):
                continue
            def txt(*names: str) -> str:
                for child in el.iter():
                    if child.tag.split("}")[-1].lower() in names and (child.text or "").strip():
                        return child.text.strip()
                return ""
            title = txt("title", "headline", "event")
            desc = txt("description", "summary", "content", "instruction")
            when = parse_dt(txt("pubdate", "published", "updated", "sent", "effective"))
            if when and when < cutoff:
                continue
            blob = f"{title} {desc} {txt('areadesc')}".lower()
            if not any(k in blob for k in self.s.advisory_region_keywords):
                continue
            if not any(k in blob for k in ADVISORY_SEVERITY_KEYWORDS):
                continue
            out.append({"title": title or desc[:120], "severity": txt("severity") or "warning", "source": "feed", "id": None})
        self.cache.set(key, out, self.s.advisory_cache_ttl_s)
        return out

    # ------------------------------------------------------------------ combined snapshot
    def snapshot(self, lat: float, lng: float, place: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Best-effort snapshot for /conditions and the Ask Engine. Each source reports its own status."""
        now = now or utcnow()
        out: Dict[str, Any] = {"generated_at": iso(now)}
        try:
            out["weather"] = {"status": "ok", "data": self.weather(lat, lng)}
        except SourceUnavailable as e:
            out["weather"] = {"status": "unavailable", "reason": e.reason}
        if place is not None and is_coastal(place):
            try:
                out["tide"] = {"status": "ok", "data": self.tide(place)}
            except SourceUnavailable as e:
                out["tide"] = {"status": "unavailable", "reason": e.reason}
        if place is not None:
            try:
                out["events"] = {"status": "ok", "data": self.events_near(place, now)}
            except SourceUnavailable as e:
                out["events"] = {"status": "unavailable", "reason": e.reason}
        try:
            out["advisories"] = {"status": "ok", "data": self.advisories()}
        except SourceUnavailable as e:
            out["advisories"] = {"status": "unavailable", "reason": e.reason}
        return out
