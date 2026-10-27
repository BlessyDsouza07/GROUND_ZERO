"""
Layer3Client — a tiny typed wrapper Layer 4 (Live Guidance Loop / Stop-Pause module) can import
to talk to a running Layer 3 service. It contains NO Layer 3 logic.

    from layer3_client import Layer3Client
    l3 = Layer3Client("http://localhost:8004")
    sid = l3.start_session(profile_id="abc123")["session_id"]

    # every ~60 s while the trip is active:
    decision = l3.evaluate(sid, lat, lng, accuracy_m=12)
    if decision["decision"] in ("speak", "safety_alert"):
        push(decision["message"])          # FCM / WebSocket / whatever Layer 4 uses
    # else: stay silent and call again in decision["retry_after_seconds"]

Layer 4 -> Layer 3 event map (what to call, when):
    Stop -> Resume Later   update_state(sid, status="paused")
    Resume                 update_state(sid, status="active") ; set_queue(sid, queue=<re-evaluated queue>)
    Stop -> Exit Trip      update_state(sid, status="ended_early")
    Mood check-in          update_state(sid, energy_band="low")
    Wallet tracker         update_state(sid, wallet_remaining=520)
    Pace Coach trims slot  set_queue(sid, queue=<queue with the slot status "dropped">)
    Quiet hours button     quiet(sid, 30)
    SOS button             sos(sid, lat, lng)
    Tourist leaves a place record_visit(sid, place_id, arrived_at=..., exited_at=..., satisfaction="up")
    Notification dismissed dismiss(sid, notification_id)
    "I'm here" button      evaluate(sid, lat, lng, manual_trigger=True)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class Layer3Error(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status}] {code}: {message}")
        self.status, self.code, self.message = status, code, message


class Layer3Client:
    def __init__(self, base_url: str = "http://localhost:8004", api_key: Optional[str] = None, timeout: float = 30.0,
                 client: Optional[httpx.Client] = None):
        headers = {"X-API-Key": api_key} if api_key else {}
        self._c = client or httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    def _req(self, method: str, path: str, **kw: Any) -> Dict[str, Any]:
        r = self._c.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                e = r.json().get("error", {})
            except ValueError:
                e = {}
            raise Layer3Error(r.status_code, e.get("code", "http_error"), e.get("message", r.text[:200]))
        return r.json()

    # sessions
    def start_session(self, **body: Any) -> Dict[str, Any]:
        return self._req("POST", "/l3/session/start", json=body)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._req("GET", f"/l3/session/{session_id}")

    def set_queue(self, session_id: str, queue: Optional[List[Dict[str, Any]]] = None, itinerary: Any = None) -> Dict[str, Any]:
        return self._req("PUT", f"/l3/session/{session_id}/queue", json={"queue": queue, "itinerary": itinerary})

    def update_state(self, session_id: str, **fields: Any) -> Dict[str, Any]:
        return self._req("PUT", f"/l3/session/{session_id}/state", json=fields)

    # location + decision
    def ping(self, session_id: str, lat: float, lng: float, **kw: Any) -> Dict[str, Any]:
        return self._req("POST", "/l3/location/ping", json={"session_id": session_id, "lat": lat, "lng": lng, **kw})

    def evaluate(self, session_id: str, lat: Optional[float] = None, lng: Optional[float] = None, **kw: Any) -> Dict[str, Any]:
        return self._req("POST", "/l3/context/evaluate", json={"session_id": session_id, "lat": lat, "lng": lng, **kw})

    def conditions(self, lat: float, lng: float, place_id: Optional[str] = None) -> Dict[str, Any]:
        return self._req("GET", "/l3/conditions", params={"lat": lat, "lng": lng, "place_id": place_id})

    # feedback
    def dismiss(self, session_id: str, notification_id: str) -> Dict[str, Any]:
        return self._req("POST", "/l3/notify/dismiss", json={"session_id": session_id, "notification_id": notification_id})

    def engage(self, session_id: str, notification_id: str, action: str = "tapped") -> Dict[str, Any]:
        return self._req("POST", "/l3/notify/engage", json={"session_id": session_id, "notification_id": notification_id, "action": action})

    def tell_more(self, session_id: str, notification_id: Optional[str] = None, place_id: Optional[str] = None, language: Optional[str] = None) -> Dict[str, Any]:
        return self._req("POST", "/l3/notify/tell-more", json={"session_id": session_id, "notification_id": notification_id, "place_id": place_id, "language": language})

    # Ask Engine
    def ask(self, question: str, session_id: Optional[str] = None, place_id: Optional[str] = None, language: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
        return self._req("POST", "/l3/ask", json={"question": question, "session_id": session_id, "place_id": place_id, "language": language, **kw})

    # controls
    def quiet(self, session_id: str, minutes: Optional[float]) -> Dict[str, Any]:
        return self._req("POST", "/l3/quiet", json={"session_id": session_id, "minutes": minutes})

    def sos(self, session_id: str, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
        return self._req("POST", "/l3/sos", json={"session_id": session_id, "lat": lat, "lng": lng})

    def clear_sos(self, session_id: str) -> Dict[str, Any]:
        return self._req("POST", "/l3/sos/clear", json={"session_id": session_id})

    def record_visit(self, session_id: str, place_id: str, **kw: Any) -> Dict[str, Any]:
        return self._req("POST", "/l3/visit", json={"session_id": session_id, "place_id": place_id, **kw})

    def report_unavailable(self, place_id: str, unavailable: bool = True, **kw: Any) -> Dict[str, Any]:
        return self._req("POST", "/l3/place/report-unavailable", json={"place_id": place_id, "unavailable": unavailable, **kw})

    def health(self) -> Dict[str, Any]:
        return self._req("GET", "/l3/health")
