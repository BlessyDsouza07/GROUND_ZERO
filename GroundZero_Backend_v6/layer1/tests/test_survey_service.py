import pytest

from layer1.application.curiosity_extractor import CuriosityExtractor
from layer1.application.profile_extractor import ProfileExtractor
from layer1.application.survey_service import InvalidSurveyAnswer, SurveyService, SurveyStep
from layer1.domain.entities import TouristProfile
from layer1.domain.repositories import TouristProfileRepository
from layer1.infrastructure.survey_session_store import InMemorySurveySessionStore


class FakeProfileRepository(TouristProfileRepository):
    def __init__(self):
        self.saved: dict[str, TouristProfile] = {}

    async def save(self, profile: TouristProfile) -> TouristProfile:
        self.saved[profile.id] = profile
        return profile

    async def get_by_id(self, profile_id: str):
        return self.saved.get(profile_id)

    async def get_prior_session_for_device(self, device_id: str):
        matches = [p for p in self.saved.values() if p.device_id == device_id]
        return matches[-1] if matches else None

    async def get_visited_place_ids(self, profile_id: str) -> list[str]:
        return ["place-1", "place-2"]

    async def mark_visited(self, profile_id: str, place_ids: list[str]) -> list[str]:
        return sorted(set(place_ids))

    async def list_by_group_session(self, group_session_id: str) -> list[TouristProfile]:
        return [p for p in self.saved.values() if p.group_session_id == group_session_id]


def _service() -> tuple[SurveyService, FakeProfileRepository]:
    repo = FakeProfileRepository()
    return SurveyService(repo, CuriosityExtractor(), InMemorySurveySessionStore()), repo


async def _answer_all(service: SurveyService, session_id: str, group_config: str = "solo", return_visitor: bool = False):
    answers = [
        (SurveyStep.OPENING_PROMPT, "I want authentic local food and quiet beaches"),  # deliberately generic re: Q1/Q2/Q3/Q6 — no ProfileExtractor wired in _service(), so this only pre-fills Q7 (see profile_extractor.py); Q1/Q2/Q3/Q6 below still get answered directly, same as before this feature existed
        (SurveyStep.Q1_PURPOSE, "foodie"),
        (SurveyStep.Q2_ENERGY, "moderate"),
        (SurveyStep.Q3_CROWD_TOLERANCE, "fine"),
        (SurveyStep.Q4_BUDGET, 1500),
        (SurveyStep.Q5_DIETARY, ["veg"]),
        (SurveyStep.Q6_GROUP_CONFIG, group_config),
        (SurveyStep.ACCESSIBILITY, []),
        (SurveyStep.Q8_TRIP_DURATION, "full_day"),
        (SurveyStep.Q9_START_TIME, "morning"),
        (SurveyStep.RETURN_VISITOR_CHECK, return_visitor),
        (SurveyStep.VOICE_PERSONALITY, "warm_local_friend"),
    ]
    if group_config != "solo":
        answers.append((SurveyStep.GROUP_SESSION_SETUP, True))

    session = None
    for step, answer in answers:
        session = await service.answer(session_id, answer)
    return session


@pytest.mark.asyncio
async def test_full_survey_flow_solo_reaches_complete():
    service, _ = _service()
    session = await service.start_session(device_id="device-abc")
    assert session.current_step == SurveyStep.OPENING_PROMPT

    final_session = await _answer_all(service, session.id, group_config="solo")
    assert final_session.current_step == SurveyStep.COMPLETE


@pytest.mark.asyncio
async def test_group_config_inserts_group_session_setup_step():
    service, _ = _service()
    session = await service.start_session()
    final_session = await _answer_all(service, session.id, group_config="family")
    assert final_session.current_step == SurveyStep.COMPLETE


@pytest.mark.asyncio
async def test_solo_skips_group_session_setup_step():
    service, _ = _service()
    session = await service.start_session()
    order = session._effective_step_order()
    assert SurveyStep.GROUP_SESSION_SETUP not in order


@pytest.mark.asyncio
async def test_invalid_answer_raises():
    service, _ = _service()
    session = await service.start_session()
    await service.answer(session.id, "exploring the city")
    with pytest.raises(InvalidSurveyAnswer):
        await service.answer(session.id, "not_a_real_purpose")


@pytest.mark.asyncio
async def test_negative_budget_rejected():
    service, _ = _service()
    session = await service.start_session()
    await service.answer(session.id, "exploring the city")
    await service.answer(session.id, "foodie")
    await service.answer(session.id, "moderate")
    await service.answer(session.id, "fine")
    with pytest.raises(InvalidSurveyAnswer):
        await service.answer(session.id, -500)


