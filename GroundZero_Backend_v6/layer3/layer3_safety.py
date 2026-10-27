"""
Safety override — Blueprint §6.2.

Exactly THREE sources can trigger it:
  1. a severe weather alert from the weather API (thunderstorm / flood-grade rain / damaging wind)
  2. a government / local-authority travel advisory feed
  3. the tourist manually tapping SOS / Help

Every source reports whether it was actually CHECKED. A source that could not be read is
reported as `checked: false` — never as a silent "clear". An unreadable source does not
block companion notifications (that would silence the app for as long as an API is down),
but it is surfaced in the response so Layer 4 / the UI can show the gap.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from layer3_config import Settings
from layer3_models import SafetyKind, SafetyStatus, SourceUnavailable
from layer3_sources import SignalSources
from layer3_utils import get_logger

log = get_logger("layer3.safety")


class SafetyEngine:
    def __init__(self, settings: Settings, sources: SignalSources):
        self.s = settings
        self.sources = sources

    def check(self, session: Dict[str, Any], lat: Optional[float], lng: Optional[float], now: datetime) -> SafetyStatus:
        report: Dict[str, Dict[str, Any]] = {}
        winner: Optional[SafetyKind] = None
        code: Optional[str] = None
        text: Optional[str] = None

        # ---- source 3: manual SOS (checked first: it is the tourist's own explicit request)
        sos = bool(session.get("sos_active"))
        report["sos"] = {"checked": True, "active": sos}
        if sos:
            winner, code, text = SafetyKind.SOS, "sos", "sos"

        # ---- source 1: weather API severe alert
        if lat is None or lng is None:
            report["weather_alert"] = {"checked": False, "active": False, "detail": "no location supplied"}
        else:
            try:
                w = self.sources.weather(lat, lng)
                reason = w.get("severe_reason") or w.get("severe_soon")
                report["weather_alert"] = {"checked": True, "active": bool(reason),
                                           "detail": {"reason": reason, "weather_code": w.get("weather_code"),
                                                      "precipitation_mm": w.get("precipitation_mm"), "gust_kmh": w.get("gust_kmh"),
                                                      "source": w.get("source")}}
                if reason and winner is None:
                    winner, code, text = SafetyKind.WEATHER_ALERT, str(reason), str(reason)
            except SourceUnavailable as e:
                report["weather_alert"] = {"checked": False, "active": False, "detail": e.reason}

        # ---- source 2: authority advisories
        try:
            adv = self.sources.advisories()
            report["advisory"] = {"checked": True,
                                  "active": bool(adv),
                                  "detail": {"count": len(adv), "feed_configured": self.sources.advisory_feed_configured(),
                                             "items": [a["title"] for a in adv[:3]]}}
            if adv and winner is None:
                winner, code, text = SafetyKind.ADVISORY, "advisory", adv[0]["title"]
        except SourceUnavailable as e:
            # DB advisories still readable? re-check them alone so a dead feed doesn't hide an admin advisory
            try:
                local = self.sources.repo.active_advisories()
            except Exception:
                local = []
            report["advisory"] = {"checked": False, "active": bool(local), "detail": e.reason}
            if local and winner is None:
                winner, code, text = SafetyKind.ADVISORY, "advisory", local[0]["title"]

        return SafetyStatus(active=winner is not None, kind=winner, reason_code=code, reason_text=text, sources=report)
