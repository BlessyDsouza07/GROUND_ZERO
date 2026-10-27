"""
Layer 3 utilities — geo maths, time helpers, tolerant parsers for the Layer 0/1/2
data shapes, an opening-hours parser and a tiny TTL cache.

Everything here is pure (no I/O) so it is trivially unit-testable.
"""
from __future__ import annotations

import json
import logging
import math
import re
import sys
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from layer3_config import SEASON_BY_MONTH

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
_LOGGERS: Dict[str, logging.Logger] = {}


def get_logger(name: str = "layer3", level: str = "INFO") -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
        log.addHandler(h)
        log.propagate = False
    log.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    _LOGGERS[name] = log
    return log


# ---------------------------------------------------------------------------
# geo
# ---------------------------------------------------------------------------
EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def valid_latlng(lat: Any, lng: Any) -> bool:
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0)


# ---------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO strings / epoch numbers / datetimes into aware UTC datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_aware(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return ensure_aware(datetime.fromisoformat(s))
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                return ensure_aware(datetime.strptime(s, fmt))
            except ValueError:
                continue
    return None


def iso(dt: Optional[datetime]) -> Optional[str]:
    return ensure_aware(dt).isoformat() if dt else None


def to_local(dt: datetime, tzname: str) -> datetime:
    dt = ensure_aware(dt)
    if ZoneInfo is None:
        return dt + timedelta(hours=5, minutes=30)
    try:
        return dt.astimezone(ZoneInfo(tzname))
    except Exception:  # tzdata missing (Windows) — fall back to a fixed IST offset
        return dt.astimezone(timezone(timedelta(hours=5, minutes=30)))


def hour_float(local_dt: datetime) -> float:
    return local_dt.hour + local_dt.minute / 60.0


def season_of(local_dt: datetime) -> str:
    return SEASON_BY_MONTH[local_dt.month]


def is_weekend(local_dt: datetime) -> bool:
    return local_dt.weekday() >= 5


def band_score(hour: float, bands: Sequence[Tuple[float, float, float]], default: float = 0.5) -> float:
    for start, end, score in bands:
        if start <= hour < end:
            return score
    return default


# ---------------------------------------------------------------------------
# tolerant accessors for Layer 0 / 1 / 2 dicts
# ---------------------------------------------------------------------------
def pget(d: Any, *keys: str, default: Any = None) -> Any:
    """First key that exists with a non-None, non-empty-string value."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return default


def as_list(v: Any) -> List[str]:
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except ValueError:
                pass
        return [p.strip() for p in re.split(r"[,;|]", s) if p.strip()]
    return [str(v)]


def as_dict(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip().startswith("{"):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def place_id_of(p: Dict[str, Any]) -> Optional[str]:
    v = pget(p, "place_id", "id")
    return str(v) if v is not None else None


def place_name_of(p: Dict[str, Any]) -> str:
    return str(pget(p, "name", "place_name", default="this place"))


def place_latlng(p: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat = pget(p, "lat", "latitude")
    lng = pget(p, "lng", "lon", "longitude")
    if valid_latlng(lat, lng):
        return float(lat), float(lng)
    return None


def place_category(p: Dict[str, Any]) -> str:
    return str(pget(p, "category", default="UNKNOWN")).upper()


def place_tags(p: Dict[str, Any]) -> List[str]:
    tags = as_list(p.get("tags")) + as_list(p.get("trip_relevance_tags"))
    seen, out = set(), []
    for t in tags:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(tl)
    return out


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def find_first(obj: Any, keys: Iterable[str], _depth: int = 0) -> Any:
    """Depth-limited recursive search for the first non-null value under any of `keys`."""
    keys = tuple(keys)
    if _depth > 4:
        return None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] not in (None, ""):
                return obj[k]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                r = find_first(v, keys, _depth + 1)
                if r is not None:
                    return r
    elif isinstance(obj, list):
        for v in obj[:50]:
            r = find_first(v, keys, _depth + 1)
            if r is not None:
                return r
    return None


def normalize_language(v: Any, default: str = "en") -> str:
    if not v:
        return default
    s = str(v).strip().lower()
    table = {
        "en": "en", "eng": "en", "english": "en",
        "kn": "kn", "kan": "kn", "kannada": "kn",
        "kok": "kok", "konkani": "kok", "gom": "kok",
        "hi": "hi", "hin": "hi", "hindi": "hi",
    }
    return table.get(s, default)


def normalize_voice(v: Any, default: str = "warm") -> str:
    if not v:
        return default
    s = str(v).strip().lower()
    if "histor" in s or "calm" in s:
        return "historian"
    if "witty" in s:
        return "witty"
    if "warm" in s or "friend" in s:
        return "warm"
    return default


def normalize_energy(v: Any) -> Optional[str]:
    """Accepts 'low'/'medium'/'high', 'tired'/'energetic', or a numeric slider (0-1 or 1-10 or 0-100)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        x = float(v)
        if x > 10:
            x /= 100.0
        elif x > 1:
            x /= 10.0
        return "low" if x < 0.34 else ("medium" if x < 0.67 else "high")
    s = str(v).strip().lower()
    if s in ("low", "tired", "relaxed", "calm") or "tired" in s:
        return "low"
    if s in ("high", "energetic", "active") or "energ" in s:
        return "high"
    if s in ("medium", "med", "okay", "ok", "moderate", "balanced"):
        return "medium"
    try:
        return normalize_energy(float(s))
    except ValueError:
        return None


