"""
Soul Survey state machine (blueprint Section 4). Presents one question at
a time (4.x: "Feels like talking to a local guide... One question at a
time... Completion under 2 minutes"), tracks progress, and on completion
assembles the TouristProfile exactly as specified in 4.8.

The ordering below matches Table 3 (Q1-Q9) plus the post-Q9 additions in
4.3-4.7: accessibility flags (between Q6 and Q7 per 4.3), then after Q9:
return-visitor check (4.5), voice personality (4.6), and group session
setup if applicable (4.7).

Language question removed by request (Carol: keep companion_language to
English only, don't ask). CompanionLanguage.ENGLISH is set directly in
finalize() instead of being read from a survey answer — the enum/field
stays on TouristProfile unchanged (still used downstream by the
companion_voice templating and the Ask Engine's language instruction),
this only removes the SPOKEN QUESTION and hardcodes its answer. Re-adding
a language choice later is a one-line change: put COMPANION_LANGUAGE back
in _STEP_ORDER and read the answer in finalize() instead of hardcoding.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.application.profile_extractor import InferredProfile, ProfileExtractor
from layer1.domain.entities import (
    AccessibilityFlag,
    CompanionLanguage,
    CrowdTolerance,
    DietaryFlag,
    EnergyBand,
    GroupConfig,
    Purpose,
    StartTimePreference,
    TouristProfile,
    TripDuration,
    VoicePersonality,
)
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.survey_session_store import SurveySessionStore


class SurveyStep(str, Enum):
    OPENING_PROMPT = "opening_prompt"  # "Talk to Your Guide" — one free sentence, may pre-fill Q1/Q2/Q3/Q6/Q7
    Q1_PURPOSE = "q1_purpose"
    Q2_ENERGY = "q2_energy"
    Q3_CROWD_TOLERANCE = "q3_crowd_tolerance"
    Q4_BUDGET = "q4_budget"
    Q5_DIETARY = "q5_dietary"
    Q6_GROUP_CONFIG = "q6_group_config"
    ACCESSIBILITY = "accessibility"          # 4.3, sits between Q6 and Q7
    Q7_CURIOSITY_TEXT = "q7_curiosity_text"
    Q8_TRIP_DURATION = "q8_trip_duration"
    Q9_START_TIME = "q9_start_time"
    RETURN_VISITOR_CHECK = "return_visitor_check"  # 4.5
    VOICE_PERSONALITY = "voice_personality"    # 4.6
    GROUP_SESSION_SETUP = "group_session_setup"  # 4.7, only if group_config != solo
    COMPLETE = "complete"


_STEP_ORDER = [
    SurveyStep.OPENING_PROMPT,
    SurveyStep.Q1_PURPOSE,
    SurveyStep.Q2_ENERGY,
    SurveyStep.Q3_CROWD_TOLERANCE,
    SurveyStep.Q4_BUDGET,
    SurveyStep.Q5_DIETARY,
    SurveyStep.Q6_GROUP_CONFIG,
    SurveyStep.ACCESSIBILITY,
    SurveyStep.Q7_CURIOSITY_TEXT,
    SurveyStep.Q8_TRIP_DURATION,
    SurveyStep.Q9_START_TIME,
    SurveyStep.RETURN_VISITOR_CHECK,
    SurveyStep.VOICE_PERSONALITY,
    SurveyStep.GROUP_SESSION_SETUP,
    SurveyStep.COMPLETE,
]


class InvalidSurveyAnswer(Exception):
    pass


class SurveySessionNotOwned(Exception):
    """Raised when a session was created for one authenticated user and a
    different authenticated user tries to read/advance/finalize it.

    SECURITY FIX (final-release-hardening pass, Oct 2026): until now
    SurveySession carried no user_id at all. Both survey surfaces
    (/trips/survey/* and the legacy /survey/*) required being signed in,
    but never checked WHICH signed-in user a given session_id belonged
    to — an authenticated User B who obtained User A's session_id
    (logged, leaked, intercepted, or simply guessed given it's returned
    in every response body) could read or advance A's in-progress
    survey. That's the gap between "you must be logged in" and "this
    session belongs to you." See the README changelog for the live
    two-user verification."""


@dataclass
class SurveySession:
    id: str
    device_id: Optional[str]
    user_id: Optional[str] = None  # see SurveySessionNotOwned; None only for sessions created with no caller identity (layer1's own standalone test harness)
    join_group_session_id: Optional[str] = None  # set when joining via a shared code (blueprint 4.7)
    current_step_index: int = 0
    answers: dict[str, Any] = field(default_factory=dict)
    inferred_steps: set[str] = field(default_factory=set)  # steps pre-filled from OPENING_PROMPT, see profile_extractor.py
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_step(self) -> SurveyStep:
        return _STEP_ORDER[self.current_step_index]

    @property
    def progress_fraction(self) -> float:
        return round(self.current_step_index / (len(_STEP_ORDER) - 1), 4)

    def _effective_step_order(self) -> list[SurveyStep]:
        """GROUP_SESSION_SETUP only applies if Q6 wasn't solo (blueprint
        4.7) — evaluated against whatever the final group_config answer
        is, whether it came from a direct Q6 answer or was inferred from
        OPENING_PROMPT (see SurveyService.answer). Anything in
        inferred_steps was already answered by inference and is skipped
        the same way GROUP_SESSION_SETUP is skipped for solo travellers —
        same mechanism, different trigger, per document 4's design."""
        group_config = self.answers.get(SurveyStep.Q6_GROUP_CONFIG.value)
        order = _STEP_ORDER
        if group_config == GroupConfig.SOLO.value or group_config is None:
            order = [s for s in order if s != SurveyStep.GROUP_SESSION_SETUP]
        if self.inferred_steps:
            order = [s for s in order if s.value not in self.inferred_steps]
        return order

    def advance(self) -> SurveyStep:
        order = self._effective_step_order()
        idx = order.index(self.current_step)
        if idx + 1 < len(order):
            self.current_step_index = _STEP_ORDER.index(order[idx + 1])
        return self.current_step


class SurveyService:
    def __init__(
        self,
        profile_repository: TouristProfileRepository,
        curiosity_extractor: CuriosityExtractor,
        session_store: SurveySessionStore,
        profile_extractor: ProfileExtractor | None = None,
    ):
        self.profile_repository = profile_repository
        self.curiosity_extractor = curiosity_extractor
        self.session_store = session_store
        # Optional and separate from curiosity_extractor (not a
        # replacement for it) so existing callers that construct
        # SurveyService without this argument keep working exactly as
        # before — OPENING_PROMPT simply won't be able to pre-fill
        # anything, and the survey falls back to asking every question
        # directly, same as today.
        self.profile_extractor = profile_extractor

    async def start_session(
        self, device_id: Optional[str] = None, join_group_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SurveySession:
        session = SurveySession(
            id=str(uuid.uuid4()), device_id=device_id, user_id=user_id,
            join_group_session_id=join_group_session_id,
        )
        await self.session_store.set(session)
        return session

    async def get_session(self, session_id: str, requesting_user_id: Optional[str] = None) -> SurveySession:
        session = await self.session_store.get(session_id)
        if session is None:
            raise ValueError(f"Survey session {session_id} not found")
        # SECURITY FIX (final-release-hardening pass, Oct 2026): see
        # SurveySessionNotOwned. requesting_user_id is None only for
        # layer1's own standalone test harness, which never passes it —
        # every real HTTP call site (trips/routes.py, layer1/api/routes.py)
        # always passes the authenticated caller's id, so this check is
        # live in both production survey surfaces. session.user_id is
        # None only for a session created before this fix shipped (the
        # 1-hour Redis TTL means those age out on their own) or by the
        # test harness — same "predates the ownership log" allowance
        # shared/ownership.py already documents for tourist_profiles, not
        # a new gap.
        if requesting_user_id is not None and session.user_id is not None and session.user_id != requesting_user_id:
            raise SurveySessionNotOwned(f"Survey session {session_id} does not belong to this account")
        return session

    async def answer(self, session_id: str, answer: Any, requesting_user_id: Optional[str] = None) -> SurveySession:
        session = await self.get_session(session_id, requesting_user_id=requesting_user_id)
        step = session.current_step
        self._validate(step, answer)
        session.answers[step.value] = answer

        if step == SurveyStep.OPENING_PROMPT:
            self._apply_opening_prompt_inference(session, answer)

        session.advance()
        await self.session_store.set(session)
        return session

    def _apply_opening_prompt_inference(self, session: SurveySession, opening_text: str) -> None:
        """Document 4's "Talk to Your Guide" flow: the opening sentence
        always supplies Q7's curiosity text (it IS the sentence Q7 used to
        ask for separately — see profile_extractor.py docstring), and may
        additionally pre-fill Q1/Q2/Q3/Q6 when the lexicon found a single,
        unambiguous signal for that field. Each pre-filled field is
        written into session.answers under its real step key — exactly as
        if the tourist had answered that step directly — so finalize()'s
        existing exact-key reads and TouristProfile construction need zero
        changes and carry zero extra risk. A field the extractor couldn't
        confidently call (empty or conflicting matches) is simply left
        alone and its normal question still gets asked."""
        session.answers[SurveyStep.Q7_CURIOSITY_TEXT.value] = opening_text
        session.inferred_steps.add(SurveyStep.Q7_CURIOSITY_TEXT.value)

        if self.profile_extractor is None:
            return

        inferred: InferredProfile = self.profile_extractor.extract(opening_text)

        if inferred.purpose is not None:
            session.answers[SurveyStep.Q1_PURPOSE.value] = inferred.purpose.value
            session.inferred_steps.add(SurveyStep.Q1_PURPOSE.value)
        if inferred.energy_band is not None:
            session.answers[SurveyStep.Q2_ENERGY.value] = inferred.energy_band.value
            session.inferred_steps.add(SurveyStep.Q2_ENERGY.value)
        if inferred.crowd_tolerance is not None:
            session.answers[SurveyStep.Q3_CROWD_TOLERANCE.value] = inferred.crowd_tolerance.value
            session.inferred_steps.add(SurveyStep.Q3_CROWD_TOLERANCE.value)
        if inferred.group_config is not None:
            session.answers[SurveyStep.Q6_GROUP_CONFIG.value] = inferred.group_config.value
            session.inferred_steps.add(SurveyStep.Q6_GROUP_CONFIG.value)

    def _validate(self, step: SurveyStep, answer: Any) -> None:
        try:
            if step == SurveyStep.OPENING_PROMPT:
                if not isinstance(answer, str) or not answer.strip():
                    raise InvalidSurveyAnswer("Opening prompt requires a non-empty sentence")
            elif step == SurveyStep.Q1_PURPOSE:
                Purpose(answer)
            elif step == SurveyStep.Q2_ENERGY:
                EnergyBand(answer)
            elif step == SurveyStep.Q3_CROWD_TOLERANCE:
                CrowdTolerance(answer)
            elif step == SurveyStep.Q4_BUDGET:
                if not isinstance(answer, (int, float)) or answer < 0:
                    raise InvalidSurveyAnswer("Q4 budget must be a non-negative number")
            elif step == SurveyStep.Q5_DIETARY:
                for flag in answer:
                    DietaryFlag(flag)
            elif step == SurveyStep.Q6_GROUP_CONFIG:
                GroupConfig(answer)
            elif step == SurveyStep.ACCESSIBILITY:
                for flag in answer:
                    AccessibilityFlag(flag)
            elif step == SurveyStep.Q7_CURIOSITY_TEXT:
                if not isinstance(answer, str) or not answer.strip():
                    raise InvalidSurveyAnswer("Q7 requires a non-empty sentence")
            elif step == SurveyStep.Q8_TRIP_DURATION:
                TripDuration(answer["duration"] if isinstance(answer, dict) else answer)
            elif step == SurveyStep.Q9_START_TIME:
                StartTimePreference(answer)
            elif step == SurveyStep.RETURN_VISITOR_CHECK:
                if not isinstance(answer, bool):
                    raise InvalidSurveyAnswer("Return visitor check expects yes/no (bool)")
            elif step == SurveyStep.VOICE_PERSONALITY:
                VoicePersonality(answer)
            elif step == SurveyStep.GROUP_SESSION_SETUP:
                pass  # answer is just an ack; group_session_id generated in finalize()
        except ValueError as exc:
            raise InvalidSurveyAnswer(f"Invalid answer for {step.value}: {answer}") from exc

    async def finalize(self, session_id: str, requesting_user_id: Optional[str] = None) -> TouristProfile:
        session = await self.get_session(session_id, requesting_user_id=requesting_user_id)
        if session.current_step != SurveyStep.COMPLETE:
            raise InvalidSurveyAnswer("Survey is not yet complete — cannot finalize")

        a = session.answers
        curiosity_text = a[SurveyStep.Q7_CURIOSITY_TEXT.value]
        curiosity_vector = self.curiosity_extractor.extract(curiosity_text)

        duration_answer = a[SurveyStep.Q8_TRIP_DURATION.value]
        multi_day_count = None
        if isinstance(duration_answer, dict):
            trip_duration = TripDuration(duration_answer["duration"])
            multi_day_count = duration_answer.get("days")
        else:
            trip_duration = TripDuration(duration_answer)

        group_config = GroupConfig(a[SurveyStep.Q6_GROUP_CONFIG.value])

        profile = TouristProfile(
            id=str(uuid.uuid4()),
            purpose=Purpose(a[SurveyStep.Q1_PURPOSE.value]),
            energy_band=EnergyBand(a[SurveyStep.Q2_ENERGY.value]),
            crowd_tolerance=CrowdTolerance(a[SurveyStep.Q3_CROWD_TOLERANCE.value]),
            budget=float(a[SurveyStep.Q4_BUDGET.value]),
            device_id=session.device_id,
            dietary_flags=[DietaryFlag(f) for f in a[SurveyStep.Q5_DIETARY.value]],
            group_config=group_config,
            curiosity_text=curiosity_text,
            curiosity_vector=curiosity_vector,
            trip_duration_hours=trip_duration,
            multi_day_count=multi_day_count,
            start_time_preference=StartTimePreference(a[SurveyStep.Q9_START_TIME.value]),
            accessibility_flags=[AccessibilityFlag(f) for f in a.get(SurveyStep.ACCESSIBILITY.value, [])],
            companion_language=CompanionLanguage.ENGLISH,  # question removed by request; see class docstring
            voice_personality=VoicePersonality(a[SurveyStep.VOICE_PERSONALITY.value]),
            created_at=datetime.now(timezone.utc),
            # SECURITY FIX (final-release-hardening pass, Oct 2026): stamp
            # the real ownership record directly, rather than leaving
            # shared/ownership.py to infer it later from a TripEvent log
            # entry that might never get written. session.user_id is None
            # for an anonymous/device-only survey — profile stays
            # unowned, same as before this fix.
            user_id=session.user_id,
        )

        # Return Visitor check (4.5)
        if a.get(SurveyStep.RETURN_VISITOR_CHECK.value) and session.device_id:
            prior = await self.profile_repository.get_prior_session_for_device(session.device_id)
            if prior and prior.id:
                profile.return_visitor_exclusions = await self.profile_repository.get_visited_place_ids(prior.id)

        # Group Session setup (4.7). Joining via a shared code (someone else
        # already started this group) links to their exact group_session_id
        # instead of minting a new one; starting fresh as a group mints one.
        if session.join_group_session_id:
            profile.group_session_id = session.join_group_session_id
        elif group_config != GroupConfig.SOLO:
            profile.new_group_session()

        saved = await self.profile_repository.save(profile)
        # The survey is done — drop its transient state so it doesn't sit
        # around in Redis until its TTL expires for no reason.
        await self.session_store.delete(session_id)
        return saved
