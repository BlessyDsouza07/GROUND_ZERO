# Architecture

Public sources -> source adapters -> robots/access checks -> live fetch -> Schema.org Event parsing -> normalization -> deduplication -> PostgreSQL/SQLite -> freshness/status -> FastAPI -> itinerary integration.

The system intentionally fails closed when a configured source cannot be safely collected. It does not manufacture fallback events.
