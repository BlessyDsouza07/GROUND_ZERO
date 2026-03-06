import sqlite3
import json
import os

DB_FILE = "data_storage/mangalore.db"
DATA_FILE = "data_storage/normalized_places.json"

os.makedirs("data_storage", exist_ok=True)

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    latitude REAL,
    longitude REAL,
    place_type TEXT,
    raw_tags TEXT,
    last_updated TEXT
)
""")

with open(DATA_FILE, encoding="utf-8") as f:
    places = json.load(f)

for place in places:
    cursor.execute("""
        INSERT OR REPLACE INTO places
        (id, name, category, latitude, longitude, place_type, raw_tags, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        place["id"],
        place["name"],
        place["category"],
        place["latitude"],
        place["longitude"],
        place["place_type"],
        json.dumps(place["raw_tags"], ensure_ascii=False),
        place["last_updated"]
    ))

conn.commit()
conn.close()

print("✅ All places stored successfully in SQLite database.")
