"""Chunk 3 — Explore.

A thin integration layer, same philosophy as `trips/`: almost everything
this module needs already exists in Layer 0-2 (place data + tags, weather
collector, tide collector, Personal Fit Score) plus the standalone
`live_events` service. This module composes those into the "mood-first,
context-aware discovery" shapes Carol's Explore spec asks for, and adds
the one thing that didn't already exist: an auth-optional read path (every
endpoint here works for a signed-out tourist; only `POST
/explore/add-to-journey` requires a signed-in user, same bearer-token
pattern as `trips/`).

See README_EXPLORE.md for what's real vs. honestly deferred.
"""
