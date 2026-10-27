"""
Layer 3 persistence.

* `AbstractLayer3Repository` — the contract (Repository Pattern).
* `SqlLayer3Repository` — SQLAlchemy 2.0 Core implementation.
  - SQLite by default (own file `data_output/layer3.db`, WAL mode)
  - works unchanged on PostgreSQL (`LAYER3_DATABASE_URL=postgresql+psycopg2://...`)
  - every table is prefixed `l3_` so it can safely live inside the shared
    `ground_zero.db` (`LAYER3_SHARE_GROUND_ZERO_DB=true`) without touching any
    Layer 0 / 1 / 2 table.

Layer 3 NEVER writes to Layer 0's `places` table or any other layer's table.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, Index, Integer, MetaData, String, Table, Text,
    and_, create_engine, delete, event, insert, select, text, update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from layer3_utils import ensure_aware, get_logger, utcnow

log = get_logger("layer3.repo")


class UTCDateTime(TypeDecorator):
    """Stores naive UTC, returns timezone-aware UTC (consistent on SQLite and PostgreSQL)."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return ensure_aware(value).astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


metadata = MetaData()

sessions = Table(
    "l3_sessions", metadata,
    Column("session_id", String(64), primary_key=True),
    Column("profile_id", String(64), index=True),
    Column("device_id", String(128), index=True),
    Column("group_session_id", String(64), index=True),
    Column("status", String(16), nullable=False, default="active"),
    Column("language", String(8), nullable=False, default="en"),
    Column("voice", String(16), nullable=False, default="warm"),
    Column("profile", JSON),
    Column("queue", JSON),
    Column("current_slot_index", Integer, default=0),
    Column("energy_band", String(8)),
    Column("energy_updated_at", UTCDateTime),
    Column("quiet_until", UTCDateTime),
    Column("last_notification_at", UTCDateTime),
    Column("consecutive_dismissals", Integer, default=0),
    Column("dismissed_count", Integer, default=0),
    Column("geofence_lock_place_id", String(64)),
    Column("geofence_lock_since", UTCDateTime),
    Column("visited_place_ids", JSON),
    Column("wallet_remaining", Integer),
    Column("sos_active", Boolean, default=False),
    Column("sos_since", UTCDateTime),
    Column("created_at", UTCDateTime, nullable=False),
    Column("updated_at", UTCDateTime, nullable=False),
)

pings = Table(
    "l3_pings", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), nullable=False),
    Column("lat", Float, nullable=False),
    Column("lng", Float, nullable=False),
    Column("accuracy_m", Float),
    Column("speed_mps", Float),
    Column("ts", UTCDateTime, nullable=False),
    Index("ix_l3_pings_session_ts", "session_id", "ts"),
)

notifications = Table(
    "l3_notifications", metadata,
    Column("notification_id", String(64), primary_key=True),
    Column("session_id", String(64), nullable=False, index=True),
    Column("place_id", String(64)),
    Column("kind", String(16), nullable=False),        # companion | safety
    Column("safety_kind", String(16)),
    Column("message", Text),
    Column("language", String(8)),
    Column("voice", String(16)),
    Column("tier_b_score", Float),
    Column("payload", JSON),
    Column("status", String(16), default="sent"),      # sent | dismissed | engaged
    Column("created_at", UTCDateTime, nullable=False),
    Column("responded_at", UTCDateTime),
)

evaluations = Table(
    "l3_evaluations", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), nullable=False, index=True),
    Column("place_id", String(64)),
    Column("decision", String(16), nullable=False),
    Column("reason", String(96)),
    Column("trigger", String(16)),
    Column("tier_a", JSON),
    Column("tier_b", JSON),
    Column("created_at", UTCDateTime, nullable=False),
)

replan_log = Table(
    "l3_replan_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), nullable=False, index=True),
    Column("original_place_id", String(64), nullable=False),
    Column("substitute_place_id", String(64)),
    Column("role", String(24)),
    Column("reason", String(48)),
    Column("personal_fit", Float),
    Column("created_at", UTCDateTime, nullable=False),
)

