"""
Accessibility detection (blueprint 3.4 `accessibility_tags`, feeds Layer 2
Hard Filters — "stairs/uneven terrain" exclusion, Table 3 row 4).

Takes the raw OSM tag dict (wheelchair=yes/no/limited, surface=*, etc.) and
derives the structured AccessibilityInfo the rest of the system uses. This
keeps OSM's messy tagging vocabulary out of the domain layer.
"""
from __future__ import annotations

from layer0.domain.entities import AccessibilityInfo

_STAIRS_INDICATORS = {"steps", "stairs"}
_UNEVEN_SURFACES = {"unpaved", "ground", "gravel", "sand", "dirt", "grass", "sett", "cobblestone"}


class AccessibilityDetector:
    def detect(self, osm_tags: dict[str, str]) -> AccessibilityInfo:
        tags: list[str] = []

        wheelchair_raw = osm_tags.get("wheelchair")
        wheelchair: bool | None
        if wheelchair_raw == "yes":
            wheelchair = True
        elif wheelchair_raw in ("no", "limited"):
            wheelchair = False
            if wheelchair_raw == "limited":
                tags.append("limited-wheelchair-access")
        else:
            wheelchair = None

        highway = osm_tags.get("highway", "")
        surface = osm_tags.get("surface", "")
        has_stairs = highway in _STAIRS_INDICATORS or osm_tags.get("stairs") == "yes"
        has_uneven = surface in _UNEVEN_SURFACES

        if has_stairs:
            tags.append("stairs-only")
        if has_uneven:
            tags.append("uneven-terrain")
        if wheelchair is False:
            tags.append("no-wheelchair-access")

        sensory_notes = None
        if osm_tags.get("tactile_paving") == "yes":
            sensory_notes = "tactile paving present"

        return AccessibilityInfo(
            tags=tags,
            wheelchair=wheelchair,
            stairs=has_stairs if (has_stairs or "stairs" in osm_tags) else None,
            sensory_notes=sensory_notes,
        )

    def blocks_for(self, flags: list[str]) -> set[str]:
        """Given a TouristProfile's accessibility_flags, return the set of
        AccessibilityInfo.tags values that should exclude a place. Mirrors
        blueprint 4.3: 'wheelchair' and 'limited_walking' both exclude
        stairs-only / uneven-terrain places."""
        blocking: set[str] = set()
        if "wheelchair" in flags or "limited_walking" in flags:
            blocking.update({"stairs-only", "uneven-terrain", "no-wheelchair-access"})
        return blocking
