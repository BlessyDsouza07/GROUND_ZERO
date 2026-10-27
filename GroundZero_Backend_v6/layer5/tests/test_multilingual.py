import pytest

from layer5.multilingual import Language, MultilingualInterface, TranslationService


@pytest.mark.asyncio
async def test_translate_same_language_is_passthrough_and_marked_translated():
    svc = TranslationService(source_language=Language.ENGLISH)
    text, was_translated = await svc.translate("Hello", Language.ENGLISH)
    assert text == "Hello"
    assert was_translated is True


@pytest.mark.asyncio
async def test_translate_without_backend_returns_original_text_and_flags_it():
    # Regression test for the fabrication bug: the old implementation
    # returned "[kn] Hello" here — a fake-looking translation — instead
    # of honestly saying no translation happened.
    svc = TranslationService(source_language=Language.ENGLISH)
    text, was_translated = await svc.translate("Hello", Language.KANNADA)
    assert text == "Hello"
    assert was_translated is False


@pytest.mark.asyncio
async def test_translate_place_reports_translation_available_flag():
    ml = MultilingualInterface()
    place = {"name": "Milagres Church", "description": "A historic church.", "category": "heritage_site"}
    translated = await ml.translator.translate_place(place, Language.TAMIL)
    assert translated["translation_available"] is False
    # Content is preserved untranslated, not replaced with a fabricated string.
    assert translated["name"] == "Milagres Church"
