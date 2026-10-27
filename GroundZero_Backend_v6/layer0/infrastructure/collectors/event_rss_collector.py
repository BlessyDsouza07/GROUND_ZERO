"""
Local event / festival RSS collector (blueprint 3.1 source #7... actually
#6 in the numbered list, "Local event / festival RSS feeds"). Feeds
Table 6's "Nearby events" signal and Layer 0 freshness for festival-linked
places.

Real feed parsing via `feedparser` against whatever URLs are configured in
`event_rss_feed_urls` (comma-separated). No feed URLs configured -> no
events collected this run, logged clearly, not faked.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import feedparser
import httpx

logger = logging.getLogger("groundzero.layer0.collectors.event_rss")

SOURCE_NAME = "event_rss"


@dataclass(frozen=True)
class EventEntry:
    title: str
    published: datetime | None
    link: str
    summary: str | None
    feed_url: str


class EventRssCollector:
    def __init__(self, feed_urls: list[str], timeout_seconds: float = 15.0):
        self.feed_urls = feed_urls
        self.timeout_seconds = timeout_seconds

    async def collect(self) -> list[EventEntry]:
        if not self.feed_urls:
            logger.info("%s: no feed URLs configured, skipping", SOURCE_NAME)
            return []

        entries: list[EventEntry] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for feed_url in self.feed_urls:
                try:
                    response = await client.get(feed_url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("%s: failed to fetch %s (%s), skipping this feed", SOURCE_NAME, feed_url, exc)
                    continue

                parsed = feedparser.parse(response.content)
                for item in parsed.entries:
                    published = None
                    if getattr(item, "published_parsed", None):
                        published = datetime(*item.published_parsed[:6])
                    entries.append(
                        EventEntry(
                            title=item.get("title", "Untitled"),
                            published=published,
                            link=item.get("link", ""),
                            summary=item.get("summary"),
                            feed_url=feed_url,
                        )
                    )
        logger.info("%s: collected %d events from %d feeds", SOURCE_NAME, len(entries), len(self.feed_urls))
        return entries
