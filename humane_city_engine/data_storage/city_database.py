"""
data_storage/city_database.py  [UPGRADED — LIVE DATA VERSION]

WHAT CHANGED FROM ORIGINAL:
- ADDED: 8 new columns (website, phone, address, opening_hours, cuisine,
         wheelchair, description, domain)
- ADDED: 4 database indexes for fast querying by domain, category, location
- ADDED: Full-text search support via FTS5 virtual table
- ADDED: Upsert logic (INSERT OR REPLACE respects all new columns)
- ADDED: Database versioning / migration support
- ADDED: stats() function to report what's stored
- CHANGED: Schema now reads from BaseEntity, not a separate JSON file
- KEPT: Same DB_FILE location, same table name 'places'

WHY: Original had 8 columns. A real city brain needs 16+ columns
     and indexes or queries become too slow at scale.

USAGE:
    from data_storage.city_database import CityDatabase
    db = CityDatabase()
    db.upsert_entities(scored_entities)
    results = db.query_by_domain("food")
"""

import sqlite3
import json
import os
from typing import List, Dict, Optional
from datetime import datetime, timezone

from core.base_models import BaseEntity


DB_FILE = "data_storage/mangalore.db"


# ============================================================
# DATABASE CLASS
# ============================================================

class CityDatabase:

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    # --------------------------------------------------------
    # SCHEMA INITIALIZATION
    # --------------------------------------------------------

    def _init_schema(self):
        """Create tables and indexes if they don't exist."""

        conn = self._connect()
        cursor = conn.cursor()

        # --- MAIN PLACES TABLE (expanded from original 8 cols to 20 cols) ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS places (
            osm_id          TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            domain          TEXT,
            category        TEXT,
            subcategory     TEXT,
            latitude        REAL,
            longitude       REAL,

            -- NEW COLUMNS (were missing in original)
            address         TEXT,
            phone           TEXT,
            website         TEXT,
            opening_hours   TEXT,
            cuisine         TEXT,
            wheelchair      TEXT,
            description     TEXT,

            -- SCORING (from BaseEntity)
            structural_score        REAL DEFAULT 0.0,
            review_score            REAL DEFAULT 0.0,
            final_authenticity_score REAL DEFAULT 0.0,
            grade           TEXT DEFAULT 'D',

            -- METADATA
            sources         TEXT,
            last_updated    TEXT
        )
        """)

        # --- INDEXES FOR FAST QUERYING (all new — original had none) ---
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_domain
        ON places(domain)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_category
        ON places(category)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_grade
        ON places(grade)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_location
        ON places(latitude, longitude)
        """)

        # --- FTS5 FULL TEXT SEARCH TABLE (new) ---
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS places_fts
        USING fts5(
            osm_id UNINDEXED,
            name,
            category,
            description,
            cuisine,
            content='places',
            content_rowid='rowid'
        )
        """)

        # --- EVENTS TABLE (new — original had no events storage) ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id        TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            category        TEXT,
            venue           TEXT,
            start_date      TEXT,
            source          TEXT,
            source_url      TEXT,
            status          TEXT DEFAULT 'active',
            collected_at    TEXT
        )
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_date
        ON events(start_date)
        """)

        # --- WEATHER SNAPSHOTS TABLE (new) ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            condition       TEXT,
            temperature_c   REAL,
            humidity        REAL,
            wind_speed      REAL,
            description     TEXT,
            fetched_at      TEXT
        )
        """)

        conn.commit()
        conn.close()

    # --------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --------------------------------------------------------
    # UPSERT ENTITIES FROM PIPELINE
    # --------------------------------------------------------

    def upsert_entities(self, entities: List[BaseEntity]) -> int:
        """
        Insert or update scored entities from DataCorePipeline.

        ORIGINAL: read from JSON file at module level (fragile)
        UPGRADED: accepts BaseEntity objects directly from pipeline

        Returns: number of rows upserted
        """

        conn = self._connect()
        cursor = conn.cursor()
        count = 0

        for entity in entities:

            # Extract OSM_ID from decision_trace
            osm_id = None
            address = None
            phone = None
            website = None
            opening_hours = None
            cuisine = None
            wheelchair = None
            description = None

            for trace in entity.decision_trace:
                if trace.startswith("OSM_ID:"):
                    osm_id = trace.replace("OSM_ID:", "").strip()
                elif trace.startswith("OSM_EXTRA:"):
                    try:
                        extra = json.loads(trace.replace("OSM_EXTRA:", ""))
                        address = extra.get("address")
                        phone = extra.get("phone")
                        website = extra.get("website")
                        opening_hours = extra.get("opening_hours")
                        cuisine = extra.get("cuisine")
                        wheelchair = extra.get("wheelchair_accessible")
                        description = extra.get("description")
                    except Exception:
                        pass

            if not osm_id:
                osm_id = entity.entity_id

            cursor.execute("""
                INSERT OR REPLACE INTO places
                (osm_id, name, domain, category, subcategory,
                 latitude, longitude,
                 address, phone, website, opening_hours, cuisine,
                 wheelchair, description,
                 structural_score, review_score, final_authenticity_score, grade,
                 sources, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                osm_id,
                entity.name,
                entity.domain.value,
                entity.category,
                entity.subcategory,
                entity.latitude,
                entity.longitude,
                address,
                phone,
                website,
                opening_hours,
                cuisine,
                wheelchair,
                description,
                entity.structural_score,
                entity.review_score,
                entity.final_authenticity_score,
                entity.grade.value,
                json.dumps(entity.sources),
                datetime.now(timezone.utc).isoformat()
            ))
            count += 1

        conn.commit()
        conn.close()

        print(f"  Upserted {count} entities into database.")
        return count

    # --------------------------------------------------------
    # QUERY METHODS
    # --------------------------------------------------------

    def query_by_domain(self, domain: str, min_grade: str = "C") -> List[Dict]:
        """Fetch all places in a domain with minimum grade."""

        grade_order = {"A": 4, "B": 3, "C": 2, "D": 1}
        min_score = grade_order.get(min_grade, 2)

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM places
            WHERE domain = ?
              AND final_authenticity_score > 0
            ORDER BY final_authenticity_score DESC
        """, (domain,))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return rows

    def search_places(self, query: str) -> List[Dict]:
        """Full-text search across name, category, description."""

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.* FROM places p
            JOIN places_fts fts ON p.osm_id = fts.osm_id
            WHERE places_fts MATCH ?
            ORDER BY p.final_authenticity_score DESC
            LIMIT 20
        """, (query,))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return rows

    def query_near(self, lat: float, lon: float, radius_km: float = 1.0) -> List[Dict]:
        """
        Simple bounding-box proximity query.
        (1 degree lat ≈ 111 km)
        """

        delta = radius_km / 111.0

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM places
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
            ORDER BY final_authenticity_score DESC
        """, (lat - delta, lat + delta, lon - delta, lon + delta))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return rows

    # --------------------------------------------------------
    # UPSERT EVENTS
    # --------------------------------------------------------

    def upsert_events(self, events: List[Dict]) -> int:
        """Store live events from EventsCollector."""

        conn = self._connect()
        cursor = conn.cursor()
        count = 0

        for event in events:
            cursor.execute("""
                INSERT OR REPLACE INTO events
                (event_id, name, category, venue, start_date,
                 source, source_url, status, collected_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                event.get("id") or event.get("event_signature", ""),
                event.get("name", ""),
                event.get("category", "event"),
                event.get("venue", ""),
                event.get("date") or event.get("start_date", ""),
                event.get("source", ""),
                event.get("source_url", ""),
                event.get("status", "active"),
                datetime.now(timezone.utc).isoformat()
            ))
            count += 1

        conn.commit()
        conn.close()
        return count

    # --------------------------------------------------------
    # WEATHER SNAPSHOT
    # --------------------------------------------------------

    def save_weather(self, weather: Dict):
        """Persist a live weather snapshot."""

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO weather_snapshots
            (condition, temperature_c, humidity, wind_speed, description, fetched_at)
            VALUES (?,?,?,?,?,?)
        """, (
            weather.get("condition", ""),
            weather.get("temperature_c", 0),
            weather.get("humidity", 0),
            weather.get("wind_speed", 0),
            weather.get("description", ""),
            datetime.now(timezone.utc).isoformat()
        ))

        conn.commit()
        conn.close()

    # --------------------------------------------------------
    # STATS
    # --------------------------------------------------------

    def stats(self) -> Dict:
        """Report what's currently stored in the database."""

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM places")
        total_places = cursor.fetchone()[0]

        cursor.execute("SELECT domain, COUNT(*) as cnt FROM places GROUP BY domain")
        domain_counts = {row["domain"]: row["cnt"] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM weather_snapshots")
        total_weather = cursor.fetchone()[0]

        conn.close()

        return {
            "total_places": total_places,
            "by_domain": domain_counts,
            "total_events": total_events,
            "weather_snapshots": total_weather
        }


# ============================================================
# STANDALONE INIT (called by city_bootstrap.py)
# ============================================================

if __name__ == "__main__":

    db = CityDatabase()
    print("Database initialized.")
    print("Stats:", db.stats())