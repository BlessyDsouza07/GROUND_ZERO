"""
Closes the loop from the itinerary feedback feature back into the
dataset: reads every accumulated PlaceFeedbackSignal (thumbs up/down,
removals, manual adds — see layer2/domain/feedback_entities.py, filled in
by ItineraryFeedbackService.confirm), applies the bounded nudge formula in
BiasSignalEstimator.refine_with_community_feedback to that place's stored
bias signals, recomputes bias_index/grade via BiasAuditService, and
upserts the updated Place back. This is the concrete mechanism behind
"tourist feedback enriches the dataset" — a periodic maintenance pass over
EXISTING places, not something that runs during ingestion of new ones
(which have no feedback yet by definition), so it belongs alongside
run_periodic_pipeline.py as its own scheduled job rather than inside the
live request-time ETL.

Usage:

    python scripts/apply_community_feedback.py            # run once
    python scripts/apply_community_feedback.py --dry-run  # show what would change, write nothing

Recommended cadence: daily, same as run_periodic_pipeline.py — feedback
accumulates slowly (one signal per confirmed trip), so there's no benefit
to running this more often than that.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from layer0.application.bias_audit import BiasAuditService
from layer0.application.bias_signal_estimator import BiasSignalEstimator
from layer0.infrastructure.db.repository_impl import PostgresPlaceRepository
from layer0.infrastructure.db.session import get_session
from layer2.infrastructure.db.repository_impl import PostgresItineraryFeedbackRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("groundzero.scripts.apply_community_feedback")


async def run(dry_run: bool = False) -> None:
    estimator = BiasSignalEstimator()
    auditor = BiasAuditService()

    async with get_session() as session:
        place_repo = PostgresPlaceRepository(session)
        feedback_repo = PostgresItineraryFeedbackRepository(session)

        signals = await feedback_repo.list_all_signals()
        logger.info("Found %d place(s) with accumulated feedback signals", len(signals))

        updated, skipped_no_place, skipped_no_change = 0, 0, 0
        for signal in signals:
            place = await place_repo.get_by_id(signal.place_id)
            if place is None:
                skipped_no_place += 1
                continue

            before_bias_index = place.bias_index
            estimator.refine_with_community_feedback(
                place.bias_signals,
                thumbs_up=signal.thumbs_up,
                thumbs_down=signal.thumbs_down,
                times_removed=signal.times_removed,
                times_manually_added=signal.times_manually_added,
            )
            breakdown = auditor.compute(place.bias_signals)
            place.bias_index = breakdown.bias_index
            place.grade = auditor.grade_for(breakdown.bias_index)

            if place.bias_index == before_bias_index:
                skipped_no_change += 1
                continue

            logger.info(
                "%s: bias_index %s -> %s (up=%d down=%d removed=%d added=%d)",
                place.name, before_bias_index, place.bias_index,
                signal.thumbs_up, signal.thumbs_down, signal.times_removed, signal.times_manually_added,
            )
            if not dry_run:
                await place_repo.upsert(place)
            updated += 1

        logger.info(
            "Done. updated=%d skipped_no_change=%d skipped_place_not_found=%d dry_run=%s",
            updated, skipped_no_change, skipped_no_place, dry_run,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Compute and log changes without writing them")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
