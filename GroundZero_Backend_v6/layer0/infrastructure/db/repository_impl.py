"""
Postgres implementation of the Layer 0 repository ports. This is the only
file in Layer 0 that imports both the domain entities AND SQLAlchemy — the
mapping boundary the Repository Pattern exists to create.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID, ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from layer0.domain.entities import (
    AccessibilityInfo,
    BiasSignals,
    CommunitySubmission,
    Coordinates,
    CrowdLevel,
    DataSource,
    EnergyRequirement,
    Grade,
    OpeningHours,
    Place,
    PriceBand,
)
from layer0.domain.repositories import CommunitySubmissionRepository, PlaceRepository
from layer0.infrastructure.db.models import (
    BiasSignalsModel,
    CommunitySubmissionModel,
    PlaceModel,
    SubmissionStatusEnum,
)

logger = logging.getLogger("groundzero.layer0.repository")


def _place_to_model(place: Place, existing: PlaceModel | None = None) -> PlaceModel:
    model = existing or PlaceModel(id=uuid.UUID(place.id) if place.id else uuid.uuid4())
    model.name = place.name
    model.category = place.category
    model.location = ST_SetSRID(ST_MakePoint(place.coordinates.longitude, place.coordinates.latitude), 4326)
    model.opening_hours_raw = place.opening_hours.raw
    model.days_open = place.opening_hours.days_open
    model.opens_at = place.opening_hours.opens_at
    model.closes_at = place.opening_hours.closes_at
    model.price_band = place.price_band.value
    model.estimated_cost = place.estimated_cost
    model.tags = place.tags
    model.bias_index = place.bias_index
    model.grade = place.grade.value if place.grade else None
    model.energy_requirement = place.energy_requirement.value
    model.crowd_level = place.crowd_level.value
    model.season_suitability = place.season_suitability
    model.tide_dependency = place.tide_dependency
    model.dwell_time_typical_minutes = place.dwell_time_typical_minutes
    model.accessibility_tags = place.accessibility.tags
    model.wheelchair = place.accessibility.wheelchair
    model.stairs = place.accessibility.stairs
    model.sensory_notes = place.accessibility.sensory_notes
    model.parking = place.parking
    model.washrooms = place.washrooms
    model.food_available = place.food_available
    model.pet_friendly = place.pet_friendly
    model.family_friendly = place.family_friendly
    model.kid_friendly = place.kid_friendly
    model.photography_allowed = place.photography_allowed
    model.best_time = place.best_time
    model.freshness_score = place.freshness_score
    model.last_verified_at = place.last_verified_at
    model.temporarily_unavailable = place.temporarily_unavailable
    model.etiquette_tag = place.etiquette_tag
    model.source = [s.value for s in place.source]
    model.description = place.description
    model.wiki_summary = place.wiki_summary
    model.transport_access = place.transport_access
    model.verification_status = place.verification_status

    if not existing:
        model.bias_signals = BiasSignalsModel(
            media_mentions=place.bias_signals.media_mentions,
            local_percentage=place.bias_signals.local_percentage,
            commercial_flags=place.bias_signals.commercial_flags,
            tourist_popularity=place.bias_signals.tourist_popularity,
            sponsored_indicator=place.bias_signals.sponsored_indicator,
        )
    else:
        bs = model.bias_signals
        bs.media_mentions = place.bias_signals.media_mentions
        bs.local_percentage = place.bias_signals.local_percentage
        bs.commercial_flags = place.bias_signals.commercial_flags
        bs.tourist_popularity = place.bias_signals.tourist_popularity
        bs.sponsored_indicator = place.bias_signals.sponsored_indicator

    return model


def _model_to_place(model: PlaceModel, lat: float, lon: float) -> Place:
    return Place(
        id=str(model.id),
        name=model.name,
        category=model.category,
        coordinates=Coordinates(latitude=lat, longitude=lon),
        opening_hours=OpeningHours(
            raw=model.opening_hours_raw or "",
            days_open=model.days_open or [],
            opens_at=model.opens_at,
            closes_at=model.closes_at,
        ),
        price_band=PriceBand(model.price_band),
        estimated_cost=model.estimated_cost,
        tags=model.tags or [],
        bias_signals=BiasSignals(
            media_mentions=model.bias_signals.media_mentions if model.bias_signals else 0,
            local_percentage=model.bias_signals.local_percentage if model.bias_signals else 0.0,
            commercial_flags=model.bias_signals.commercial_flags if model.bias_signals else 0,
            tourist_popularity=model.bias_signals.tourist_popularity if model.bias_signals else 0.0,
            sponsored_indicator=model.bias_signals.sponsored_indicator if model.bias_signals else False,
        ),
        bias_index=model.bias_index,
        grade=Grade(model.grade) if model.grade else None,
        energy_requirement=EnergyRequirement(model.energy_requirement),
        crowd_level=CrowdLevel(model.crowd_level),
        season_suitability=model.season_suitability or [],
        tide_dependency=model.tide_dependency,
        dwell_time_typical_minutes=model.dwell_time_typical_minutes,
        accessibility=AccessibilityInfo(
            tags=model.accessibility_tags or [],
            wheelchair=model.wheelchair,
            stairs=model.stairs,
            sensory_notes=model.sensory_notes,
        ),
        parking=model.parking,
        washrooms=model.washrooms,
        food_available=model.food_available,
        pet_friendly=model.pet_friendly,
        family_friendly=model.family_friendly,
        kid_friendly=model.kid_friendly,
        photography_allowed=model.photography_allowed,
        best_time=model.best_time,
        freshness_score=model.freshness_score,
        last_verified_at=model.last_verified_at,
        temporarily_unavailable=model.temporarily_unavailable,
        etiquette_tag=model.etiquette_tag,
        source=[DataSource(s) for s in (model.source or [])],
        description=model.description,
        wiki_summary=model.wiki_summary,
        transport_access=model.transport_access,
        verification_status=model.verification_status or "verified",
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class PostgresPlaceRepository(PlaceRepository):
    # Default chunk size for bulk_upsert. An unchunked ETL run storing
    # thousands of places in a single flush/commit risks large parameter
    # counts per statement and, more importantly, means a failure late in
    # the run rolls back every place enriched so far — nothing from that
    # run is resumable. Chunking commits progress incrementally: if chunk
    # 8 of 12 fails, chunks 1-7 are already durably stored. 500 is a
    # reasonable default for city-scale imports; callers ingesting a much
    # larger area can lower it via the constructor without touching the
    # ETL orchestrator or the abstract PlaceRepository interface at all.
    DEFAULT_BATCH_SIZE = 500

    def __init__(self, session: AsyncSession, batch_size: int = DEFAULT_BATCH_SIZE):
        self.session = session
        self.batch_size = batch_size

    async def _lat_lon(self, model: PlaceModel) -> tuple[float, float]:
        # Querying model.location directly (rather than by id) triggers an
        # implicit lazy-load of the ORM attribute, which is synchronous and
        # breaks inside an async session (MissingGreenlet) — confirmed by
        # running this against a live PostGIS instance. Query by id instead.
        stmt = select(
            ST_Y(PlaceModel.location.cast(models_geometry_type())),
            ST_X(PlaceModel.location.cast(models_geometry_type())),
        ).where(PlaceModel.id == model.id)
        result = await self.session.execute(stmt)
        lat, lon = result.one()
        return lat, lon

    async def get_by_id(self, place_id: str) -> Optional[Place]:
        model = await self.session.get(PlaceModel, uuid.UUID(place_id), options=[selectinload(PlaceModel.bias_signals)])
        if model is None:
            return None
        lat, lon = await self._lat_lon(model)
        return _model_to_place(model, lat, lon)

    async def find_duplicates(self, place: Place, radius_meters: float = 75.0) -> list[Place]:
        point = ST_SetSRID(ST_MakePoint(place.coordinates.longitude, place.coordinates.latitude), 4326)
        stmt = select(PlaceModel).options(selectinload(PlaceModel.bias_signals)).where(
            ST_DWithin(PlaceModel.location, point, radius_meters),
            PlaceModel.category == place.category,
        )
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()
        places = []
        for model in candidates:
            lat, lon = await self._lat_lon(model)
            places.append(_model_to_place(model, lat, lon))
        return places

    async def upsert(self, place: Place) -> Place:
        existing = await self.session.get(PlaceModel, uuid.UUID(place.id), options=[selectinload(PlaceModel.bias_signals)]) if place.id else None
        model = _place_to_model(place, existing=existing)
        if not existing:
            self.session.add(model)
        await self.session.flush()
        lat, lon = await self._lat_lon(model)
        await self.session.commit()
        return _model_to_place(model, lat, lon)

    async def bulk_upsert(self, places: list[Place]) -> list[Place]:
        """Real batch insert, chunked into self.batch_size-sized groups,
        each with its own flush/commit — instead of either the
        N-round-trips-and-N-commits pattern `upsert()` uses in a loop, or
        one giant unchunked transaction for the entire run.

        Chunking exists for two confirmed reasons: an architectural audit
        found the fully-sequential per-place commit pattern was a real
        ETL bottleneck at hundreds/thousands of places, but a single
        unchunked flush for the *whole* run means a failure near the end
        rolls back everything enriched so far, so nothing from that run
        is durable. Committing per chunk bounds both the per-statement
        parameter count and the amount of work lost to a failure — if
        chunk 8 of 12 fails, chunks 1-7 are already stored.

        Individual place failures within a chunk (e.g. a unique-constraint
        violation from a near-duplicate that slipped past application-level
        dedup) are caught per-place so one bad row doesn't roll back the
        rest of that chunk; callers get back only the places that actually
        saved."""
        if not places:
            return []

        stored: list[Place] = []
        for start in range(0, len(places), self.batch_size):
            chunk = places[start : start + self.batch_size]
            stored.extend(await self._upsert_chunk(chunk))
        return stored

    async def _upsert_chunk(self, places: list[Place]) -> list[Place]:
        models: list[PlaceModel] = []
        for place in places:
            existing = (
                await self.session.get(PlaceModel, uuid.UUID(place.id), options=[selectinload(PlaceModel.bias_signals)])
                if place.id else None
            )
            model = _place_to_model(place, existing=existing)
            if not existing:
                self.session.add(model)
            models.append(model)

        try:
            await self.session.flush()
        except Exception:
            await self.session.rollback()
            # Fall back to one-at-a-time so a single bad row in this chunk
            # doesn't lose the rest of an otherwise-valid chunk.
            results = []
            for place in places:
                try:
                    results.append(await self.upsert(place))
                except Exception:  # noqa: BLE001 — genuinely skip just this one row
                    logger.warning("bulk_upsert: skipping place %r after individual retry also failed", place.name)
            return results

        stored: list[Place] = []
        for model in models:
            lat, lon = await self._lat_lon(model)
            stored.append(_model_to_place(model, lat, lon))
        await self.session.commit()
        return stored

    
    async def list_all(self, category: Optional[str] = None) -> list[Place]:
        stmt = select(PlaceModel).options(
            selectinload(PlaceModel.bias_signals)
        )

        if category:
            stmt = stmt.where(PlaceModel.category == category)

        try:
            result = await self.session.execute(stmt)
            models = result.scalars().all()

            places = []
            for model in models:
                lat, lon = await self._lat_lon(model)
                places.append(_model_to_place(model, lat, lon))

            logger.info(
                "list_all succeeded: category=%r, count=%d",
                category,
                len(places),
            )
            return places

        except Exception:
            logger.exception(
                "list_all failed: category=%r",
                category,
            )
            raise


    async def list_stale(self, older_than_days: int) -> list[Place]:
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        stmt = select(PlaceModel).options(selectinload(PlaceModel.bias_signals)).where(
            (PlaceModel.last_verified_at == None) | (PlaceModel.last_verified_at < cutoff_dt)  # noqa: E711
        )
        result = await self.session.execute(stmt)
        places = []
        for model in result.scalars().all():
            lat, lon = await self._lat_lon(model)
            places.append(_model_to_place(model, lat, lon))
        return places

    async def delete(self, place_id: str) -> None:
        model = await self.session.get(PlaceModel, uuid.UUID(place_id), options=[selectinload(PlaceModel.bias_signals)])
        if model:
            await self.session.delete(model)
            await self.session.commit()

    async def record_visit(self, place_id: str) -> None:
        """Record that a user has visited this place.
        
        Phase 1 implementation (Aug 4 2026): Provides the write path for the
        Return Visitor Check workflow. In Phase 2, this will be integrated with
        TouristProfile.visited_log and proper device tracking.
        
        For now, simply verifies the place exists. The actual visit recording
        will be handled by Layer 1's TouristProfileRepository once user sessions
        are properly tracked.
        
        Args:
            place_id: UUID of the place being marked visited
            
        Raises:
            ValueError: If place_id does not exist
        """
        # Verify the place exists
        place_model = await self.session.get(PlaceModel, uuid.UUID(place_id))
        if not place_model:
            raise ValueError(f"Place {place_id} not found")
        
        # Placeholder: In Phase 2, this will record the visit in TouristProfile.visited_log
        # For now, we confirm the place exists and return success.
        # This allows the API endpoint to work while Layer 1 integration is developed.


def models_geometry_type():
    """GeoAlchemy2's Geography column needs an explicit cast for ST_X/ST_Y
    in some dialects; isolated here so it's easy to adjust per-Postgres-version."""
    from geoalchemy2 import Geometry
    return Geometry("POINT", srid=4326)