visits = Table(
    "l3_visits", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), index=True),
    Column("device_id", String(128), index=True),
    Column("place_id", String(64), nullable=False),
    Column("arrived_at", UTCDateTime),
    Column("exited_at", UTCDateTime),
    Column("dwell_minutes", Float),
    Column("satisfaction", String(8)),                 # up | down | skip
    Column("created_at", UTCDateTime, nullable=False),
)

place_flags = Table(
    "l3_place_flags", metadata,
    Column("place_id", String(64), primary_key=True),
    Column("unavailable", Boolean, nullable=False, default=True),
    Column("reason", String(200)),
    Column("reported_by", String(64)),
    Column("expires_at", UTCDateTime),
    Column("created_at", UTCDateTime, nullable=False),
)

advisories = Table(
    "l3_advisories", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(300), nullable=False),
    Column("severity", String(24), default="warning"),
    Column("area", String(120)),
    Column("source", String(64), default="admin"),
    Column("active", Boolean, default=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("expires_at", UTCDateTime),
)

ask_log = Table(
    "l3_ask_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), index=True),
    Column("place_id", String(64)),
    Column("question", Text),
    Column("answer", Text),
    Column("grounded", Boolean),
    Column("mode", String(24)),
    Column("language", String(8)),
    Column("created_at", UTCDateTime, nullable=False),
)

SESSION_COLUMNS = {c.name for c in sessions.columns}


