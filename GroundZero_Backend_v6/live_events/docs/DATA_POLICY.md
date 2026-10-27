# Live Data Policy

1. Event records are created only from configured source fetches.
2. No event record is shipped as seed/demo data.
3. Missing fields remain null/unknown; they are never guessed.
4. A source disappearing does not automatically prove cancellation.
5. Explicit structured cancellation/postponement may change status.
6. Events are refreshed periodically and retain `last_verified_at`.
7. Stale events are labelled `STALE` by the API freshness check.
8. Only physical/hybrid general-public events are automatically marked itinerary eligible by the baseline classifier. This is conservative and source-specific adapters can refine it.
9. Online/FDP/student-only/academic-only events may remain stored for search/history but are not automatically itinerary candidates.
10. Collection obeys configured robots rules, same-host restrictions and request timeouts.
11. Add a source only after confirming it is public, permitted to collect, and technically parseable.