def normalize_crowd_tolerance(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    s = str(v).strip().lower().replace("-", " ").replace("_", " ")
    if "love" in s:
        return "love"
    if "avoid" in s:
        return "avoid"
    if "quiet" in s:
        return "prefer_quiet"
    if "fine" in s or "balanced" in s or "ok" in s:
        return "fine"
    return None


def normalize_crowd_level(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        x = float(v)
        if x > 1:
            x = x / 10.0 if x <= 10 else x / 100.0
        return "low" if x < 0.35 else ("medium" if x < 0.65 else "high")
    s = str(v).strip().lower()
    if s in ("low", "quiet", "empty", "light"):
        return "low"
    if s in ("medium", "moderate", "med", "normal"):
        return "medium"
    if s in ("high", "busy", "crowded", "packed", "very high"):
        return "high"
    return None


def first_sentences(text: str, n: int, skip: int = 0) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", re.sub(r"\s+", " ", str(text)).strip())
    parts = [p.strip() for p in parts if len(p.strip()) > 3]
    return parts[skip: skip + n]


# ---------------------------------------------------------------------------
# opening hours (OSM string or JSON) — best effort, returns None when unsure
# ---------------------------------------------------------------------------
_DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")


def _day_set(spec: str) -> Optional[set]:
    spec = spec.strip().lower()
    if not spec:
        return set(range(7))
    days: set = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = [x.strip()[:2] for x in part.split("-", 1)]
            if a in _DAYS and b in _DAYS:
                i, j = _DAYS.index(a), _DAYS.index(b)
                days |= set(range(i, j + 1)) if i <= j else set(list(range(i, 7)) + list(range(0, j + 1)))
            else:
                return None
        else:
            d = part[:2]
            if d in _DAYS:
                days.add(_DAYS.index(d))
            elif part in ("ph", "sh"):
                continue
            else:
                return None
    return days


class OpeningHours:
    """Parsed opening hours. `is_open(local_dt)` -> True / False / None (unknown).

    Rule precedence follows OSM: for a given weekday the *last* matching rule wins
    (so "Mo-Su 09:00-18:00; Su off" correctly closes Sunday).
    """

    def __init__(self, rules: Optional[List[Tuple[set, List[Tuple[int, int]]]]], always: bool = False):
        self.rules = rules
        self.always = always

    @property
    def known(self) -> bool:
        return self.always or bool(self.rules)

    def _effective(self, weekday: int) -> Optional[List[Tuple[int, int]]]:
        eff = None
        for days, intervals in (self.rules or []):
            if weekday in days:
                eff = intervals
        return eff

    def is_open(self, local_dt: datetime) -> Optional[bool]:
        if self.always:
            return True
        if not self.rules:
            return None
        minutes = local_dt.hour * 60 + local_dt.minute
        wd = local_dt.weekday()
        for (s, e) in (self._effective(wd) or []):
            if s < e and s <= minutes < e:
                return True
            if s > e and minutes >= s:          # overnight, evening part
                return True
            if s == e:                          # 24h
                return True
        for (s, e) in (self._effective((wd - 1) % 7) or []):
            if s > e and minutes < e:           # overnight, after-midnight part
                return True
        return False

    def closing_time_today(self, local_dt: datetime) -> Optional[str]:
        eff = self._effective(local_dt.weekday()) if self.rules else None
        if not eff:
            return None
        end = max(e for _, e in eff)
        return f"{(end // 60) % 24:02d}:{end % 60:02d}"


def parse_opening_hours(raw: Any) -> OpeningHours:
    if raw is None or raw == "":
        return OpeningHours(None)
    if isinstance(raw, str) and raw.strip().startswith(("{", "[")):
        try:
            raw = json.loads(raw)
        except ValueError:
            return OpeningHours(None)
    if isinstance(raw, dict):
        return _parse_json_hours(raw)
    if isinstance(raw, list):
        rules = []
        for item in raw:
            oh = _parse_json_hours(item) if isinstance(item, dict) else OpeningHours(None)
            if oh.always:
                return oh
            if oh.rules:
                rules.extend(oh.rules)
        return OpeningHours(rules or None)
    if isinstance(raw, str):
        return _parse_osm_hours(raw)
    return OpeningHours(None)


def _hm(v: Any) -> Optional[int]:
    if v is None:
        return None
    m = re.match(r"^\s*(\d{1,2}):?(\d{2})?\s*(am|pm)?\s*$", str(v).lower())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 24 or mi > 59:
        return None
    return h * 60 + mi


def _parse_json_hours(d: Dict[str, Any]) -> OpeningHours:
    if d.get("always") or d.get("is_24_7") or str(d.get("open", "")).lower() in ("24/7", "24h"):
        return OpeningHours(None, always=True)
    o, c = _hm(d.get("open")), _hm(d.get("close"))
    if o is None or c is None:
        return OpeningHours(None)
    days_raw = d.get("days")
    days: set = set(range(7))
    if isinstance(days_raw, list) and days_raw:
        days = set()
        for x in days_raw:
            if isinstance(x, int) and 0 <= x <= 6:
                days.add(x)
            elif isinstance(x, str) and x.strip()[:2].lower() in _DAYS:
                days.add(_DAYS.index(x.strip()[:2].lower()))
        if not days:
            days = set(range(7))
    return OpeningHours([(days, [(o, 24 * 60 if c == 0 else c)])])


def _parse_osm_hours(s: str) -> OpeningHours:
    s = s.strip()
    if not s:
        return OpeningHours(None)
    if s.lower() in ("24/7", "24 / 7"):
        return OpeningHours(None, always=True)
    rules: List[Tuple[set, List[Tuple[int, int]]]] = []
    for rule in s.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        low = rule.lower()
        if "sunrise" in low or "sunset" in low or "dusk" in low or "dawn" in low:
            return OpeningHours(None)  # cannot evaluate reliably
        times = _TIME_RE.findall(rule)
        day_part = _TIME_RE.split(rule)[0] if times else re.sub(r"\boff\b|\bclosed\b", "", low)
        days = _day_set(day_part.strip().rstrip(" ,"))
        if days is None:
            return OpeningHours(None)
        if not times:
            if "off" in low or "closed" in low:
                rules.append((days, []))
                continue
            return OpeningHours(None)
        intervals = [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in times]
        rules.append((days, intervals))
    return OpeningHours(rules or None)


# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------
class TTLCache:
    def __init__(self, maxsize: int = 512):
        self._d: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.maxsize = maxsize

    def get(self, key: Any) -> Any:
        with self._lock:
            item = self._d.get(key)
            if not item:
                return None
            exp, val = item
            if exp < _time.monotonic():
                self._d.pop(key, None)
                return None
            return val

    def set(self, key: Any, value: Any, ttl_s: float) -> None:
        with self._lock:
            if len(self._d) >= self.maxsize:
                now = _time.monotonic()
                for k in [k for k, (e, _) in self._d.items() if e < now][: self.maxsize // 4 or 1]:
                    self._d.pop(k, None)
                if len(self._d) >= self.maxsize:
                    self._d.pop(next(iter(self._d)))
            self._d[key] = (_time.monotonic() + ttl_s, value)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def safe_json_loads(s: Any, default: Any = None) -> Any:
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default