class AbstractLayer3Repository(ABC):
    @abstractmethod
    def create_all(self) -> None: ...
    @abstractmethod
    def ping_db(self) -> bool: ...

    # sessions
    @abstractmethod
    def save_session(self, data: Dict[str, Any]) -> Dict[str, Any]: ...
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def update_session(self, session_id: str, **fields: Any) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def group_sessions(self, group_session_id: str) -> List[Dict[str, Any]]: ...

    # pings
    @abstractmethod
    def add_ping(self, session_id: str, lat: float, lng: float, ts: datetime,
                 accuracy_m: Optional[float] = None, speed_mps: Optional[float] = None) -> None: ...
    @abstractmethod
    def recent_pings(self, session_id: str, since: datetime) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def latest_ping(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    # notifications / evaluations / logs
    @abstractmethod
    def add_notification(self, data: Dict[str, Any]) -> str: ...
    @abstractmethod
    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def update_notification(self, notification_id: str, **fields: Any) -> None: ...
    @abstractmethod
    def last_safety_notification(self, session_id: str, safety_kind: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def last_place_notification(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def log_evaluation(self, data: Dict[str, Any]) -> None: ...
    @abstractmethod
    def add_replan(self, data: Dict[str, Any]) -> None: ...
    @abstractmethod
    def list_replans(self, session_id: str) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def add_ask(self, data: Dict[str, Any]) -> None: ...

    # visits
    @abstractmethod
    def add_visit(self, data: Dict[str, Any]) -> int: ...
    @abstractmethod
    def visits_for_device(self, device_id: str) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def visits_for_session(self, session_id: str) -> List[Dict[str, Any]]: ...

    # place flags + advisories
    @abstractmethod
    def set_place_flag(self, place_id: str, unavailable: bool, reason: str, reported_by: Optional[str],
                       ttl_hours: Optional[float]) -> None: ...
    @abstractmethod
    def active_unavailable_ids(self) -> set: ...
    @abstractmethod
    def add_advisory(self, title: str, severity: str, area: Optional[str], ttl_hours: Optional[float],
                     source: str = "admin") -> int: ...
    @abstractmethod
    def active_advisories(self) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def deactivate_advisory(self, advisory_id: int) -> bool: ...


class SqlLayer3Repository(AbstractLayer3Repository):
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = self._make_engine(database_url)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_engine(url: str) -> Engine:
        kwargs: Dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
            if url in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool
        eng = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(eng, "connect")
            def _pragma(dbapi_conn, _):  # pragma: no cover - trivial
                cur = dbapi_conn.cursor()
                try:
                    cur.execute("PRAGMA journal_mode=WAL")
                except Exception:
                    pass
                cur.execute("PRAGMA busy_timeout=15000")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        return eng

    def create_all(self) -> None:
        metadata.create_all(self.engine)   # idempotent — only creates missing l3_* tables

    def ping_db(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception as e:  # pragma: no cover
            log.error("DB ping failed: %s", e)
            return False

    @staticmethod
    def _row(row) -> Optional[Dict[str, Any]]:
        return dict(row._mapping) if row is not None else None

    # ------------------------------------------------------------------ sessions
    def save_session(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow()
        rec = {k: v for k, v in data.items() if k in SESSION_COLUMNS}
        rec.setdefault("created_at", now)
        rec["updated_at"] = now
        with self.engine.begin() as c:
            exists = c.execute(select(sessions.c.session_id).where(sessions.c.session_id == rec["session_id"])).first()
            if exists:
                rec.pop("created_at", None)
                c.execute(update(sessions).where(sessions.c.session_id == rec["session_id"]).values(**rec))
            else:
                c.execute(insert(sessions).values(**rec))
        return self.get_session(rec["session_id"])  # type: ignore[return-value]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as c:
            return self._row(c.execute(select(sessions).where(sessions.c.session_id == session_id)).first())

    def update_session(self, session_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        vals = {k: v for k, v in fields.items() if k in SESSION_COLUMNS and k not in ("session_id", "created_at")}
        vals["updated_at"] = utcnow()
        with self.engine.begin() as c:
            c.execute(update(sessions).where(sessions.c.session_id == session_id).values(**vals))
        return self.get_session(session_id)

    def group_sessions(self, group_session_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(select(sessions).where(sessions.c.group_session_id == group_session_id)).all()
        return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------ pings
    def add_ping(self, session_id, lat, lng, ts, accuracy_m=None, speed_mps=None) -> None:
        with self.engine.begin() as c:
            c.execute(insert(pings).values(session_id=session_id, lat=lat, lng=lng, ts=ts,
                                           accuracy_m=accuracy_m, speed_mps=speed_mps))

    def recent_pings(self, session_id: str, since: datetime) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(pings).where(and_(pings.c.session_id == session_id, pings.c.ts >= since)).order_by(pings.c.ts.asc())
            ).all()
        return [dict(r._mapping) for r in rows]

    def latest_ping(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as c:
            return self._row(c.execute(
                select(pings).where(pings.c.session_id == session_id).order_by(pings.c.ts.desc()).limit(1)).first())

    def prune_pings(self, session_id: str, older_than: datetime) -> None:
        with self.engine.begin() as c:
            c.execute(delete(pings).where(and_(pings.c.session_id == session_id, pings.c.ts < older_than)))

    # ------------------------------------------------------------------ notifications & logs
    def add_notification(self, data: Dict[str, Any]) -> str:
        nid = data.get("notification_id") or uuid.uuid4().hex
        rec = {**data, "notification_id": nid, "created_at": data.get("created_at") or utcnow()}
        with self.engine.begin() as c:
            c.execute(insert(notifications).values(**rec))
        return nid

    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as c:
            return self._row(c.execute(select(notifications).where(notifications.c.notification_id == notification_id)).first())

    def update_notification(self, notification_id: str, **fields: Any) -> None:
        with self.engine.begin() as c:
            c.execute(update(notifications).where(notifications.c.notification_id == notification_id).values(**fields))

    def last_safety_notification(self, session_id: str, safety_kind: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as c:
            return self._row(c.execute(
                select(notifications).where(and_(notifications.c.session_id == session_id,
                                                 notifications.c.kind == "safety",
                                                 notifications.c.safety_kind == safety_kind))
                .order_by(notifications.c.created_at.desc()).limit(1)).first())

    def last_place_notification(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as c:
            return self._row(c.execute(
                select(notifications).where(and_(notifications.c.session_id == session_id,
                                                 notifications.c.kind == "companion",
                                                 notifications.c.place_id.is_not(None)))
                .order_by(notifications.c.created_at.desc()).limit(1)).first())

    def log_evaluation(self, data: Dict[str, Any]) -> None:
        with self.engine.begin() as c:
            c.execute(insert(evaluations).values(**{**data, "created_at": data.get("created_at") or utcnow()}))

    def add_replan(self, data: Dict[str, Any]) -> None:
        with self.engine.begin() as c:
            c.execute(insert(replan_log).values(**{**data, "created_at": data.get("created_at") or utcnow()}))

    def list_replans(self, session_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(select(replan_log).where(replan_log.c.session_id == session_id).order_by(replan_log.c.id.asc())).all()
        return [dict(r._mapping) for r in rows]

    def add_ask(self, data: Dict[str, Any]) -> None:
        with self.engine.begin() as c:
            c.execute(insert(ask_log).values(**{**data, "created_at": data.get("created_at") or utcnow()}))

    # ------------------------------------------------------------------ visits
    def add_visit(self, data: Dict[str, Any]) -> int:
        with self.engine.begin() as c:
            res = c.execute(insert(visits).values(**{**data, "created_at": data.get("created_at") or utcnow()}))
            return int(res.inserted_primary_key[0])

    def visits_for_device(self, device_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(select(visits).where(visits.c.device_id == device_id).order_by(visits.c.created_at.asc())).all()
        return [dict(r._mapping) for r in rows]

    def visits_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(select(visits).where(visits.c.session_id == session_id).order_by(visits.c.created_at.asc())).all()
        return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------ place flags
    def set_place_flag(self, place_id, unavailable, reason, reported_by, ttl_hours) -> None:
        now = utcnow()
        expires = now + timedelta(hours=ttl_hours) if ttl_hours else None
        with self.engine.begin() as c:
            exists = c.execute(select(place_flags.c.place_id).where(place_flags.c.place_id == place_id)).first()
            vals = dict(unavailable=unavailable, reason=reason, reported_by=reported_by, expires_at=expires, created_at=now)
            if exists:
                c.execute(update(place_flags).where(place_flags.c.place_id == place_id).values(**vals))
            else:
                c.execute(insert(place_flags).values(place_id=place_id, **vals))

    def active_unavailable_ids(self) -> set:
        now = utcnow()
        with self.engine.connect() as c:
            rows = c.execute(select(place_flags.c.place_id, place_flags.c.expires_at)
                             .where(place_flags.c.unavailable.is_(True))).all()
        return {r[0] for r in rows if r[1] is None or r[1] > now}

    # ------------------------------------------------------------------ advisories
    def add_advisory(self, title, severity, area, ttl_hours, source="admin") -> int:
        now = utcnow()
        with self.engine.begin() as c:
            res = c.execute(insert(advisories).values(
                title=title, severity=severity, area=area, source=source, active=True, created_at=now,
                expires_at=now + timedelta(hours=ttl_hours) if ttl_hours else None))
            return int(res.inserted_primary_key[0])

    def active_advisories(self) -> List[Dict[str, Any]]:
        now = utcnow()
        with self.engine.connect() as c:
            rows = c.execute(select(advisories).where(advisories.c.active.is_(True)).order_by(advisories.c.id.desc())).all()
        return [dict(r._mapping) for r in rows if r._mapping["expires_at"] is None or r._mapping["expires_at"] > now]

    def deactivate_advisory(self, advisory_id: int) -> bool:
        with self.engine.begin() as c:
            res = c.execute(update(advisories).where(advisories.c.id == advisory_id).values(active=False))
            return res.rowcount > 0
