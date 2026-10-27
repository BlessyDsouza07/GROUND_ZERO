# GroundZero backend v6 – HIVE 2 + privacy

1. `pip install -r requirements.txt`
2. Keep Docker Postgres running, then `alembic upgrade head` (adds 5 tables, revision d7e8f9a0b1c2)
3. `python import_master_data.py` (if not already), then `uvicorn main:app --port 8000`

New endpoints: `POST /hive/plan`, `/hive/feedback`, `/hive/location`, `GET|PUT|DELETE /hive/profile`, `GET /hive/events`; `GET|PUT /privacy/consents`, `GET /privacy/export`, `POST /privacy/report`, `GET /legal/{privacy|terms|safety}`, `GET /safety`.
Register now requires `accepted_terms` and `adult_confirmed`.
Tests: `pytest hive2 auth explore guide layer2` (layer0 DB tests need Postgres). Evaluation: `python scripts/evaluate_hive2.py`.

Honest limits: ranking is rule-based, not a trained model. 'Typical' opening hours are estimates. Legal files in `legal/` are drafts, not legal advice; fill the [brackets] and have a lawyer review them before public launch.
