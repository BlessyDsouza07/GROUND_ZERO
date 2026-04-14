"""
data_storage/city_database.py  [v3 — Five-Layer Schema]

SQLite storage for all Ground Zero entity layers.
Schema stores Layer 1 columns directly + Layers 2-5 as JSON blobs.
This makes queries fast for structural fields while keeping layers flexible.
"""

import sqlite3, json, os
from typing import List, Dict, Optional
from datetime import datetime, timezone
from core.base_models import BaseEntity
from utils.logger import get_logger

logger = get_logger("CityDatabase")
DB_FILE = "data_storage/mangalore.db"


class CityDatabase:

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        conn = self._connect()
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS places (
            osm_id          TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            domain          TEXT,
            category        TEXT,
            subcategory     TEXT,
            latitude        REAL,
            longitude       REAL,

            -- Layer 1: Structural practical fields (fast-query columns)
            address         TEXT,
            phone           TEXT,
            website         TEXT,
            opening_hours   TEXT,
            cuisine         TEXT,
            wheelchair      TEXT,
            description     TEXT,

            -- Scores
            structural_score         REAL DEFAULT 0.0,
            final_authenticity_score REAL DEFAULT 0.0,
            formula_score            REAL DEFAULT 0.0,
            grade                    TEXT DEFAULT 'D',
            unexplored_flag          INTEGER DEFAULT 0,
            hidden_gem_tier          INTEGER DEFAULT 0,

            -- Layers 2-5 as JSON blobs
            layer_contextual    TEXT,
            layer_behavioral    TEXT,
            layer_authenticity  TEXT,
            layer_experience    TEXT,

            -- Metadata
            sources         TEXT,
            last_updated    TEXT
        )""")

        # Indexes for common HIVE Engine queries
        for idx, col in [
            ("idx_places_domain",      "domain"),
            ("idx_places_grade",       "grade"),
            ("idx_places_location",    "latitude, longitude"),
            ("idx_places_unexplored",  "unexplored_flag"),
            ("idx_places_score",       "final_authenticity_score"),
        ]:
            c.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON places({col})")

        # Full-text search
        c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS places_fts
        USING fts5(osm_id UNINDEXED, name, category, description, cuisine,
                   content='places', content_rowid='rowid')""")

        # Events table
        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id     TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            category     TEXT,
            venue        TEXT,
            start_date   TEXT,
            source       TEXT,
            source_url   TEXT,
            feast_season TEXT,
            status       TEXT DEFAULT 'active',
            collected_at TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date)")

        # Weather snapshots
        c.execute("""
        CREATE TABLE IF NOT EXISTS weather_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            condition     TEXT,
            temperature_c REAL,
            humidity      REAL,
            wind_speed    REAL,
            description   TEXT,
            crowd_modifier REAL,
            fetched_at    TEXT
        )""")

        conn.commit()
        conn.close()

    def upsert_entities(self, entities: List[BaseEntity]) -> int:
        conn = self._connect()
        c    = conn.cursor()
        count = 0

        for entity in entities:
            # Extract Layer 1 practical fields from decision_trace
            extra = {}
            osm_id = None
            for t in entity.decision_trace:
                if t.startswith("OSM_ID:"):
                    osm_id = t.replace("OSM_ID:", "").strip()
                for prefix in ("OSM_EXTRA:", "HG_META:"):
                    if t.startswith(prefix):
                        try:
                            extra = json.loads(t[len(prefix):])
                        except Exception:
                            pass

            if not osm_id:
                osm_id = entity.entity_id

            c.execute("""
            INSERT OR REPLACE INTO places
            (osm_id, name, domain, category, subcategory,
             latitude, longitude,
             address, phone, website, opening_hours, cuisine, wheelchair, description,
             structural_score, final_authenticity_score, formula_score, grade,
             unexplored_flag, hidden_gem_tier,
             layer_contextual, layer_behavioral, layer_authenticity, layer_experience,
             sources, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                osm_id, entity.name,
                entity.domain.value, entity.category, entity.subcategory,
                entity.latitude, entity.longitude,
                extra.get("address"),
                extra.get("phone") or extra.get("contact:phone"),
                extra.get("website"),
                extra.get("opening_hours"),
                extra.get("cuisine"),
                extra.get("wheelchair") or extra.get("wheelchair_accessible"),
                extra.get("description", "")[:600],
                entity.structural_score,
                entity.final_authenticity_score,
                entity.authenticity.compute_formula_score(),
                entity.grade.value,
                1 if extra.get("unexplored_flag") else 0,
                int(extra.get("hidden_gem_tier", 0) or 0),
                json.dumps(entity.contextual.to_dict()),
                json.dumps(entity.behavioral.to_dict()),
                json.dumps({**entity.authenticity.to_dict(),
                            "formula_score": entity.authenticity.compute_formula_score()}),
                json.dumps(entity.experience.to_dict()),
                json.dumps(entity.sources),
                datetime.now(timezone.utc).isoformat()
            ))
            count += 1

        conn.commit()
        conn.close()
        logger.info(f"  Upserted {count} entities")
        return count

    def query_by_domain(self, domain: str) -> List[Dict]:
        conn = self._connect()
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM places WHERE domain=? ORDER BY final_authenticity_score DESC",
            (domain,)).fetchall()]
        conn.close()
        return rows

    def query_unexplored(self) -> List[Dict]:
        conn = self._connect()
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM places WHERE unexplored_flag=1 ORDER BY final_authenticity_score DESC"
        ).fetchall()]
        conn.close()
        return rows

    def search_places(self, query: str) -> List[Dict]:
        conn = self._connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT p.* FROM places p JOIN places_fts fts ON p.osm_id=fts.osm_id "
                "WHERE places_fts MATCH ? ORDER BY p.final_authenticity_score DESC LIMIT 20",
                (query,)).fetchall()]
        except Exception:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM places WHERE name LIKE ? LIMIT 20",
                (f"%{query}%",)).fetchall()]
        conn.close()
        return rows

    def query_near(self, lat: float, lon: float, radius_km: float = 1.0) -> List[Dict]:
        delta = radius_km / 111.0
        conn  = self._connect()
        rows  = [dict(r) for r in conn.execute(
            "SELECT * FROM places WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ? "
            "ORDER BY final_authenticity_score DESC",
            (lat - delta, lat + delta, lon - delta, lon + delta)).fetchall()]
        conn.close()
        return rows

    def upsert_events(self, events: List[Dict]) -> int:
        conn = self._connect()
        c    = conn.cursor()
        count = 0
        for ev in events:
            c.execute("""
            INSERT OR REPLACE INTO events
            (event_id, name, category, venue, start_date, source, source_url,
             feast_season, status, collected_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                ev.get("id") or ev.get("event_signature", ""),
                ev.get("name", ""),
                ev.get("category", "event"),
                ev.get("venue", ""),
                ev.get("date") or ev.get("start_date", ""),
                ev.get("source", ""),
                ev.get("source_url", ""),
                ev.get("feast_season", ""),
                ev.get("status", "active"),
                datetime.now(timezone.utc).isoformat()
            ))
            count += 1
        conn.commit()
        conn.close()
        return count

    def save_weather(self, weather: Dict):
        conn = self._connect()
        conn.execute("""
        INSERT INTO weather_snapshots
        (condition, temperature_c, humidity, wind_speed, description, crowd_modifier, fetched_at)
        VALUES (?,?,?,?,?,?,?)
        """, (
            weather.get("condition", ""),
            weather.get("temperature_c", 0),
            weather.get("humidity", 0),
            weather.get("wind_speed", 0),
            weather.get("description", ""),
            weather.get("crowd_modifier", 1.0),
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()

    def stats(self) -> Dict:
        conn = self._connect()
        total = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        domains = {r[0]: r[1] for r in conn.execute("SELECT domain, COUNT(*) FROM places GROUP BY domain").fetchall()}
        unexplored = conn.execute("SELECT COUNT(*) FROM places WHERE unexplored_flag=1").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        grades = {r[0]: r[1] for r in conn.execute("SELECT grade, COUNT(*) FROM places GROUP BY grade").fetchall()}
        conn.close()
        return {
            "total_places": total, "by_domain": domains,
            "unexplored": unexplored, "events": events, "grades": grades
        }
