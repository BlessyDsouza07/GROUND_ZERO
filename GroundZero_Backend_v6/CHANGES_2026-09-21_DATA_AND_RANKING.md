# 2026-09-21 — new places ingest + Ranking v2

## Data
- `scripts/ingest_new_places.py` (+ `layer0/application/place_ingest.py`, `shared/place_taxonomy.py`): cleans
  the queue, dedups against community + master data, resolves coordinates ONLY from a hand pin, a confirmed OSM
  feature, a researched OSM alias (`osm_ref`), or (with `--online`) a validated Nominatim hit. Never guesses.
- community_places.csv 64 -> 78 rows. 43 localities -> `data/mangaluru_localities.csv` (reference only).
- Queue now 322 rows with `priority` (A = recommendable stop), Google Maps link, and `pin_lat`/`pin_lon`
  columns: paste a pin, re-run the script.
- ETL now maps curator category words (temple/mosque/church/hotel...) to the shared vocabulary; the original
  word is kept as a tag.
- Known drift found: seed rows flagged "(approx — verify)" are ~1.1-1.2 km off OSM (Tannirbhavi Beach,
  Pilikula Nisargadhama). Not changed — decide whether to repair.

## Ranking v2 (`layer2/application/ranking.py`, on in production DI, off by default in HiveEngine)
Benchmark (`scripts/benchmark_recommendations.py`, 24 profiles, real master data):
route length 29.3 -> 9.2 km; meal-anchor distance from 13:15 2.36 -> 0.25 h; categories/day 4.1 -> 4.8;
purpose match 56.9% -> 55.3% (small cost of favouring nearby places); non-attraction stops 0% -> 0% (gate is a safety net).

## Duplicate cleanup (later on 2026-09-21)
- `scripts/audit_dataset_duplicates.py` (read-only) and `scripts/clean_dataset_duplicates.py` (backs up, then fixes).
- Root cause: hand-seeded rows with approximate coordinates (0.5-3 km off) could never merge with their OSM twins
  (ETL needs <= 75 m). 8 places existed twice: Rosario Cathedral, Panambur Beach, Tannirbhavi Beach, Milagres Church,
  St Aloysius Chapel, Tagore Park, Diesel Cafe, Sultan Battery. Merged into the OSM record; community CSV coordinates aligned.
- 5 rows sharing an identical pin with a different place (centroid signature) removed and re-queued.
- master 722 -> 708 records; community 78 -> 73 rows; queue 322 -> 327; 7 stray-quote names cleaned; 4 blank categories filled.
- `data/duplicate_cleanup_ids.txt` = 14 ids to delete from Postgres via `scripts/delete_duplicate_places.py`
  (the importer only upserts, so it never removes rows).
- Seed records also carry shifted columns (opening_hours.raw holds a URL, a time inside tags, season_suitability ['false']);
  not fixed here, so only description + clean tags were carried over in merges.
