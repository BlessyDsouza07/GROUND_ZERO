# -*- coding: utf-8 -*-
"""
Companion voice — turns "the Silence Filter said speak" into exactly ONE short sentence
(+ an optional etiquette whisper in the same delivery, Blueprint §6.4).

Design:
  * Pre-templated per language x personality (Blueprint §4.4) — deterministic, offline, free.
  * The place-specific hook is chosen from the stored record only:
        age      -> wikidata_facts / description says it was built/founded in a given year
        hidden   -> few media mentions / mostly-local visitors / very low bias_index
        generic  -> fallback
  * Optional: LAYER3_VOICE_USE_LLM=true rewrites the line with the LLM (Groq), still grounded on the
    record only, and falls back to the template on any error or if the output looks unsafe.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from layer3_config import TTS_LOCALE, Settings
from layer3_i18n import (
    ETIQUETTE, ETIQUETTE_ALIASES, KIND_BY_CATEGORY, KIND_KEYWORDS, KINDS, STRINGS, TEMPLATES, t,
)
from layer3_models import VoiceMessage
from layer3_utils import (
    as_dict, as_list, first_sentences, get_logger, normalize_language, normalize_voice, num,
    pget, place_category, place_id_of, place_name_of, place_tags, utcnow,
)

log = get_logger("layer3.voice")

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")


def infer_kind(place: Dict[str, Any]) -> str:
    hay = " ".join([place_name_of(place), str(place.get("subcategory") or "")] + place_tags(place)).lower()
    for kw, kind in KIND_KEYWORDS:
        if kw in hay:
            return kind
    return KIND_BY_CATEGORY.get(place_category(place), "place")


def infer_built_year(place: Dict[str, Any]) -> Optional[int]:
    facts = as_dict(place.get("wikidata_facts"))
    for k, v in facts.items():
        if any(w in str(k).lower() for w in ("inception", "built", "founded", "established", "construct", "year")):
            m = _YEAR.search(str(v))
            if m:
                return int(m.group(1))
    extract = str(place.get("wikipedia_extract") or "")
    m = re.search(r"(?:built|founded|established|constructed|consecrated|erected|dating (?:back )?to)[^.]{0,40}?\b(1[0-9]{3}|20[0-2][0-9])\b", extract, re.I)
    return int(m.group(1)) if m else None


def is_hidden(place: Dict[str, Any]) -> bool:
    mm = place.get("media_mentions")
    lp = place.get("local_percentage")
    bi = place.get("bias_index")
    if mm is not None and num(mm, 999) <= 5:
        return True
    if lp is not None and num(lp, 0) >= 75:
        return True
    return bi is not None and num(bi, 1) <= 0.12


def normalize_etiquette(tag: Any) -> List[str]:
    """'remove footwear, no leather items inside' -> ['remove footwear', 'no leather']  (+ unknown tokens verbatim)."""
    out: List[str] = []
    for token in as_list(tag):
        low = token.lower().strip()
        key = low if low in ETIQUETTE else next((canon for alias, canon in ETIQUETTE_ALIASES.items() if alias in low), None)
        out.append(key or token.strip())
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


class CompanionVoice:
    def __init__(self, settings: Settings, llm=None):
        self.s = settings
        self.llm = llm

    # ------------------------------------------------------------------ main line
    def compose(self, place: Dict[str, Any], voice: str, language: str, now: Optional[datetime] = None) -> VoiceMessage:
        lang = normalize_language(language)
        voice = normalize_voice(voice)
        kind_key = infer_kind(place)
        noun, noun_a = KINDS[kind_key].get(lang, KINDS[kind_key]["en"])
        year = infer_built_year(place)
        age = None
        if year:
            ref = (now or utcnow()).year
            age = ref - year if 20 <= ref - year <= 2500 else None
        hook = "age" if age else ("hidden" if is_hidden(place) else "generic")
        minutes = int(round(num(place.get("dwell_time_typical"), 0) / 5.0) * 5) or 15
        minutes = max(5, min(minutes, 180))
        tpl = (TEMPLATES.get(lang) or TEMPLATES["en"])[voice][hook]
        main = tpl.format(name=place_name_of(place), kind=noun_a if lang == "en" else noun, kind_n=noun, age=age or "", minutes=minutes)
        mode = "template"
        if self.s.voice_use_llm and self.llm is not None and self.llm.enabled:
            polished = self._llm_line(place, voice, lang, main)
            if polished:
                main, mode = polished, "llm"
        whisper = self.whisper(place.get("etiquette_tag"), lang)
        text = f"{main} {whisper}" if whisper else main
        return VoiceMessage(
            text=text, language=lang, voice=voice, place_id=place_id_of(place), place_name=place_name_of(place),
            etiquette_whisper=whisper, kind="companion", tell_more_available=bool(self._detail_sentences(place, 1, skip=0)),
            tts_locale=TTS_LOCALE.get(lang, "en-IN"), mode=mode,
        )

    def whisper(self, etiquette_tag: Any, lang: str) -> Optional[str]:
        tokens = normalize_etiquette(etiquette_tag)
        if not tokens:
            return None
        phrases = []
        for tk in tokens:
            entry = ETIQUETTE.get(tk)
            phrases.append(entry.get(lang) or entry["en"] if entry else tk)
        joined = ", ".join(phrases)
        end = "." if lang == "en" else ("।" if lang in ("hi", "kok") else ".")
        return f"{t(lang, 'whisper_prefix')} {joined}{end}"

    # ------------------------------------------------------------------ Tell me more
    def _detail_sentences(self, place: Dict[str, Any], n: int, skip: int = 1) -> List[str]:
        text = str(place.get("wikipedia_extract") or "")
        sents = first_sentences(text, n, skip=skip)
        if not sents:
            facts = as_dict(place.get("wikidata_facts"))
            bits = [f"{str(k).replace('_', ' ').capitalize()}: {v}." for k, v in facts.items() if v not in (None, "", [], {})]
            sents = bits[:n]
        return sents

    # Personality-flavoured lead-ins for "Tell me more" — the grounded fact
    # sentence itself never changes (still zero LLM calls here, per Blueprint
    # §7.2's strict-grounding rule); only the framing around it matches the
    # warm / historian / witty voice picked at survey time, English only —
    # the kn/hi/kok packs are first-draft translations (see module docstring
    # in layer3_i18n.py) and aren't extended here to avoid low-quality text.
    _TELL_MORE_LEAD_EN = {
        "warm": "Here's something lovely about it:",
        "historian": "For the record:",
        "witty": "Here's a fun fact:",
    }

    def tell_more(self, place: Dict[str, Any], language: str, voice: str = "warm") -> Dict[str, Any]:
        """Return exactly ONE stored-fact sentence; never call the LLM here."""
        lang = normalize_language(language)
        v = normalize_voice(voice)
        sents = self._detail_sentences(place, 2, skip=0)
        if not sents:
            return {"text": t(lang, "no_more_detail"), "language": lang, "grounded": True, "available": False,
                    "sources": [], "tts_locale": TTS_LOCALE.get(lang, "en-IN"), "translated": False}
        text = (sents[1] if len(sents) > 1 else sents[0]).strip()
        if lang == "en":
            lead = self._TELL_MORE_LEAD_EN.get(v)
            if lead:
                text = f"{lead} {text}"
        # Keep the Tell Me More interaction deterministic and strictly grounded
        # in the stored Wikipedia/Wikidata record; no Groq/LLM translation or
        # generation is used for this tap — only the lead-in phrase above
        # varies by personality, never the grounded fact after it.
        return {"text": text, "language": lang, "grounded": True, "available": True,
                "sources": ["wikipedia_extract" if place.get("wikipedia_extract") else "wikidata_facts"],
                "tts_locale": TTS_LOCALE.get(lang, "en-IN"), "translated": False}

    # ------------------------------------------------------------------ safety
    def safety(self, kind: str, reason_code: Optional[str], reason_text: Optional[str], language: str,
               nearest_help: Optional[List[str]] = None) -> VoiceMessage:
        lang = normalize_language(language)
        if kind == "sos":
            text = t(lang, "safety_sos")
            if nearest_help:
                text += f" {t(lang, 'nearest_help')} {', '.join(nearest_help)}."
        elif kind == "weather_alert":
            reason = t(lang, f"reason_{reason_code}") if reason_code and f"reason_{reason_code}" in STRINGS["en"] \
                else (reason_text or "severe weather")
            text = t(lang, "safety_weather", reason=reason)
        else:
            text = t(lang, "safety_advisory", reason=reason_text or "advisory in effect")
        return VoiceMessage(text=text, language=lang, voice="safety", kind="safety", tts_locale=TTS_LOCALE.get(lang, "en-IN"))

    # ------------------------------------------------------------------ optional LLM polish
    def _llm_line(self, place: Dict[str, Any], voice: str, lang: str, fallback: str) -> Optional[str]:
        facts = {k: place.get(k) for k in ("name", "category", "subcategory", "tags", "dwell_time_typical", "wikipedia_extract") if place.get(k)}
        system = ("You write ONE short sentence (max 30 words) that a friendly local guide would say as a tourist approaches a place. "
                  f"Tone: {voice}. Language: {lang}. Use ONLY facts in the JSON record. Never invent facts, dates, prices or opening hours. "
                  "Output the sentence only.")
        out = self.llm.chat(system, "RECORD:\n" + str(facts)[:1500], max_tokens=90)
        if not out:
            return None
        out = out.strip().strip('"')
        if len(out) > 300 or "\n" in out:
            return None
        return out
