"""
Layer 5 — On-the-ground companion features (blueprint Section 7):
chatbot, geofencing/narration, voice guide, multilingual support.

Until this fix, this package had zero `__init__.py` files, was never
imported by `main.py`, had no API routes, no tests, and every class's
data hooks (`place_repository`, `hive_engine`) were `None` stubs wired to
nothing — meaning none of this code ever ran against the real app. See
`layer5/api/routes.py` for the real, wired-up entry points.
"""