@pytest.mark.asyncio
async def test_finalize_produces_tourist_profile_with_curiosity_vector():
    service, repo = _service()
    session = await service.start_session(device_id="device-xyz")
    await _answer_all(service, session.id, group_config="solo")

    profile = await service.finalize(session.id)
    assert profile.purpose.value == "foodie"
    assert profile.budget == 1500.0
    assert "local_kitchen" in profile.curiosity_vector.weights
    assert profile.id in repo.saved


@pytest.mark.asyncio
async def test_finalize_before_complete_raises():
    service, _ = _service()
    session = await service.start_session()
    await service.answer(session.id, "foodie")  # only answer Q1
    with pytest.raises(InvalidSurveyAnswer):
        await service.finalize(session.id)


@pytest.mark.asyncio
async def test_device_id_persists_onto_the_saved_profile():
    """Regression test: TouristProfile.device_id previously existed nowhere
    (not on the entity, not wired through save()), so Return Visitor Check
    could never find a prior session. Confirms the fix."""
    service, repo = _service()
    session = await service.start_session(device_id="device-persisted")
    await _answer_all(service, session.id, group_config="solo")
    profile = await service.finalize(session.id)
    assert profile.device_id == "device-persisted"


@pytest.mark.asyncio
async def test_return_visitor_finds_prior_session_via_device_id():
    service, repo = _service()

    # First visit — establishes a prior profile for this device.
    session1 = await service.start_session(device_id="repeat-device")
    await _answer_all(service, session1.id, group_config="solo", return_visitor=False)
    first_profile = await service.finalize(session1.id)
    assert first_profile.device_id == "repeat-device"

    # Second visit, same device, opts into "skip places from last visit".
    session2 = await service.start_session(device_id="repeat-device")
    await _answer_all(service, session2.id, group_config="solo", return_visitor=True)
    second_profile = await service.finalize(session2.id)

    assert second_profile.return_visitor_exclusions == ["place-1", "place-2"]


@pytest.mark.asyncio
async def test_group_config_generates_group_session_id():
    service, _ = _service()
    session = await service.start_session()
    await _answer_all(service, session.id, group_config="friends")
    profile = await service.finalize(session.id)
    assert profile.group_session_id is not None


@pytest.mark.asyncio
async def test_joining_a_group_via_shared_code_links_to_the_same_session():
    service, repo = _service()

    # First member starts a group, gets a group_session_id minted.
    session1 = await service.start_session(device_id="device-1")
    await _answer_all(service, session1.id, group_config="family")
    first_profile = await service.finalize(session1.id)
    shared_code = first_profile.group_session_id
    assert shared_code is not None

    # Second member joins using that exact code instead of minting a new one.
    session2 = await service.start_session(device_id="device-2", join_group_session_id=shared_code)
    await _answer_all(service, session2.id, group_config="family")
    second_profile = await service.finalize(session2.id)

    assert second_profile.group_session_id == shared_code

    linked = await repo.list_by_group_session(shared_code)
    assert {p.device_id for p in linked} == {"device-1", "device-2"}


@pytest.mark.asyncio
async def test_finalize_removes_session_from_store():
    service, _ = _service()
    session = await service.start_session()
    await _answer_all(service, session.id, group_config="solo")
    await service.finalize(session.id)

    with pytest.raises(ValueError):
        await service.get_session(session.id)


# --- ProfileExtractor / "Talk to Your Guide" opening-prompt inference ---

def _service_with_inference() -> tuple[SurveyService, FakeProfileRepository]:
    repo = FakeProfileRepository()
    service = SurveyService(
        repo, CuriosityExtractor(), InMemorySurveySessionStore(),
        profile_extractor=ProfileExtractor(),
    )
    return service, repo


@pytest.mark.asyncio
async def test_opening_prompt_infers_and_skips_confident_fields():
    """A clear, unambiguous sentence should pre-fill purpose/energy/group/
    crowd and skip straight past all their questions to the first one
    that wasn't confidently inferable (Q4_BUDGET — no lexicon exists for
    a number, by design)."""
    service, _ = _service_with_inference()
    session = await service.start_session(device_id="device-infer")
    session = await service.answer(
        session.id, "Just want to relax with my partner somewhere not too touristy"
    )

    assert SurveyStep.Q1_PURPOSE.value in session.inferred_steps
    assert SurveyStep.Q2_ENERGY.value in session.inferred_steps
    assert SurveyStep.Q6_GROUP_CONFIG.value in session.inferred_steps
    assert SurveyStep.Q3_CROWD_TOLERANCE.value in session.inferred_steps
    assert SurveyStep.Q7_CURIOSITY_TEXT.value in session.inferred_steps
    assert session.answers[SurveyStep.Q1_PURPOSE.value] == "leisure"
    assert session.answers[SurveyStep.Q2_ENERGY.value] == "low"
    assert session.answers[SurveyStep.Q6_GROUP_CONFIG.value] == "couple"
    assert session.answers[SurveyStep.Q3_CROWD_TOLERANCE.value] == "prefer_quiet"
    # Budget has no lexicon (it's a number, not inferable from prose) -> still asked directly
    assert session.current_step == SurveyStep.Q4_BUDGET


