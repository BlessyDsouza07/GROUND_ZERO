"""
Wikipedia collector (blueprint 3.1 source #2, ETL Step 3).

Uses Wikipedia's REST summary endpoint to pull a plain-text extract for a
page title handed off from the Wikidata collector's sitelink. Stored as
`wiki_summary` on the Place record.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

from layer0.infrastructure.http_client import ResilientHttpClient, SourceUnavailable

logger = logging.getLogger("groundzero.layer0.collectors.wikipedia")

SOURCE_NAME = "wikipedia"


@dataclass(frozen=True)
class WikipediaSummary:
    title: str
    extract: str
    page_url: str | None


class WikipediaCollector:
    def __init__(self, http_client: ResilientHttpClient, base_rest_url: str = "https://en.wikipedia.org/api/rest_v1"):
        self.http_client = http_client
        self.base_rest_url = base_rest_url

    async def summary(self, title: str) -> WikipediaSummary | None:
        encoded_title = quote(title.replace(" ", "_"))
        url = f"{self.base_rest_url}/page/summary/{encoded_title}"
        try:
            response = await self.http_client.request(SOURCE_NAME, "GET", url)
        except SourceUnavailable:
            logger.warning("%s: source unavailable this run, skipping summary for '%s'", SOURCE_NAME, title)
            raise

        if response.status_code == 404:
            return None

        data = response.json()
        extract = data.get("extract")
        if not extract:
            return None

        return WikipediaSummary(
            title=data.get("title", title),
            extract=extract,
            page_url=data.get("content_urls", {}).get("desktop", {}).get("page"),
        )
