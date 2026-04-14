"""
events/config_runtime.py
=========================================================

RUNTIME POLICY & COMPLIANCE CONFIGURATION
------------------------------------------

This file defines all runtime safety, legal, and compliance
rules for the Events Engine.

It ensures:

✔ No permanent storage of API data
✔ TTL-based refresh policy
✔ Auto deletion of stale events
✔ 30-day hard cleanup rule
✔ Rate limit compliance
✔ Source attribution enforcement
✔ Cancellation safety
✔ Missing-event sync protection
✔ Bias control safeguards

IMPORTANT:
Do NOT hardcode these values inside collectors.
All collectors must import from this file.

Author: Your Smart City Guide Engine
Last Updated: 2026
=========================================================
"""

from datetime import timedelta
import os


# =========================================================
# 1️⃣ GOLDEN RULE OF CACHING (ANTI-LIABILITY PROTECTION)
# =========================================================
"""
Most ticketing APIs (Ticketmaster, Eventbrite)
require that data must NOT be stored permanently.

If an event is cancelled and your app still shows it,
you could be liable for misinformation.

Solution:
- Apply TTL
- Force refresh
- Delete missing events
"""

# How long API event data can live before forced refresh
API_EVENT_TTL_HOURS = int(os.getenv("API_EVENT_TTL_HOURS", 12))

# Hard delete any event older than X days (regardless of source)
MAX_EVENT_AGE_DAYS = int(os.getenv("MAX_EVENT_AGE_DAYS", 30))


def get_api_ttl():
    """
    Returns timedelta for TTL expiration.
    """
    return timedelta(hours=API_EVENT_TTL_HOURS)


def get_max_event_age():
    """
    Returns timedelta for maximum event lifespan.
    """
    return timedelta(days=MAX_EVENT_AGE_DAYS)


# =========================================================
# 2️⃣ RATE LIMIT CONTROL (DON'T GET BANNED 🚦)
# =========================================================
"""
APIs have strict rate limits.

Ticketmaster Free Tier:
~5 requests per second

We stay below that to avoid:
- IP bans
- API key suspension
"""

REQUESTS_PER_SECOND_LIMIT = int(
    os.getenv("REQUESTS_PER_SECOND_LIMIT", 4)
)

# Delay between each API call (seconds)
REQUEST_DELAY_SECONDS = float(
    os.getenv("REQUEST_DELAY_SECONDS", 0.3)
)

# Optional: enable stricter throttling
ENABLE_RATE_LIMITING = True


# =========================================================
# 3️⃣ SOURCE ATTRIBUTION (MANDATORY BRANDING)
# =========================================================
"""
Many APIs require you to show attribution.

Examples:
- "Tickets provided by Eventbrite"
- "Powered by Ticketmaster"
- Govt Open Data License requires acknowledgement

Your frontend must display source.
"""

REQUIRE_SOURCE_ATTRIBUTION = True

# Standard format for UI rendering
SOURCE_DISPLAY_TEMPLATE = "Data provided by {source_name}"

# Show official source URL in UI
SHOW_SOURCE_URL = True


# =========================================================
# 4️⃣ EVENT STATUS SAFETY RULES
# =========================================================

# Automatically delete cancelled events
DELETE_CANCELLED_EVENTS = True

# Delete events not found in latest live API sync
DELETE_MISSING_FROM_LIVE_FEED = True

# Prevent storing events without a valid date
REJECT_EVENTS_WITHOUT_DATE = True

# Prevent storing events in the past
REJECT_PAST_EVENTS = True


# =========================================================
# 5️⃣ GOVERNMENT DATA DISCLAIMER RULE
# =========================================================
"""
If you use Govt RSS or Open Data:
You must clarify that your app is NOT an official government app.
"""

SHOW_GOVERNMENT_DISCLAIMER = True

GOVERNMENT_DISCLAIMER_TEXT = (
    "This is not an official Government of India application. "
    "Event data is sourced from publicly available government feeds "
    "under the Government Open Data License (GODL-India)."
)


# =========================================================
# 6️⃣ DATA MINIMIZATION POLICY (PRIVACY SAFE MODE)
# =========================================================
"""
You are aggregating PUBLIC event data only.

You must NOT store:
- User emails
- Phone numbers
- Ticket buyer information
"""

ALLOW_USER_DATA_COLLECTION = False

ALLOWED_EVENT_FIELDS = [
    "id",
    "name",
    "category",
    "type",
    "venue",
    "date",
    "source",
    "source_url",
    "status",
]


# =========================================================
# 7️⃣ BIAS / ETHICS ENGINE PROTECTION
# =========================================================
"""
Ensure your recommendation engine does NOT:
- Hide events by religion
- Filter based on caste
- Exclude cultural categories unfairly
"""

ENABLE_BIAS_MONITORING = True

PROTECTED_EVENT_TYPES = [
    "religious_festival",
    "religious_feast",
    "cultural",
    "traditional_sport",
    "performing_arts",
]


# =========================================================
# 8️⃣ AUTO CLEANUP SCHEDULING POLICY
# =========================================================
"""
Defines how often the cleanup process should run.
"""

CLEANUP_RUN_INTERVAL_HOURS = 6


# =========================================================
# 9️⃣ DEBUG MODE (FOR DEVELOPMENT ONLY)
# =========================================================

DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

if DEBUG_MODE:
    print("⚠ DEBUG MODE ENABLED - Not for production use")


# =========================================================
# 🔟 SYSTEM HEALTH CHECK FUNCTION
# =========================================================

def print_runtime_config():
    """
    Prints current runtime configuration.
    Useful for debugging and logging.
    """
    print("===== EVENT ENGINE RUNTIME CONFIG =====")
    print(f"API TTL Hours: {API_EVENT_TTL_HOURS}")
    print(f"Max Event Age (Days): {MAX_EVENT_AGE_DAYS}")
    print(f"Requests/sec Limit: {REQUESTS_PER_SECOND_LIMIT}")
    print(f"Rate Delay (sec): {REQUEST_DELAY_SECONDS}")
    print(f"Delete Cancelled: {DELETE_CANCELLED_EVENTS}")
    print(f"Delete Missing: {DELETE_MISSING_FROM_LIVE_FEED}")
    print(f"Require Attribution: {REQUIRE_SOURCE_ATTRIBUTION}")
    print(f"Allow User Data: {ALLOW_USER_DATA_COLLECTION}")
    print("========================================")
