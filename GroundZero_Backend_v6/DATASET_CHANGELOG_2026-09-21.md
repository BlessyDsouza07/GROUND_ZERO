# community_places.csv — Cleanup & Merge, 2026-09-21

Source files checked: `Mangaluru_327_Research_Ready_Final.csv`, `Mangaluru_327_Strong_Pass_Clean.csv`
(uploaded twice, byte-identical — treated as one file).

Of 327 candidate rows, only **15** had `production_status = READY`
(`coordinate_ready_for_use = True`, independently verified). The other 303
are `NOT_YET_INDEPENDENTLY_VERIFIED` and were **not** touched — adding them
would have meant guessing at unverified coordinates, which contradicts your
own audit's own verdict on them. 9 rows were explicitly `REMOVE` in your
sheet (not applicable to Mangaluru dataset) — also skipped.

**Net result: 73 → 80 places. 3 removed, 5 coordinate corrections, 10 added.**

## Removed (duplicates found inside the existing 73)

| Removed | Kept instead | Why |
|---|---|---|
| Our Lady of Rosary Cathedral | Rosario Cathedral | 35m apart, same cathedral — the removed row's own OSM alias note said so |
| Mangalore Junction Railway Station Bus Stop | Mangalore Junction Railway Station | identical coordinates, templated duplicate record |
| Kadri Shri Yogeshwara Matha - Jogi Sampradaya | Kadri Shri Yogeshwara Matha | 382m apart, same matha name, thin templated entry vs. real OSM match |

## Coordinate corrections (same place, better source)

| Place | Old | New | Source |
|---|---|---|---|
| Mangaluru International Airport | 12.9548909, 74.8855223 | 12.9620611111, 74.8897833333 | AAI government dataset |
| Mangalore Central Railway Station | 12.8698101, 74.8430082 | 12.8634, 74.84324 | OSM + Wikidata crosscheck |
| Mangalore Junction Railway Station | 12.872159, 74.8867594 | 12.86663, 74.87923 | OSM + Wikidata crosscheck |
| Bejai Museum | 12.8815, 74.85 (approx) | 12.887, 74.846491 | Published museum reference |
| Surathkal Lighthouse | 13.0047774, 74.7897559 | 13.00478, 74.78976 | Govt gazette + OSM (1m diff, negligible) |

## Added (10 new verified places)

Bengre Beach · NITK Beach · Swami Vivekananda Planetarium · Pilikula
Zoological Garden · Zeenath Baksh Juma Masjid · Pandeshwar Fire Station ·
KMC Hospital, Attavar · Lady Goschen Hospital · Mangalore University ·
St Aloysius University

5 candidates from the READY list were **not** added as new rows because
they duplicate places already in the dataset (coordinates updated instead,
see table above): Surathkal Lighthouse Beach, Mangalore Airport, Mangalore
Central, Mangalore Junction, Srimanthi Bai Memorial Government Museum
(= Bejai Museum).

Fields left blank on the new rows (`estimated_cost`, `parking`, `washrooms`,
etc.) are ones your source data itself marked `verify` / `to_be_verified` —
left blank rather than guessed, same discipline the rest of the dataset
already follows (`local_percentage_hint` / `media_mentions_hint` are blank
on all 10 too; the bias estimator's category-level priors apply automatically,
same as every other unhinted row).

One thing to sanity-check yourself: **St Aloysius University**'s verified
coordinate (12.9141, 74.8560) is identical to the generic Mangaluru
city-centre point used elsewhere in the codebase. That's plausible — Kodialbail
is genuinely central — but it's flagged in the row's `address` field as
city-block precision, not a building pin.

## What was NOT removed (checked, found legitimate)

- No places outside the Mangaluru area — the farthest entries (Saavira
  Kambada Basadi 22.7km, Polali Temple 21.1km, Sasihithlu/NITK/Someshwara
  beaches 13-14km) are all real, commonly-included Mangaluru-region day-trip
  spots, not data errors.
- No "closed" places found — neither your source CSVs nor the existing
  dataset flag any place as closed/demolished; `temporarily_unavailable`
  stays a live runtime signal (Layer 0), not something to hardcode here.
- 20+ other near-name/near-coordinate pairs were checked (e.g. multiple
  bookshops, temples, hospitals close together downtown) and are genuinely
  distinct places, not duplicates — dense central Mangaluru just has a lot
  of things near each other.

## Verification

- Full merged file re-run through the actual project loader
  (`SpreadsheetListingSource.fetch()`): **80/80 rows parse with zero errors**,
  including all 3 removals confirmed gone and all 10 additions confirmed present.
- `pytest layer0/tests/test_spreadsheet_source.py`: 5/5 passed.
