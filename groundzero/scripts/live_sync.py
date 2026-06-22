import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import firebase_admin
from firebase_admin import credentials, firestore

# -----------------------
# Google Sheets Setup
# -----------------------

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

sheet_creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

client = gspread.authorize(sheet_creds)

sheet = client.open_by_key(
    "18IBu3thoOHSBw3GKw5frauhN7ze4kblGSdXi_lBbitI"
).sheet1

# -----------------------
# Firestore Setup
# -----------------------

cred = credentials.Certificate("credentials.json")

try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

db = firestore.client(database_id="gzero")

print("✅ Sync service started")

# -----------------------
# Continuous Sync
# -----------------------

while True:

    try:

        headers = sheet.row_values(1)

        rows = sheet.get_all_records(
            expected_headers=headers
        )

        for row in rows:

            timestamp = row.get("Timestamp")

            if not timestamp:
                continue

            doc_ref = db.collection(
                "processed_responses"
            ).document(timestamp)

            if not doc_ref.get().exists:

                db.collection(
                    "responses"
                ).add(row)

                doc_ref.set({
                    "processed": True
                })

                print(
                    f"✅ Uploaded: {timestamp}"
                )

        time.sleep(60)

    except Exception as e:

        print("❌ Error:", e)
        time.sleep(60)