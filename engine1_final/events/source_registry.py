"""
events/source_registry.py
========================================================

SOURCE REGISTRY (Governance Layer)
--------------------------------------------------------

This file acts as the master authority for:
✔ Approved data sources
✔ License tracking
✔ Attribution requirements
✔ Source classification
✔ API contract enforcement
✔ RSS verification
✔ Government Open Data compliance

All collectors must register their sources here.

If a source is not registered here,
it should NOT be used.

========================================================
"""

from typing import Dict, Optional


# =====================================================
# SOURCE TYPES
# =====================================================

SOURCE_TYPE_TICKETING = "ticketing_api"
SOURCE_TYPE_GOVERNMENT = "government_feed"
SOURCE_TYPE_MEDIA = "media_rss"
SOURCE_TYPE_CURATED = "curated_internal"


# =====================================================
# LICENSE TYPES
# =====================================================

LICENSE_API_CONTRACT = "api_contract"
LICENSE_GODL_INDIA = "government_open_data_license_india"
LICENSE_PUBLIC_RSS = "public_rss"
LICENSE_INTERNAL = "internal_dataset"


# =====================================================
# MASTER SOURCE REGISTRY
# =====================================================

REGISTERED_SOURCES: Dict[str, Dict] = {

    # ─────────────────────────────────────────
    # TICKETING APIs
    # ─────────────────────────────────────────

    "Ticketmaster": {
        "type": SOURCE_TYPE_TICKETING,
        "license": LICENSE_API_CONTRACT,
        "requires_attribution": True,
        "requires_logo_display": True,
        "official_url": "https://developer.ticketmaster.com/",
        "active": True,
    },

    "Eventbrite": {
        "type": SOURCE_TYPE_TICKETING,
        "license": LICENSE_API_CONTRACT,
        "requires_attribution": True,
        "requires_logo_display": True,
        "official_url": "https://www.eventbrite.com/platform/api/",
        "active": True,
    },

    # ─────────────────────────────────────────
    # GOVERNMENT FEEDS
    # ─────────────────────────────────────────

    "Karnataka Tourism": {
        "type": SOURCE_TYPE_GOVERNMENT,
        "license": LICENSE_GODL_INDIA,
        "requires_attribution": True,
        "requires_logo_display": False,
        "official_url": "https://karnatakatourism.org/",
        "active": True,
    },

    "Dakshina Kannada District": {
        "type": SOURCE_TYPE_GOVERNMENT,
        "license": LICENSE_GODL_INDIA,
        "requires_attribution": True,
        "requires_logo_display": False,
        "official_url": "https://dk.nic.in/",
        "active": True,
    },

    # ─────────────────────────────────────────
    # MEDIA RSS
    # ─────────────────────────────────────────

    "Udayavani Events": {
        "type": SOURCE_TYPE_MEDIA,
        "license": LICENSE_PUBLIC_RSS,
        "requires_attribution": True,
        "requires_logo_display": False,
        "official_url": "https://www.udayavani.com/",
        "active": True,
    },

    "The Hindu - Karnataka": {
        "type": SOURCE_TYPE_MEDIA,
        "license": LICENSE_PUBLIC_RSS,
        "requires_attribution": True,
        "requires_logo_display": False,
        "official_url": "https://www.thehindu.com/",
        "active": True,
    },

    "Mangalore Today": {
        "type": SOURCE_TYPE_MEDIA,
        "license": LICENSE_PUBLIC_RSS,
        "requires_attribution": True,
        "requires_logo_display": False,
        "official_url": "https://www.mangaloretoday.com/",
        "active": True,
    },

    # ─────────────────────────────────────────
    # INTERNAL CURATED DATA
    # ─────────────────────────────────────────

    "Mangalore Curated Dataset": {
        "type": SOURCE_TYPE_CURATED,
        "license": LICENSE_INTERNAL,
        "requires_attribution": False,
        "requires_logo_display": False,
        "official_url": None,
        "active": True,
    },
}


# =====================================================
# REGISTRY CLASS
# =====================================================

class SourceRegistry:
    """
    Provides validation and governance utilities
    for event sources.
    """

    @staticmethod
    def is_registered(source_name: str) -> bool:
        return source_name in REGISTERED_SOURCES

    @staticmethod
    def is_active(source_name: str) -> bool:
        source = REGISTERED_SOURCES.get(source_name)
        if not source:
            return False
        return source.get("active", False)

    @staticmethod
    def get_source_metadata(source_name: str) -> Optional[Dict]:
        return REGISTERED_SOURCES.get(source_name)

    @staticmethod
    def requires_attribution(source_name: str) -> bool:
        source = REGISTERED_SOURCES.get(source_name)
        if not source:
            return False
        return source.get("requires_attribution", False)

    @staticmethod
    def requires_logo_display(source_name: str) -> bool:
        source = REGISTERED_SOURCES.get(source_name)
        if not source:
            return False
        return source.get("requires_logo_display", False)

    @staticmethod
    def get_license_type(source_name: str) -> Optional[str]:
        source = REGISTERED_SOURCES.get(source_name)
        if not source:
            return None
        return source.get("license")

    @staticmethod
    def validate_source(source_name: str) -> bool:
        """
        Full validation:
        ✔ Must be registered
        ✔ Must be active
        """
        if not SourceRegistry.is_registered(source_name):
            print(f"❌ Source not registered: {source_name}")
            return False

        if not SourceRegistry.is_active(source_name):
            print(f"❌ Source is inactive: {source_name}")
            return False

        return True

    @staticmethod
    def list_all_sources():
        return list(REGISTERED_SOURCES.keys())

    @staticmethod
    def deactivate_source(source_name: str):
        if source_name in REGISTERED_SOURCES:
            REGISTERED_SOURCES[source_name]["active"] = False

    @staticmethod
    def activate_source(source_name: str):
        if source_name in REGISTERED_SOURCES:
            REGISTERED_SOURCES[source_name]["active"] = True
