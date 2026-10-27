"""
Wikidata collector (blueprint 3.1 source #2, enrichment step per ETL Step 2).

Given a place name + approximate coordinates, queries Wikidata's SPARQL
endpoint for a matching entity within a small radius and pulls back
structured enrichment: description, inception date, heritage status,
image, and a Wikipedia sitelink (handed to the Wikipedia collector next).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable

logger = logging.getLogger("groundzero.layer0.collectors.wikidata")

SOURCE_NAME = "wikidata"


@dataclass(frozen=True)
class WikidataEnrichment:
    qid: str
    description: str | None
    heritage_status: str | None
    wikipedia_title: str | None
    image_url: str | None


def build_nearby_query(lat: float, lon: float, radius_km: float, name_hint: str) -> str:
    # geosearch via wdt:P625 (coordinate location) within radius_km of the point,
    # optionally filtered by an approximate label match on name_hint.
    escaped_hint = name_hint.replace('"', '\\"')
    return f"""
SELECT ?item ?itemLabel ?description ?heritage ?heritageLabel ?article ?image WHERE {{
  SERVICE wikibase:around {{
    ?item wdt:P625 ?location .
    bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "{radius_km}" .
  }}
  OPTIONAL {{ ?item schema:description ?description . FILTER(LANG(?description) = "en") }}
  OPTIONAL {{ ?item wdt:P1435 ?heritage . }}
  OPTIONAL {{ ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?item wdt:P18 ?image . }}
  ?item rdfs:label ?itemLabel .
  FILTER(LANG(?itemLabel) = "en")
  FILTER(CONTAINS(LCASE(?itemLabel), LCASE("{escaped_hint}")))
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 5
""".strip()


class WikidataCollector:
    def __init__(self, http_client: ResilientHttpClient, sparql_url: str):
        self.http_client = http_client
        self.sparql_url = sparql_url

    async def enrich(
        self, lat: float, lon: float, name_hint: str, radius_km: float = 0.15
    ) -> WikidataEnrichment | None:
        query = build_nearby_query(lat, lon, radius_km, name_hint)
        try:
            response = await self.http_client.request(
                SOURCE_NAME, "GET", self.sparql_url,
                params={"query": query, "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
            )
        except SourceUnavailable:
            logger.warning("%s: source unavailable this run, skipping enrichment for '%s'", SOURCE_NAME, name_hint)
            raise

        bindings = response.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None

        row = bindings[0]
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        wikipedia_title = None
        if "article" in row:
            wikipedia_title = row["article"]["value"].rsplit("/", 1)[-1].replace("_", " ")

        return WikidataEnrichment(
            qid=qid,
            description=row.get("description", {}).get("value"),
            heritage_status=row.get("heritageLabel", {}).get("value"),
            wikipedia_title=wikipedia_title,
            image_url=row.get("image", {}).get("value"),
        )
