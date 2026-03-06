import json
import hashlib
import os
from datetime import datetime

OLD_FILE = "data_storage/normalized_places_old.json"
NEW_FILE = "data_storage/normalized_places.json"
CHANGE_LOG = "logs/change_log.json"

os.makedirs("logs", exist_ok=True)

def hash_place(place):
    """Create stable hash ignoring last_updated"""
    filtered = {
        "id": place["id"],
        "name": place["name"],
        "category": place["category"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "place_type": place["place_type"]
    }
    return hashlib.md5(json.dumps(filtered, sort_keys=True).encode()).hexdigest()

# If first run, initialize old file
if not os.path.exists(OLD_FILE):
    with open(NEW_FILE, "r", encoding="utf-8") as f:
        json.dump(json.load(f), open(OLD_FILE, "w", encoding="utf-8"), indent=2)
    print("✅ Initial snapshot saved. No changes yet.")
    exit()

old_data = json.load(open(OLD_FILE, encoding="utf-8"))
new_data = json.load(open(NEW_FILE, encoding="utf-8"))

old_map = {p["id"]: hash_place(p) for p in old_data}

added, updated = [], []

for place in new_data:
    place_hash = hash_place(place)
    if place["id"] not in old_map:
        added.append(place)
    elif old_map[place["id"]] != place_hash:
        updated.append(place)

change_report = {
    "timestamp": datetime.utcnow().isoformat(),
    "new_places": len(added),
    "updated_places": len(updated),
    "added_ids": [p["id"] for p in added],
    "updated_ids": [p["id"] for p in updated]
}

with open(CHANGE_LOG, "w", encoding="utf-8") as f:
    json.dump(change_report, f, indent=2)

# Update snapshot
with open(OLD_FILE, "w", encoding="utf-8") as f:
    json.dump(new_data, f, indent=2)

print("✅ Change detection complete.")
print(f"➕ New places: {len(added)}")
print(f"♻ Updated places: {len(updated)}")
