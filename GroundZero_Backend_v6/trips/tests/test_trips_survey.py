"""Covers the two things that are genuinely new/risky in trips/service.py:

1. The slider -> enum threshold mapping (energy_slider_to_band,
   crowd_slider_to_tolerance) — pure functions, easy to get wrong at the
   boundaries.
2. The auto-fill logic that turns layer1's real 13-step survey machine
   into exactly Carol's 9 questions (see service.py's module docstring).
   This runs the REAL SurveyService + InMemorySurveySessionStore — only
   the profile repository is faked (in-memory dict), so this test needs
   no database and no network, and still exercises the real question-
   skipping logic instead of re-describing it.

Itinerary generation / live-trip endpoints are NOT covered here — those
need a real Postgres-backed place catalog (for HiveEngine) and are
exercised manually against a running stack instead; see
trips/README_TRIPS.md.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.application.profile_extractor import ProfileExtractor
from layer1.application.survey_service import SurveyService
from layer1.domain.entities import GroupConfig, Purpose, TouristProfile, VoicePersonality
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.survey_session_store import InMemorySurveySessionStore

from trips.service import TripsService, crowd_slider_to_tolerance, energy_slider_to_band


def test_energy_slider_thresholds():
    assert energy_slider_to_band(0) == "low"
    assert energy_slider_to_band(33) == "low"
    assert energy_slider_to_band(34) == "moderate"
    assert energy_slider_to_band(66) == "moderate"
    assert energy_slider_to_band(67) == "high"
    assert energy_slider_to_band(100) == "high"


def test_crowd_slider_thresholds():
    assert crowd_slider_to_tolerance(0) == "avoid_entirely"
    assert crowd_slider_to_tolerance(25) == "avoid_entirely"
    assert crowd_slider_to_tolerance(26) == "prefer_quiet"
    assert crowd_slider_to_tolerance(50) == "prefer_quiet"
    assert crowd_slider_to_tolerance(51) == "fine"
    assert crowd_slider_to_tolerance(75) == "fine"
    assert crowd_slider_to_tolerance(76) == "love_them"
    assert crowd_slider_to_tolerance(100) == "love_them"


class _FakeProfileRepo(TouristProfileRepository):
    def __init__(self):
        self.saved: dict[str, TouristProfile] = {}

    async def save(self, profile: TouristProfile) -> TouristProfile:
        self.saved[profile.id] = profile
        return profile

    async def get_by_id(self, profile_id: str) -> Optional[TouristProfile]:
        return self.saved.get(profile_id)

    async def get_prior_session_for_device(self, device_id: str) -> Optional[TouristProfile]:
        return None

    async def get_visited_place_ids(self, profile_id: str) -> list[str]:
        return []

    async def mark_visited(self, profile_id: str, place_ids: list[str]) -> list[str]:
        return place_ids

    async def list_by_group_session(self, group_session_id: str) -> list[TouristProfile]:
        return []


class _FakeDb:
    """log_event only ever needs .add() + an awaitable .flush() — no real
    session required for this test, which never reads TripEvent back."""

    def add(self, obj):
        pass

    async def flush(self):
        return None


def _make_trips_service() -> TripsService:
    profile_repo = _FakeProfileRepo()
    survey_service = SurveyService(
        profile_repository=profile_repo,
        curiosity_extractor=CuriosityExtractor(),
        session_store=InMemorySurveySessionStore(),
        profile_extractor=ProfileExtractor(),
    )
    return TripsService(
        db=_FakeDb(), survey_service=survey_service, profile_repository=profile_repo,
        hive_engine=None, place_repository=None, custom_place_service=None,
    )


@pytest.mark.asyncio
async def test_survey_asks_exactly_carols_nine_questions():
    # SECURITY FIX (final-release-hardening pass, Oct 2026): start_survey/
    # answer_survey now require the caller's user_id, since sessions are
    # bound to their creator (see SurveySessionNotOwned). One fixed test
    # user_id throughout, matching what a real signed-in caller would do.
    import uuid as _uuid
    test_user_id = _uuid.uuid4()

    svc = _make_trips_service()
    session_id, first_step = await svc.start_survey(test_user_id)
    assert first_step == "opening_prompt"

    expected_order = [
        "opening_prompt", "q2_energy", "q3_crowd_tolerance", "q4_budget",
        "q5_dietary", "accessibility", "q8_trip_duration", "q9_start_time",
        "return_visitor_check",
    ]

    answers = {
        # Deliberately generic — avoids tripping ProfileExtractor's lexicon
        # inference for purpose/energy/crowd/group, which would otherwise
        # remove that question from the sequence below (correct behavior,
        # just not what this test is checking).
        "opening_prompt": "I want to explore Mangaluru and see what's around.",
        "q2_energy": 40,  # slider -> moderate
        "q3_crowd_tolerance": 20,  # slider -> avoid_entirely
        "q4_budget": 1500,
        "q5_dietary": ["no_restrictions"],
        "accessibility": [],
        "q8_trip_duration": "full_day",
        "return_visitor_check": False,
        "q9_start_time": "morning",
    }

    seen_order = [expected_order[0]]
    step = first_step
    for expected_step in expected_order:
        assert step == expected_step
        value = answers[step]
        # the router does the slider->enum conversion before calling the
        # service — mirror that here for the two slider questions.
        if step == "q2_energy":
            from trips.service import energy_slider_to_band
            value = energy_slider_to_band(value)
        elif step == "q3_crowd_tolerance":
            from trips.service import crowd_slider_to_tolerance
            value = crowd_slider_to_tolerance(value)
        next_step, progress, done = await svc.answer_survey(session_id, step, value, test_user_id)
        if not done:
            seen_order.append(next_step)
            step = next_step

    assert done
    assert seen_order == expected_order

    profile = await svc.finalize_survey(session_id, user_id=test_user_id)
    # None of these were asked directly — confirm the silent defaults landed.
    assert profile.group_config == GroupConfig.SOLO
    assert profile.voice_personality == VoicePersonality.WARM_LOCAL_FRIEND
    assert profile.budget == 1500
    assert profile.energy_band.value == "moderate"
    assert profile.crowd_tolerance.value == "avoid_entirely"
