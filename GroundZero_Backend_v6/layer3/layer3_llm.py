"""
Thin LLM client for the Ask Engine (and the optional voice polish / translation).

Provider: Groq's OpenAI-compatible chat-completions endpoint (free tier, default model
`llama-3.1-8b-instant`). Set GROQ_API_KEY to enable. With no key — or LAYER3_LLM_PROVIDER=none —
`enabled` is False and every caller transparently uses its deterministic, extractive fallback.

The client never raises: on any failure it returns None and records `last_error` so the
caller can report an honest `mode` ("extractive_fallback") instead of pretending the LLM answered.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from layer3_config import Settings
from layer3_utils import get_logger

log = get_logger("layer3.llm")

LANG_NAMES = {"en": "English", "kn": "Kannada (ಕನ್ನಡ script)", "kok": "Konkani (Devanagari script)", "hi": "Hindi (Devanagari script)"}


class LLMClient:
    def __init__(self, settings: Settings, http: Optional[httpx.Client] = None):
        self.s = settings
        self.http = http or httpx.Client(timeout=settings.llm_timeout_s)
        self.last_error: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.s.llm_provider == "groq" and bool(self.s.groq_api_key)

    def chat(self, system: str, user: str, max_tokens: Optional[int] = None, temperature: float = 0.1) -> Optional[str]:
        if not self.enabled:
            self.last_error = "llm_disabled"
            return None
        payload: Dict[str, Any] = {
            "model": self.s.groq_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens or self.s.llm_max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.s.groq_api_key}", "Content-Type": "application/json"}
        url = self.s.groq_base_url.rstrip("/") + "/chat/completions"
        for attempt in (1, 2):
            try:
                r = self.http.post(url, json=payload, headers=headers)
            except httpx.HTTPError as e:
                self.last_error = f"network:{e.__class__.__name__}"
                log.warning("LLM network error: %s", e.__class__.__name__)
                return None
            if r.status_code == 429 and attempt == 1:
                try:
                    wait = min(2.0, float(r.headers.get("retry-after", "1")))
                except ValueError:
                    wait = 1.0
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                self.last_error = f"http_{r.status_code}"
                log.warning("LLM HTTP %s", r.status_code)
                return None
            try:
                content = r.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError):
                self.last_error = "bad_response"
                return None
            self.last_error = None
            return (content or "").strip() or None
        return None

    def translate(self, text: str, lang: str) -> Optional[str]:
        system = (f"Translate the user's text into {LANG_NAMES.get(lang, lang)}. Keep proper nouns. "
                  "Do not add, remove or change any facts. Output only the translation.")
        return self.chat(system, text[:1500], max_tokens=400)
