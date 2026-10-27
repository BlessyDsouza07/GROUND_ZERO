# Ground Zero — Live Mangaluru Events (LIVE-ONLY)

This build contains **NO seed event records**. The database starts empty and is populated only by runtime collection from configured public sources.

## What it does
- Fetches configured public event sources at runtime.
- Parses Schema.org `Event` JSON-LD where available.
- Follows same-host event/detail links conservatively.
- Normalizes and deduplicates events.
- Stores source URL, first seen, last verified, status and update history.
- Never invents missing event details.
- Does not mark an event cancelled merely because it disappears from a later crawl.
- Automatically refreshes on a schedule.
- Exposes API endpoints for current/upcoming/date-filtered events and source health.
- Supports SQLite for development and PostgreSQL for deployment.
- Protects manual refresh with an API key.

## Important truth about "complete live data"
No public system can honestly guarantee every event in Mangaluru. This project is designed as a **multi-source live event intelligence system**: it can only know events exposed by configured sources and reachable under their access rules. Add more verified public sources to `data/sources.json` as they are approved.

The current registry contains a confirmed public St Aloysius event directory. The source currently exposes 11 listings; some are already past relative to the current date, so the application filters itinerary candidates by date/status rather than treating every listing as upcoming.

Source-specific terms, robots.txt rules, rate limits and applicable law still apply. This project does not bypass login, CAPTCHA, paywalls, access controls or robots.txt restrictions.

## Run
1. Create a virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Run `python -m app.main`.
5. The first startup performs a live refresh; no seed loader runs.
6. The scheduler repeats refreshes every `REFRESH_INTERVAL_MINUTES`.

API:
- `GET /health`
- `GET /events`
- `GET /events/today`
- `GET /events/date/{YYYY-MM-DD}`
- `GET /events/upcoming`
- `GET /events/{id}`
- `GET /sources`
- `GET /sources/health`
- `POST /admin/refresh` with `X-Admin-Key`

For a production deployment, use PostgreSQL and a reverse proxy/TLS.
