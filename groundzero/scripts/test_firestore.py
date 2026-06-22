import firebase_admin
from firebase_admin import credentials, firestore

try:
    print("Starting Firestore test...")

    cred = credentials.Certificate("credentials.json")
    print("Credentials loaded")

    firebase_admin.initialize_app(cred)
    print("Firebase initialized")

    db = firestore.client(database_id="gzero")
    print("Firestore connected")

    db.collection("test").add({
        "message": "Hello Firestore"
    })

    print("✅ Data written successfully!")

except Exception as e:
    print("ERROR:")
    print(e)