@pytest.mark.asyncio
async def test_opening_prompt_leaves_genuinely_ambiguous_purpose_unset():
    """This is document 4's own worked example sentence — it contains both
    a LEISURE trigger ("relax") and a FOODIE trigger ("good food"), so
    purpose is genuinely ambiguous and must NOT be guessed; the honesty
    rule (single confident match required, see profile_extractor.py) is
    the whole safety property of this feature."""
    service, _ = _service_with_inference()
    session = await service.start_session(device_id="device-ambiguous")
    session = await service.answer(
        session.id, "Honestly just want to relax, maybe with my partner, somewhere quiet with good food, not too touristy."
    )
    assert SurveyStep.Q1_PURPOSE.value not in session.inferred_steps
    assert session.current_step == SurveyStep.Q1_PURPOSE


@pytest.mark.asyncio
async def test_opening_prompt_with_no_signal_falls_back_to_every_question():
    """A generic sentence with no lexicon hits should infer nothing beyond
    Q7 (which the opening prompt always supplies) — full fallback to
    asking every other question directly, exactly as before this feature."""
    service, _ = _service_with_inference()
    session = await service.start_session(device_id="device-generic")
    session = await service.answer(session.id, "Mangaluru")

    assert session.inferred_steps == {SurveyStep.Q7_CURIOSITY_TEXT.value}
    assert session.current_step == SurveyStep.Q1_PURPOSE


@pytest.mark.asyncio
async def test_finalize_after_opening_prompt_inference_produces_valid_profile():
    """End-to-end: inferred fields plus the remaining directly-answered
    ones still assemble into a complete, valid TouristProfile — proves
    inference doesn't bypass validation or leave TouristProfile fields
    unset. Purpose/energy/group/crowd are all inferred for this sentence
    (see test above), so only budget through voice_personality remain."""
    service, repo = _service_with_inference()
    session = await service.start_session(device_id="device-e2e")
    session = await service.answer(session.id, "Relax with my partner, not too touristy")
    session = await service.answer(session.id, 2000)  # Q4_BUDGET (Q1/Q2/Q3/Q6 all inferred and skipped)
    session = await service.answer(session.id, ["no_restrictions"])  # Q5_DIETARY
    session = await service.answer(session.id, [])  # ACCESSIBILITY
    session = await service.answer(session.id, "full_day")  # Q8
    session = await service.answer(session.id, "morning")  # Q9
    session = await service.answer(session.id, False)  # RETURN_VISITOR_CHECK
    session = await service.answer(session.id, "calm_historian")  # VOICE_PERSONALITY
    session = await service.answer(session.id, True)  # GROUP_SESSION_SETUP (group_config was inferred as "couple", not solo)
    assert session.current_step == SurveyStep.COMPLETE

    profile = await service.finalize(session.id)
    assert profile.energy_band.value == "low"
    assert profile.group_config.value == "couple"
    assert profile.crowd_tolerance.value == "prefer_quiet"
    assert profile.purpose.value == "leisure"
    assert profile.curiosity_text == "Relax with my partner, not too touristy"
    assert profile.companion_language.value == "english"  # question removed; always English
    assert profile.id in repo.saved


@pytest.mark.asyncio
async def test_companion_language_question_is_never_asked():
    """Companion language is never asked; it defaults to English. Walks the
    whole flow and asserts no step named like a language question is ever
    presented, and that the finalized profile is English."""
    service, repo = _service()
    session = await service.start_session()
    seen_steps = [session.current_step.value]
    answers = {
        SurveyStep.OPENING_PROMPT: "I want authentic local food and quiet beaches",
        SurveyStep.Q1_PURPOSE: "foodie",
        SurveyStep.Q2_ENERGY: "moderate",
        SurveyStep.Q3_CROWD_TOLERANCE: "fine",
        SurveyStep.Q4_BUDGET: 1500,
        SurveyStep.Q5_DIETARY: ["veg"],
        SurveyStep.Q6_GROUP_CONFIG: "solo",
        SurveyStep.ACCESSIBILITY: [],
        SurveyStep.Q8_TRIP_DURATION: "full_day",
        SurveyStep.Q9_START_TIME: "morning",
        SurveyStep.RETURN_VISITOR_CHECK: False,
        SurveyStep.VOICE_PERSONALITY: "warm_local_friend",
    }
    while session.current_step != SurveyStep.COMPLETE:
        session = await service.answer(session.id, answers[session.current_step])
        seen_steps.append(session.current_step.value)

    assert not any("language" in s for s in seen_steps)
    profile = await service.finalize(session.id)
    assert profile.companion_language.value == "english"
