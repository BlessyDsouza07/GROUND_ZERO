"""
Deduplication (ETL step 8). The same physical place will surface from
multiple sources — OSM as a node, Wikidata as an entity, a community
submission with a slightly different name spelling. This service decides
whether a newly-collected Place is the same as an existing one, using
haversine distance + normalized name similarity, and merges sources rather
than creating duplicate rows.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from layer0.domain.entities import Place

EARTH_RADIUS_METERS = 6_371_000.0

DEFAULT_DISTANCE_THRESHOLD_METERS = 75.0
DEFAULT_NAME_SIMILARITY_THRESHOLD = 0.82


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\b(the|a|an)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


@dataclass(frozen=True)
class DedupMatch:
    existing: Place
    distance_meters: float
    name_similarity_score: float


class DedupService:
    def __init__(
        self,
        distance_threshold_meters: float = DEFAULT_DISTANCE_THRESHOLD_METERS,
        name_similarity_threshold: float = DEFAULT_NAME_SIMILARITY_THRESHOLD,
    ):
        self.distance_threshold_meters = distance_threshold_meters
        self.name_similarity_threshold = name_similarity_threshold

    def find_best_match(self, candidate: Place, existing_places: list[Place]) -> DedupMatch | None:
        best: DedupMatch | None = None
        for existing in existing_places:
            distance = haversine_meters(
                candidate.coordinates.latitude, candidate.coordinates.longitude,
                existing.coordinates.latitude, existing.coordinates.longitude,
            )
            if distance > self.distance_threshold_meters:
                continue
            similarity = name_similarity(candidate.name, existing.name)
            if similarity < self.name_similarity_threshold:
                continue
            if best is None or distance < best.distance_meters:
                best = DedupMatch(existing=existing, distance_meters=distance, name_similarity_score=similarity)
        return best

    def merge(self, existing: Place, incoming: Place) -> Place:
        """Merge incoming source's data into the existing record. Prefers
        non-null/richer values, unions tags and sources, never silently
        drops a previously-known field just because the new source lacks it."""
        existing.tags = sorted(set(existing.tags) | set(incoming.tags))
        existing.source = list({*existing.source, *incoming.source})
        existing.description = existing.description or incoming.description
        existing.wiki_summary = existing.wiki_summary or incoming.wiki_summary
        existing.transport_access = existing.transport_access or incoming.transport_access
        existing.etiquette_tag = existing.etiquette_tag or incoming.etiquette_tag

        # bias signal accumulation: take the max media_mentions seen (a
        # source undercounting shouldn't erase a higher count from another).
        existing.bias_signals.media_mentions = max(
            existing.bias_signals.media_mentions, incoming.bias_signals.media_mentions
        )
        if incoming.bias_signals.local_percentage:
            existing.bias_signals.local_percentage = (
                existing.bias_signals.local_percentage + incoming.bias_signals.local_percentage
            ) / 2

        if incoming.last_verified_at and (
            existing.last_verified_at is None or incoming.last_verified_at > existing.last_verified_at
        ):
            existing.last_verified_at = incoming.last_verified_at

        return existing
