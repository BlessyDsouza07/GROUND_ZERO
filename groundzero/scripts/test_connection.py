import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Define API scope
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Load credentials
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

# Authorize client
client = gspread.authorize(creds)

# Open your sheet (PUT YOUR EXACT SHEET NAME HERE)
sheet = client.open_by_key("18IBu3thoOHSBw3GKw5frauhN7ze4kblGSdXi_lBbitI").sheet1


# Print datas
print("✅ Connected successfully!")
#print(sheet.row_values(1))
#print("Headers:")
#print(sheet.row_values(1))
data = sheet.get_all_values()

headers = data[0]
rows = data[1:]

# Clean + make headers unique
unique_headers = []
seen = {}

for h in headers:
    h = h.strip()  # remove extra spaces

    if h == "" or "[]" in h:
        h = "unknown_field"  # handle empty headers

    if h in seen:
        seen[h] += 1
        new_h = f"{h}_{seen[h]}"
    else:
        seen[h] = 0
        new_h = h

    unique_headers.append(new_h)

# Convert to dictionary
for row in rows:
    record = dict(zip(unique_headers, row))
    print(record)
import json

all_data = []

for row in rows:
    record = dict(zip(unique_headers, row))
    all_data.append(record)

# Save to file
with open("data.json", "w") as f:
    json.dump(all_data, f, indent=4)

print("✅ Data saved as JSON")
