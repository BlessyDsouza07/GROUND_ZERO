"""
Layer 3 <-> Layers 0 / 1 / 2 bridge.  READ-ONLY.

Layer 3 never writes into another layer's files or tables. It reads:

  Layer 0  data_output/master_data_core.json          (place records — single source of truth)
           data_output/ground_zero.db  (places table)  (optional: live `temporarily_unavailable` overlay)
           data_output/live_tide_cache.json            (see layer3_sources)
           data_output/live_events_cache.json          (see layer3_sources)
  Layer 1  layer1/data_output/profiles/<id>.json       (or GET {layer1}/profile/<id>)
  Layer 2  POST {layer2}/hive/generate                 (only when a session is started from a profile_id)

All parsers are deliberately tolerant of shape differences (list vs {"places": [...]},
`place_id` vs `id`, slots nested under `recommendation`, ...) because Layers 0-2 are owned
by other people and evolve independently.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from layer3_config import Settings
from layer3_models import LayerError, NotFound
from layer3_utils import as_list, get_logger, pget, place_id_of, place_latlng, haversine_m, place_category

log = get_logger("layer3.bridge")

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,96}$")


def safe_id(value: str) -> str:
    """Reject anything that could escape a directory when used as a file name."""
    if not isinstance(value, str) or not _SAFE_ID.match(value) or ".." in value:
        raise LayerError(f"Invalid identifier: {value!r}", 400, "invalid_id")
    return value


# ---------------------------------------------------------------------------
# Layer 0 — master data core
# ---------------------------------------------------------------------------
class MasterCoreStore:
    """Loads master_data_core.json, reloads automatically when the file changes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._mtime: Optional[float] = None
        self._places: List[Dict[str, Any]] = []
        self._index: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, Any] = {}

    @staticmethod
    def _extract_places(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)], {}
        if isinstance(payload, dict):
            for key in ("places", "data", "items", "records", "master_data_core"):
                v = payload.get(key)
                if isinstance(v, list):
                    return [p for p in v if isinstance(p, dict)], {k: payload[k] for k in payload if k != key}
                if isinstance(v, dict):
                    inner, meta = MasterCoreStore._extract_places(v)
                    if inner:
                        return inner, meta
        return [], {}

    def _reload_if_needed(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            with self._lock:
                self._places, self._index, self._mtime = [], {}, None
            return
        with self._lock:
            if self._mtime == mtime:
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                log.error("Could not read %s: %s", self.path, e)
                return
            places, meta = self._extract_places(payload)
            index: Dict[str, Dict[str, Any]] = {}
            for p in places:
                for k in ("place_id", "id"):
                    if p.get(k) is not None:
                        index.setdefault(str(p[k]), p)
            self._places, self._index, self._meta, self._mtime = places, index, meta, mtime
            log.info("Loaded %d places from %s", len(places), self.path)

    def all(self) -> List[Dict[str, Any]]:
        self._reload_if_needed()
        return self._places

    def get(self, place_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if place_id is None:
            return None
        self._reload_if_needed()
        return self._index.get(str(place_id))

    def require(self, place_id: str) -> Dict[str, Any]:
        p = self.get(place_id)
        if p is None:
            raise NotFound(f"Place '{place_id}' not found in master_data_core.json", "place_not_found")
        return p

    def nearby(self, lat: float, lng: float, radius_m: float, categories: Optional[set] = None, limit: int = 5) -> List[Tuple[float, Dict[str, Any]]]:
        out = []
        for p in self.all():
            ll = place_latlng(p)
            if not ll:
                continue
            if categories and place_category(p) not in categories:
                continue
            d = haversine_m(lat, lng, ll[0], ll[1])
            if d <= radius_m:
                out.append((d, p))
        out.sort(key=lambda x: x[0])
        return out[:limit]

    def status(self) -> Dict[str, Any]:
        self._reload_if_needed()
        return {"path": str(self.path), "exists": self.path.exists(), "place_count": len(self._places),
                "loaded": self._mtime is not None}


class LiveFlagOverlay:
    """Read-only look at Layer 0's SQLite `places.temporarily_unavailable` column.

    master_data_core.json is only refreshed when Layer 0's export stage runs; the DB is
    updated immediately when a PlaceProblemReport auto-flags a place. Reading the DB
    (never writing) makes the Replan Trigger react in real time. If the DB / table /
    column isn't there the overlay silently contributes nothing.
    """

    def __init__(self, db_path: Path, enabled: bool = True, ttl_s: float = 60.0):
        self.db_path = Path(db_path)
        self.enabled = enabled
        self.ttl_s = ttl_s
        self._cache: Tuple[float, set] = (float("-inf"), set())   # -inf guarantees the FIRST read is never mistaken for a fresh cache hit
        self.available: Optional[bool] = None

    def unavailable_ids(self) -> set:
        import time
        if not self.enabled or not self.db_path.exists():
            self.available = False
            return set()
        now = time.monotonic()
        if now - self._cache[0] < self.ttl_s:
            return self._cache[1]
        ids: set = set()
        try:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=2)
            try:
                rows = con.execute("SELECT place_id, id FROM places WHERE temporarily_unavailable = 1").fetchall()
                for pid, rid in rows:
                    if pid is not None:
                        ids.add(str(pid))
                    if rid is not None:
                        ids.add(str(rid))
                self.available = True
            finally:
                con.close()
        except Exception as e:
            self.available = False
            log.debug("Layer 0 DB flag overlay unavailable: %s", e)
        self._cache = (now, ids)
        return ids


# ---------------------------------------------------------------------------
# Layer 1 — profiles
# ---------------------------------------------------------------------------
class ProfileStore:
    def __init__(self, settings: Settings):
        self.s = settings

    def get(self, profile_id: str) -> Dict[str, Any]:
        pid = safe_id(profile_id)
        path = self.s.layer1_profiles_dir / f"{pid}.json"
        if path.exists():
            try:
                return self._unwrap(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                raise LayerError(f"Profile file unreadable: {e}", 502, "profile_unreadable")

        # In the current monolith, Layer 1 persists TouristProfile rows in
        # Postgres and never wrote the JSON-file export this class was
        # originally built against; its /survey-prefixed router also has no
        # plain GET /profile/{id} route, so the HTTP fallback below 404s
        # unconditionally there — not because a given profile is missing.
        # Read the same shared table directly, read-only, first (identical
        # pattern to LiveFlagOverlay's direct read of Layer 0's DB above).
        row = self._from_postgres(pid)
        if row is not None:
            return row

        # fall back to the Layer 1 API (correct when Layer 1 runs standalone
        # and really does expose GET /profile/{id} at its root)
        try:
            r = httpx.get(f"{self.s.layer1_base_url.rstrip('/')}/profile/{pid}", timeout=self.s.upstream_timeout_s)
        except httpx.HTTPError as e:
            raise NotFound(f"Profile '{pid}' not found in {self.s.layer1_profiles_dir}, not in the shared "
                            f"database, and Layer 1 API unreachable ({e.__class__.__name__})", "profile_not_found")
        if r.status_code == 404:
            raise NotFound(f"Profile '{pid}' not found", "profile_not_found")
        if r.status_code >= 400:
            raise LayerError(f"Layer 1 returned HTTP {r.status_code}", 502, "layer1_error")
        return self._unwrap(r.json())

    def _from_postgres(self, pid: str) -> Optional[Dict[str, Any]]:
        """Read-only lookup straight from Layer 1's `tourist_profiles` table.
        Never raises — a missing driver, unreachable DB, or bad id just means
        'try the next source', same as every other optional signal in Layer 3.
        """
        try:
            import psycopg  # lazy: keeps psycopg optional, never blocks Layer 3's own import
        except ImportError:
            return None
        if not self.s.postgres_dsn:
            return None
        try:
            with psycopg.connect(self.s.postgres_dsn, connect_timeout=3) as con:
                with con.cursor() as cur:
                    cur.execute(
                        """SELECT id, purpose, energy_band, crowd_tolerance, budget, dietary_flags,
                                  group_config, group_session_id, curiosity_text, curiosity_vector,
                                  trip_duration_hours, multi_day_count, start_time_preference,
                                  accessibility_flags, companion_language, voice_personality,
                                  return_visitor_exclusions, device_id
                           FROM tourist_profiles WHERE id = %s::uuid""",
                        (pid,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        return None
                    data = dict(zip([d.name for d in cur.description], row))
        except Exception as e:
            log.debug("Postgres profile lookup unavailable for %s: %s", pid, e)
            return None
        cv = data.get("curiosity_vector")
        if isinstance(cv, str):
            try:
                data["curiosity_vector"] = json.loads(cv)
            except ValueError:
                pass
        data["id"] = str(data["id"])
        return data

    @staticmethod
    def _unwrap(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict) and isinstance(payload.get("profile"), dict):
            return payload["profile"]
        return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# Layer 2 — itinerary
# ---------------------------------------------------------------------------
_ROLE_KEYS = ("slot_role", "role")
_PLACE_HOLDERS = ("recommendation", "place", "rec", "candidate")
_SKIP_KEYS = {"alternatives", "rejected", "considered", "candidates", "alternates", "explanations", "route", "routes", "legs"}


class Layer2Client:
    def __init__(self, settings: Settings):
        self.s = settings

    def generate(self, profile_id: str) -> Dict[str, Any]:
        # SECURITY FIX (4th audit response, Oct 2026): /hive/generate is
        # now gated by the same shared-secret admin key /admin/* uses
        # (see integration/layer2_layer3_bridge.py) -- this server-to-
        # server call has no end-user token to forward, so it sends that
        # internal key instead of being reachable anonymously.
        import os
        headers = {}
        admin_key = os.environ.get("ADMIN_API_KEY", "")
        if admin_key:
            headers["X-Admin-Api-Key"] = admin_key
        try:
            r = httpx.post(f"{self.s.layer2_base_url.rstrip('/')}/hive/generate",
                           json={"profile_id": profile_id}, headers=headers,
                           timeout=max(self.s.upstream_timeout_s, 60.0))
        except httpx.HTTPError as e:
            raise LayerError(f"Layer 2 (HIVE) unreachable at {self.s.layer2_base_url}: {e.__class__.__name__}", 502, "layer2_unreachable")
        if r.status_code >= 400:
            raise LayerError(f"Layer 2 returned HTTP {r.status_code}: {r.text[:200]}", 502, "layer2_error")
        return r.json()


def normalize_itinerary(payload: Any) -> List[Dict[str, Any]]:
    """Flatten *any* HIVE-style itinerary into Layer 3's canonical slot list.

    Canonical slot:
      {slot_id, order, day, role, place_id|None, place_name, status, time_window, transport_tag, distance_to_next_km}
    A slot with place_id None is a synthetic break (e.g. Layer 2's lunch ANCHOR) — Layer 3 keeps it for
    ordering but never geofences it.
    """
    slots: List[Dict[str, Any]] = []

    def visit(node: Any, day: Optional[int]) -> None:
        if isinstance(node, list):
            for x in node:
                visit(x, day)
            return
        if not isinstance(node, dict):
            return
        d = day
        for dk in ("day_number", "day_index", "day"):
            if isinstance(node.get(dk), int):
                d = node[dk]
                break
        slot = _extract_slot(node, d)
        if slot:
            slot["order"] = len(slots)
            slot["slot_id"] = slot.get("slot_id") or f"s{len(slots)}"
            slots.append(slot)
            return
        for k, v in node.items():
            if k in _SKIP_KEYS:
                continue
            if isinstance(v, (dict, list)):
                visit(v, d)

    if isinstance(payload, dict) and isinstance(payload.get("queue"), list) and payload["queue"] and \
            all(isinstance(x, dict) for x in payload["queue"]) and any("place_id" in x for x in payload["queue"]):
        visit(payload["queue"], None)
    else:
        visit(payload, None)
    return slots


def _extract_slot(node: Dict[str, Any], day: Optional[int]) -> Optional[Dict[str, Any]]:
    role = pget(node, *_ROLE_KEYS)
    if role is None or isinstance(role, (dict, list)):
        return None
    role = str(role).upper()
    pid = node.get("place_id")
    holder = node
    if pid is None:
        for key in _PLACE_HOLDERS:
            child = node.get(key)
            if isinstance(child, dict):
                cpid = child.get("place_id", child.get("id"))
                if cpid is not None:
                    pid, holder = cpid, child
                    break
    if pid is None:
        # a place-less slot is only meaningful for the synthetic meal-break ANCHOR
        if role != "ANCHOR":
            return None
    name = pget(holder, "place_name", "name") or pget(node, "place_name", "name")
    tw = pget(node, "time_window", "window", "scheduled_time")
    if tw is None and (node.get("start_time") or node.get("end_time")):
        tw = {"start": node.get("start_time"), "end": node.get("end_time")}
    return {
        "slot_id": node.get("slot_id") or node.get("id"),
        "day": day if day is not None else 1,
        "role": role,
        "place_id": str(pid) if pid is not None else None,
        "place_name": name,
        "status": "pending",
        "time_window": tw,
        "transport_tag": pget(node, "transport_tag", "transport_mode", "transport"),
        "distance_to_next_km": pget(node, "distance_to_next_km", "distance_km"),
    }
