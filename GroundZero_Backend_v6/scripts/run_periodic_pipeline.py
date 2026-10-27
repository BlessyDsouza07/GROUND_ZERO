"""
Keeps the Master Data Core continuously fresh and verified.

The blueprint (Section 3, Layer 0) says the Background Engine runs "24/7,
always." As shipped, `/admin/pipeline/run` only runs when someone calls
it — there is no scheduler wired in. This script is the honest, minimal
way to make that real without adding a new dependency (no APScheduler,
no Celery): it just calls the existing, already-authenticated admin
endpoint on a loop.

What "verified and fresh" actually means here, concretely:
  - Every place the OSM/Wikidata/Wikipedia/spreadsheet sources still
    confirm gets `last_verified_at` reset to now every run, which is what
    keeps `freshness_score` (see layer0/application/freshness.py) near
    1.0 for that place.
  - A place that stops showing up in a fresh pull (closed, demolished,
    relocated, or simply gone from OSM) stops getting its
    `last_verified_at` refreshed, so its freshness_score decays over the
    following days/weeks and Layer 2's Hard Filters (5.1) will eventually
    stop recommending it on their own — no manual cleanup step required.
  - Running this daily (rather than the 180-day stale_after_days decay
    window) catches closures far faster than waiting for natural decay.

This does NOT invent a live "is this exact place still open right now"
check against Google/Zomato — no such free, legal, unlimited API exists.
It re-runs the same real, legal collectors the rest of Layer 0 uses.

Usage (see also the execution guide):

    python scripts/run_periodic_pipeline.py --interval-hours 24

Run this in the background (a systemd service, a `pm2` process, a
Windows Scheduled Task calling it once, or just a terminal you leave
open) on the same machine/server as the main API — not in this sandbox,
which has no route to the OSM/Wikidata endpoints.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("groundzero.periodic_pipeline")


async def run_once(base_url: str, admin_api_key: str) -> None:
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{base_url}/admin/pipeline/run",
            headers={"X-Admin-Api-Key": admin_api_key},
        )
    if response.status_code != 200:
        logger.error("Pipeline run failed: HTTP %s — %s", response.status_code, response.text[:500])
        return

    report = response.json()
    logger.info(
        "Pipeline run OK — OSM:%s stored:%s dedup_removed:%s skipped_sources:%s errors:%s",
        report.get("osm_elements_collected"),
        report.get("places_stored"),
        report.get("duplicates_removed"),
        report.get("sources_skipped"),
        len(report.get("errors", [])),
    )


async def main_loop(base_url: str, admin_api_key: str, interval_hours: float, run_forever: bool) -> None:
    while True:
        logger.info("Starting pipeline run at %s", datetime.now(timezone.utc).isoformat())
        try:
            await run_once(base_url, admin_api_key)
        except Exception:  # noqa: BLE001 — one bad run must not kill the loop
            logger.exception("Pipeline run raised an unexpected error; will retry next interval")

        if not run_forever:
            break
        logger.info("Sleeping %.1f hours until next run", interval_hours)
        await asyncio.sleep(interval_hours * 3600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("GROUNDZERO_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--admin-api-key", default=os.environ.get("ADMIN_API_KEY", ""))
    parser.add_argument("--interval-hours", type=float, default=24.0)
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit (e.g. from cron/Task Scheduler)")
    args = parser.parse_args()

    if not args.admin_api_key:
        logger.error(
            "No admin API key provided. Pass --admin-api-key or set ADMIN_API_KEY "
            "(same value as ADMIN_API_KEY in .env)."
        )
        sys.exit(1)

    asyncio.run(main_loop(args.base_url, args.admin_api_key, args.interval_hours, run_forever=not args.once))


if __name__ == "__main__":
    main()
