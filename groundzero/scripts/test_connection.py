import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Define API scope
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Load credentials
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "../credentials.json",
    scope
)

# Authorize client
client = gspread.authorize(creds)

# Open your sheet (PUT YOUR EXACT SHEET NAME HERE)
sheet = client.open_by_key("1SktMSfhM216w4pgm-yOw-RJZzmUMWKm4upK3nyspouk").sheet1


# Print datas
print("✅ Connected successfully!")
print(sheet.get_all_records())
