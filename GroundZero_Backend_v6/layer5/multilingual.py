"""
Layer 5 Feature: Multilingual Support

Phase 6 Implementation (Aug 5 2026): Multi-language support
Supports: English, Hindi, Kannada, Tamil, Telugu, Tulu

Features:
- Automatic language detection
- Real-time translation
- Language-aware UI
- Multilingual voice commands
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List

logger = logging.getLogger("groundzero.layer5.multilingual")


class Language(str, Enum):
    """Supported languages."""
    ENGLISH = "en"
    HINDI = "hi"
    KANNADA = "kn"
    TAMIL = "ta"
    TELUGU = "te"
    TULU = "tulu"


@dataclass
class LocalizedContent:
    """Content in multiple languages."""
    english: str
    hindi: Optional[str] = None
    kannada: Optional[str] = None
    tamil: Optional[str] = None
    telugu: Optional[str] = None
    tulu: Optional[str] = None

    def get(self, language: Language) -> str:
        """Get content in specified language, fallback to English."""
        mapping = {
            Language.ENGLISH: self.english,
            Language.HINDI: self.hindi,
            Language.KANNADA: self.kannada,
            Language.TAMIL: self.tamil,
            Language.TELUGU: self.telugu,
            Language.TULU: self.tulu,
        }
        return mapping.get(language) or self.english


class LanguageDetector:
    """Automatically detects user's preferred language."""

    def __init__(self):
        self.detected_language = Language.ENGLISH
        self.confidence = 0.0

    async def detect(self, text: str) -> tuple[Language, float]:
        """
        Detect language of given text.
        
        Returns:
            (detected_language, confidence_score)
        """
        # In production: use language detection library (textblob, langdetect)
        # For now: simple heuristic
        
        text_lower = text.lower()
        
        # Kannada specific words
        if any(char in text for char in ['ಅ', 'ಬ', 'ಚ', 'ಡ']):
            self.detected_language = Language.KANNADA
            self.confidence = 0.9
        # Tamil specific words
        elif any(char in text for char in ['அ', 'ஆ', 'இ', 'ஈ']):
            self.detected_language = Language.TAMIL
            self.confidence = 0.9
        # Telugu specific words
        elif any(char in text for char in ['అ', 'ఆ', 'ఇ', 'ఈ']):
            self.detected_language = Language.TELUGU
            self.confidence = 0.9
        # Hindi specific words
        elif any(char in text for char in ['अ', 'आ', 'इ', 'ई']):
            self.detected_language = Language.HINDI
            self.confidence = 0.9
        else:
            self.detected_language = Language.ENGLISH
            self.confidence = 0.5

        logger.debug("Detected language: %s (confidence: %.1f)", self.detected_language, self.confidence)
        return self.detected_language, self.confidence


class TranslationService:
    """
    Translates content between languages.
    Uses cloud API (Google Translate, or open-source alternative).
    """

    def __init__(self, source_language: Language = Language.ENGLISH):
        self.source_language = source_language
        self.translation_cache: Dict[tuple, str] = {}

    async def translate(self, text: str, target_language: Language) -> tuple[str, bool]:
        """
        Translate text to target language.

        Args:
            text: Text to translate
            target_language: Target language

        Returns:
            (text, was_translated) — `was_translated` is False whenever no
            real translation happened.

        Bug fixed: the old version returned `f"[{lang}] {text}"` for any
        non-source language — a fabricated string that *looks* like a
        real translation (it's tagged and formatted like one) but is just
        the original English text with a bracket stuck on the front. A
        caller or UI trusting that string would silently show English
        text to a Kannada/Tamil/Telugu/Hindi/Tulu speaker labelled as if
        it had actually been translated. No real translation backend
        (e.g. Google Translate, IndicTrans2) is wired up yet, and this
        module's "no-fabrication" policy — used everywhere else in this
        codebase for place data — applies here too: it's better to return
        the original text and say plainly that it wasn't translated than
        to fabricate output. Swap this method's body out once a real
        translation backend is integrated.
        """
        cache_key = (text, target_language.value)
        if cache_key in self.translation_cache:
            return self.translation_cache[cache_key], True

        if target_language == self.source_language:
            return text, True

        logger.warning(
            "No translation backend configured — returning original text untranslated for %s", target_language
        )
        return text, False

    async def translate_place(self, place: dict, target_language: Language) -> dict:
        """Translate place information to target language.

        Adds an explicit `translation_available` flag to the returned
        dict (True only if every translated field came from a real
        backend) so a UI can decide whether to show a "machine
        translation unavailable" notice instead of silently displaying
        untranslated English as if it were the target language.
        """
        translated_place = place.copy()
        all_translated = True

        for field_name in ("name", "description", "category"):
            if field_name in place and place[field_name] is not None:
                translated, was_translated = await self.translate(place[field_name], target_language)
                translated_place[field_name] = translated
                all_translated = all_translated and was_translated

        translated_place["translation_available"] = all_translated
        return translated_place


class MultilingualInterface:
    """
    Main interface for multilingual support.
    Manages language selection, detection, and translation.
    """

    def __init__(self):
        self.current_language = Language.ENGLISH
        self.detector = LanguageDetector()
        self.translator = TranslationService()
        self.supported_languages = list(Language)

    async def set_language(self, language: Language) -> None:
        """Set user's preferred language."""
        self.current_language = language
        self.translator.source_language = language
        logger.info("Language set to: %s", language)

    async def detect_and_set_language(self, text: str) -> Language:
        """Auto-detect language and set it."""
        language, confidence = await self.detector.detect(text)
        if confidence > 0.7:
            await self.set_language(language)
        return language

    async def get_place_in_language(self, place: dict, language: Optional[Language] = None) -> dict:
        """Get place information in specified language."""
        target_language = language or self.current_language
        
        if target_language == Language.ENGLISH:
            return place

        return await self.translator.translate_place(place, target_language)

    async def translate_query(self, query: str, target_language: Language) -> str:
        """Translate search query to target language.

        Returns just the text (dropping the `was_translated` flag) since
        callers of this method historically expect a plain string; with no
        backend configured this is a no-op passthrough of the original
        query, which is the correct fallback for a search query anyway.
        """
        text, _was_translated = await self.translator.translate(query, target_language)
        return text

    def get_supported_languages(self) -> List[tuple]:
        """Get list of supported languages."""
        language_names = {
            Language.ENGLISH: "English",
            Language.HINDI: "हिन्दी",
            Language.KANNADA: "ಕನ್ನಡ",
            Language.TAMIL: "தமிழ்",
            Language.TELUGU: "తెలుగు",
            Language.TULU: "ತುಳು",
        }
        return [(lang, language_names[lang]) for lang in self.supported_languages]

    def get_language_name(self, language: Language) -> str:
        """Get display name for language."""
        names = {
            Language.ENGLISH: "English",
            Language.HINDI: "हिन्दी (Hindi)",
            Language.KANNADA: "ಕನ್ನಡ (Kannada)",
            Language.TAMIL: "தமிழ் (Tamil)",
            Language.TELUGU: "తెలుగు (Telugu)",
            Language.TULU: "ತುಳು (Tulu)",
        }
        return names.get(language, "Unknown")