class PostgresCommunitySubmissionRepository(CommunitySubmissionRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _submission_to_dict(self, place: Place) -> dict:
        from dataclasses import asdict
        data = asdict(place)
        # Enums don't round-trip through asdict as plain values in a way
        # we want to rely on implicitly; normalize explicitly rather than
        # risk a silent reconstruction bug later.
        data["price_band"] = place.price_band.value
        data["energy_requirement"] = place.energy_requirement.value
        data["crowd_level"] = place.crowd_level.value
        data["grade"] = place.grade.value if place.grade else None
        data["source"] = [s.value for s in place.source]
        for dt_field in ("last_verified_at", "created_at", "updated_at"):
            if data.get(dt_field):
                data[dt_field] = data[dt_field].isoformat()
        return data

    def _dict_to_place(self, data: dict, place_id: str | None) -> Place:
        """Inverse of _submission_to_dict. Deliberately NOT `Place(**data)`,
        since asdict() flattens nested dataclasses (Coordinates,
        OpeningHours, BiasSignals, AccessibilityInfo) into plain dicts that
        Place's constructor can't accept directly — explicit reconstruction
        avoids that silent mismatch."""
        from datetime import datetime as _dt

        def parse_dt(value):
            return _dt.fromisoformat(value) if value else None

        coords = data["coordinates"]
        oh = data["opening_hours"]
        bs = data["bias_signals"]
        acc = data["accessibility"]

        return Place(
            id=place_id,
            name=data["name"],
            category=data["category"],
            coordinates=Coordinates(latitude=coords["latitude"], longitude=coords["longitude"]),
            opening_hours=OpeningHours(
                raw=oh["raw"], days_open=oh["days_open"], opens_at=oh["opens_at"], closes_at=oh["closes_at"]
            ),
            price_band=PriceBand(data["price_band"]),
            estimated_cost=data["estimated_cost"],
            tags=data.get("tags", []),
            bias_signals=BiasSignals(
                media_mentions=bs["media_mentions"],
                local_percentage=bs["local_percentage"],
                commercial_flags=bs["commercial_flags"],
                tourist_popularity=bs["tourist_popularity"],
                sponsored_indicator=bs["sponsored_indicator"],
            ),
            bias_index=data.get("bias_index"),
            grade=Grade(data["grade"]) if data.get("grade") else None,
            energy_requirement=EnergyRequirement(data["energy_requirement"]),
            crowd_level=CrowdLevel(data["crowd_level"]),
            season_suitability=data.get("season_suitability", []),
            tide_dependency=data.get("tide_dependency", False),
            dwell_time_typical_minutes=data.get("dwell_time_typical_minutes", 45),
            accessibility=AccessibilityInfo(
                tags=acc.get("tags", []), wheelchair=acc.get("wheelchair"),
                stairs=acc.get("stairs"), sensory_notes=acc.get("sensory_notes"),
            ),
            parking=data.get("parking"),
            washrooms=data.get("washrooms"),
            food_available=data.get("food_available"),
            pet_friendly=data.get("pet_friendly"),
            family_friendly=data.get("family_friendly"),
            kid_friendly=data.get("kid_friendly"),
            photography_allowed=data.get("photography_allowed"),
            best_time=data.get("best_time"),
            freshness_score=data.get("freshness_score", 0.0),
            last_verified_at=parse_dt(data.get("last_verified_at")),
            temporarily_unavailable=data.get("temporarily_unavailable", False),
            etiquette_tag=data.get("etiquette_tag"),
            source=[DataSource(s) for s in data.get("source", [])],
            description=data.get("description"),
            wiki_summary=data.get("wiki_summary"),
            transport_access=data.get("transport_access"),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
        )

    async def create(self, submission: CommunitySubmission) -> CommunitySubmission:
        model = CommunitySubmissionModel(
            submitted_place_json=self._submission_to_dict(submission.submitted_place),
            submitter_note=submission.submitter_note,
            status=SubmissionStatusEnum.pending,
            # SECURITY FIX (final-release-hardening pass, Oct 2026): see
            # layer0/domain/entities.py::CommunitySubmission.submitter_user_id.
            submitter_user_id=uuid.UUID(submission.submitter_user_id) if submission.submitter_user_id else None,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        submission.id = str(model.id)
        submission.submitted_at = model.submitted_at
        submission.submitter_user_id = str(model.submitter_user_id) if model.submitter_user_id else None
        return submission

    async def get_by_id(self, submission_id: str) -> Optional[CommunitySubmission]:
        model = await self.session.get(CommunitySubmissionModel, uuid.UUID(submission_id))
        if model is None:
            return None
        return self._model_to_domain(model)

    async def list_pending(self) -> list[CommunitySubmission]:
        stmt = select(CommunitySubmissionModel).where(
            CommunitySubmissionModel.status == SubmissionStatusEnum.pending
        )
        result = await self.session.execute(stmt)
        return [self._model_to_domain(m) for m in result.scalars().all()]

    async def update_status(
        self, submission_id: str, status: str, reviewed_by: str, resulting_place_id: str | None = None
    ) -> CommunitySubmission:
        model = await self.session.get(CommunitySubmissionModel, uuid.UUID(submission_id))
        if model is None:
            raise ValueError(f"Submission {submission_id} not found")
        model.status = SubmissionStatusEnum(status)
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(timezone.utc)
        if resulting_place_id is not None:
            model.resulting_place_id = uuid.UUID(resulting_place_id)
        await self.session.commit()
        await self.session.refresh(model)
        return self._model_to_domain(model)

    def _model_to_domain(self, model: CommunitySubmissionModel) -> CommunitySubmission:
        place_id = str(model.resulting_place_id) if model.resulting_place_id else None
        place = self._dict_to_place(model.submitted_place_json, place_id)
        return CommunitySubmission(
            id=str(model.id),
            submitted_place=place,
            submitter_note=model.submitter_note,
            status=model.status.value,
            submitted_at=model.submitted_at,
            reviewed_at=model.reviewed_at,
            reviewed_by=model.reviewed_by,
            submitter_user_id=str(model.submitter_user_id) if model.submitter_user_id else None,
        )
