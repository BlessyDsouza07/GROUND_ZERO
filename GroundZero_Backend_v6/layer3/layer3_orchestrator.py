# -*- coding: utf-8 -*-
"""
Layer 3 orchestrator — the single entry point Layer 4 (and the HTTP API) talks to.

evaluate() is the heart of Layer 3.  Order of decisions (first "stay silent" wins):

    safety override  ->  session active?  ->  Quiet Hours  ->  find target slot (300 m geofence or manual "I'm here")
    ->  Replan Trigger (temporarily_unavailable)  ->  geofence silence  ->  group gate (ANCHOR)
    ->  Tier A (fatigue gap, movement)  ->  Tier B (9 weighted signals >= 0.75)  ->  companion_voice

Nothing here writes to Layers 0/1/2.  All state lives in Layer 3's own `l3_*` tables.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from layer3_ask_engine import AskEngine
from layer3_bridge import Layer2Client, LiveFlagOverlay, MasterCoreStore, ProfileStore, normalize_itinerary, safe_id
from layer3_companion_voice import CompanionVoice
from layer3_config import LAYER3_VERSION, SERVICE_NAME, Settings, get_settings
from layer3_context_engine import TierAEvaluator, TierBEvaluator
from layer3_geofence import GeofenceEngine, GeoCandidate
from layer3_llm import LLMClient
from layer3_models import CheckResult, Decision, LayerError, NotFound, SessionStatus, SourceUnavailable
from layer3_replan import ReplanEngine
from layer3_repository import AbstractLayer3Repository, SqlLayer3Repository
from layer3_safety import SafetyEngine
from layer3_silence_filter import SilenceFilter
from layer3_sources import SignalSources
from layer3_utils import (
    as_list, ensure_aware, get_logger, iso, normalize_energy, normalize_language, normalize_voice,
    parse_dt, pget, place_id_of, place_latlng, place_name_of, utcnow, valid_latlng,
)

log = get_logger("layer3.orchestrator")

ALLOWED_TRANSITIONS = {
    "survey": {"active"},
    "active": {"paused", "ended_early", "completed"},
    "paused": {"active", "ended_early"},
    "ended_early": set(),
    "completed": set(),
}


def _ser(obj: Any) -> Any:
    """Make DB rows JSON-safe (datetimes -> ISO strings)."""
    if isinstance(obj, datetime):
        return iso(obj)
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_ser(v) for v in obj]
    return obj


class Layer3Orchestrator:
    def __init__(self, settings: Optional[Settings] = None, repo: Optional[AbstractLayer3Repository] = None,
                 master: Optional[MasterCoreStore] = None, http=None, llm: Optional[LLMClient] = None):
        self.s = settings or get_settings()
        self.repo = repo or SqlLayer3Repository(self.s.database_url)
        self.repo.create_all()
        self.master = master or MasterCoreStore(self.s.master_core_path)
        self.flags = LiveFlagOverlay(self.s.layer0_db_path, enabled=self.s.use_layer0_db_flags)
        self.profiles = ProfileStore(self.s)
        self.layer2 = Layer2Client(self.s)
        self.sources = SignalSources(self.s, self.repo, http=http)
        self.safety = SafetyEngine(self.s, self.sources)
        self.tier_a = TierAEvaluator(self.s)
        self.tier_b = TierBEvaluator(self.s, self.sources, self.master)
        self.silence = SilenceFilter(self.s, self.repo)
        self.geofence = GeofenceEngine(self.s.geofence_radius_m, self.s.place_boundary_m, self.s.place_release_m)
        self.replan = ReplanEngine(self.s, self.master)
        self.llm = llm or LLMClient(self.s)
        self.voice = CompanionVoice(self.s, self.llm)
        self.ask_engine = AskEngine(self.s, self.llm, self.sources, self.master, self.voice)

    # ======================================================================
    # helpers
    # ======================================================================
    def _now(self, override: Any = None) -> datetime:
        if override is not None and self.s.allow_time_override:
            dt = parse_dt(override)
            if dt:
                return dt
        return utcnow()

    def _require_session(self, session_id: str) -> Dict[str, Any]:
        safe_id(session_id)
        s = self.repo.get_session(session_id)
        if not s:
            raise NotFound(f"Session '{session_id}' not found. Start one with POST /l3/session/start", "session_not_found")
        return s

    @staticmethod
    def _canon_slot(x: Dict[str, Any], i: int) -> Dict[str, Any]:
        sl = copy.deepcopy(x)
        sl["role"] = str(sl.get("role") or sl.get("slot_role") or "PERSONAL").upper()
        if sl.get("place_id") is not None:
            sl["place_id"] = str(sl["place_id"])
        sl.setdefault("place_id", None)
        sl.setdefault("status", "pending")
        sl.setdefault("day", 1)
        sl["order"] = i
        sl.setdefault("slot_id", f"s{i}")
        return sl

    def _unavailable_ids(self) -> set:
        return set(self.repo.active_unavailable_ids()) | set(self.flags.unavailable_ids())

    def _is_unavailable(self, place: Dict[str, Any], flagged: set) -> bool:
        pid = place_id_of(place)
        return bool(place.get("temporarily_unavailable")) or (pid in flagged if pid else False)

    def _public_session(self, s: Dict[str, Any], include_queue: bool = True) -> Dict[str, Any]:
        out = {k: v for k, v in s.items() if k not in ("profile",)}
        prof = s.get("profile") or {}
        out["profile_summary"] = {k: prof.get(k) for k in ("purpose", "energy_band", "crowd_tolerance", "budget", "group_config",
                                                           "curiosity_vector", "accessibility_flags", "companion_language", "voice_personality") if k in prof}
        if not include_queue:
            out.pop("queue", None)
        return _ser(out)

    def _session_snapshot(self, sid: str) -> Dict[str, Any]:
        s = self.repo.get_session(sid) or {}
        streak = int(s.get("consecutive_dismissals") or 0)
        return _ser({
            "status": s.get("status"),
            "fatigue_gap_minutes": self.s.fatigue_gap_after_dismissals_min if streak >= self.s.dismissal_streak else self.s.fatigue_gap_min,
            "dismissed_count": s.get("dismissed_count"), "consecutive_dismissals": streak,
            "quiet_until": s.get("quiet_until"), "last_notification_at": s.get("last_notification_at"),
            "geofence_lock_place_id": s.get("geofence_lock_place_id"), "energy_band": s.get("energy_band"),
            "sos_active": bool(s.get("sos_active")), "current_slot_index": s.get("current_slot_index"),
            "wallet_remaining": s.get("wallet_remaining"), "voice": s.get("voice"), "language": s.get("language"),
        })

    # ======================================================================
    # session lifecycle
    # ======================================================================
    def start_session(self, *, profile_id: Optional[str] = None, profile: Optional[Dict[str, Any]] = None,
                      itinerary: Optional[Any] = None, queue: Optional[List[Dict[str, Any]]] = None,
                      session_id: Optional[str] = None, device_id: Optional[str] = None, language: Optional[str] = None,
                      voice: Optional[str] = None, group_session_id: Optional[str] = None,
                      wallet_remaining: Optional[int] = None) -> Dict[str, Any]:
        if profile is None:
            if not profile_id:
                raise LayerError("Provide profile_id (Layer 1) or an inline profile", 422, "profile_required")
            profile = self.profiles.get(profile_id)
        profile = dict(profile or {})
        profile_id = profile_id or str(pget(profile, "profile_id", "id", default="")) or None
        if profile_id:
            safe_id(profile_id)

        if queue is None:
            if itinerary is None:
                if not profile_id:
                    raise LayerError("No itinerary supplied and no profile_id to ask Layer 2 for one", 422, "itinerary_required")
                itinerary = self.layer2.generate(profile_id)
            queue = normalize_itinerary(itinerary)
        else:
            queue = [self._canon_slot(x, i) for i, x in enumerate(queue) if isinstance(x, dict)]
        if not queue:
            raise LayerError("Itinerary contained no usable slots (no role + place_id pairs found)", 422, "empty_itinerary")

        sid = session_id or uuid.uuid4().hex[:16]
        safe_id(sid)
        rec = self.repo.save_session({
            "session_id": sid, "profile_id": profile_id, "device_id": device_id or pget(profile, "device_id"),
            "group_session_id": group_session_id or pget(profile, "group_session_id"),
            "status": "active",
            "language": normalize_language(language or pget(profile, "companion_language", "language"), self.s.default_language),
            "voice": normalize_voice(voice or pget(profile, "voice_personality", "voice")),
            "profile": profile, "queue": queue, "current_slot_index": 0,
            "energy_band": normalize_energy(pget(profile, "energy_band")),
            "consecutive_dismissals": 0, "dismissed_count": 0, "visited_place_ids": [],
            "wallet_remaining": wallet_remaining, "sos_active": False,
        })
        missing = [s["place_id"] for s in queue if s.get("place_id") and not self.master.get(s["place_id"])]
        out = self._public_session(rec)
        out["warnings"] = ([f"{len(missing)} queue place(s) not found in master_data_core.json: {missing[:5]}"] if missing else [])
        return out

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._public_session(self._require_session(session_id))

    def set_queue(self, session_id: str, *, itinerary: Optional[Any] = None, queue: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Layer 4 keeps the authoritative queue (Pace Coach, Resume Evaluation...) and syncs it here."""
        self._require_session(session_id)
        if queue is not None:
            new_q = [self._canon_slot(x, i) for i, x in enumerate(queue) if isinstance(x, dict)]
        elif itinerary is not None:
            new_q = normalize_itinerary(itinerary)
        else:
            raise LayerError("Provide queue or itinerary", 422, "queue_required")
        if not new_q:
            raise LayerError("Queue is empty", 422, "empty_itinerary")
        return self._public_session(self.repo.update_session(session_id, queue=new_q, current_slot_index=0))

    def update_state(self, session_id: str, *, status: Optional[str] = None, energy_band: Optional[str] = None,
                     wallet_remaining: Optional[int] = None, language: Optional[str] = None, voice: Optional[str] = None,
                     group_session_id: Optional[str] = None, now: Any = None) -> Dict[str, Any]:
        s = self._require_session(session_id)
        upd: Dict[str, Any] = {}
        if status is not None:
            try:
                new = SessionStatus(status).value
            except ValueError:
                raise LayerError("status must be one of survey / active / paused / ended_early / completed", 422, "bad_status")
            cur = s["status"]
            if new != cur and new not in ALLOWED_TRANSITIONS.get(cur, set()):
                raise LayerError(f"Illegal status transition {cur} -> {new}", 409, "illegal_transition")
            upd["status"] = new
            if new in ("ended_early", "completed", "paused"):
                upd["geofence_lock_place_id"] = None
                upd["geofence_lock_since"] = None
        if energy_band is not None:
            eb = normalize_energy(energy_band)
            if eb is None:
                raise LayerError("energy_band must be low / medium / high", 422, "bad_energy")
            upd["energy_band"], upd["energy_updated_at"] = eb, self._now(now)
        if wallet_remaining is not None:
            upd["wallet_remaining"] = int(wallet_remaining)
        if language is not None:
            upd["language"] = normalize_language(language, s["language"])
        if voice is not None:
            upd["voice"] = normalize_voice(voice, s["voice"])
        if group_session_id is not None:
            upd["group_session_id"] = group_session_id
        return self._public_session(self.repo.update_session(session_id, **upd), include_queue=False)

    # ======================================================================
    # location
    # ======================================================================
    def ping(self, session_id: str, lat: float, lng: float, accuracy_m: Optional[float] = None,
             speed_mps: Optional[float] = None, timestamp: Any = None) -> Dict[str, Any]:
        self._require_session(session_id)
        if not valid_latlng(lat, lng):
            raise LayerError("Invalid coordinates", 422, "bad_coordinates")
        ts = parse_dt(timestamp) or utcnow()
        self.repo.add_ping(session_id, float(lat), float(lng), ts, accuracy_m, speed_mps)
        if hasattr(self.repo, "prune_pings"):
            self.repo.prune_pings(session_id, utcnow() - timedelta(minutes=self.s.ping_retention_min))  # type: ignore[attr-defined]
        return {"ok": True, "session_id": session_id, "ts": iso(ts)}

    # ======================================================================
    # THE decision: evaluate
    # ======================================================================
    def evaluate(self, session_id: str, *, lat: Optional[float] = None, lng: Optional[float] = None,
                 accuracy_m: Optional[float] = None, speed_mps: Optional[float] = None, timestamp: Any = None,
                 manual_trigger: bool = False, target_place_id: Optional[str] = None,
                 recent_pings: Optional[List[Dict[str, Any]]] = None, dry_run: bool = False, now: Any = None,
                 energy_band: Optional[str] = None, visited_place_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        t0 = self._now(now)
        persist = not dry_run
        if not self.master.all():
            raise LayerError(f"master_data_core.json not found or empty at {self.s.master_core_path} — run Layer 0 export_core first", 503, "master_core_missing")
        session = self._require_session(session_id)
        profile = session.get("profile") or {}
        warnings: List[str] = []
        if now is not None and not self.s.allow_time_override:
            warnings.append("time override ignored (LAYER3_ALLOW_TIME_OVERRIDE is false)")

        # ---- location -------------------------------------------------------
        has_loc = lat is not None and lng is not None
        if has_loc and not valid_latlng(lat, lng):
            raise LayerError("Invalid coordinates", 422, "bad_coordinates")
        cur_ping = None
        if has_loc:
            cur_ping = {"lat": float(lat), "lng": float(lng), "ts": parse_dt(timestamp) or t0,
                        "accuracy_m": accuracy_m, "speed_mps": speed_mps}
            if persist:
                self.repo.add_ping(session_id, cur_ping["lat"], cur_ping["lng"], cur_ping["ts"], accuracy_m, speed_mps)
        pings = self._gather_pings(session_id, t0, cur_ping if (dry_run and cur_ping) else None, recent_pings)
        loc = (float(lat), float(lng)) if has_loc else ((pings[-1]["lat"], pings[-1]["lng"]) if pings else None)

        # ---- state updates carried on the request ------------------------------
        if energy_band and persist:
            eb = normalize_energy(energy_band)
            if eb and eb != session.get("energy_band"):
                session = self.repo.update_session(session_id, energy_band=eb, energy_updated_at=t0)  # type: ignore[assignment]
        visited_ids = [str(x) for x in (session.get("visited_place_ids") or [])]
        for v in (visited_place_ids or []):
            if str(v) not in visited_ids:
                visited_ids.append(str(v))

        result: Dict[str, Any] = {
            "session_id": session_id, "evaluated_at": iso(t0), "dry_run": dry_run,
            "trigger": "manual" if manual_trigger else "geofence", "decision": Decision.SILENT.value, "reason": None,
            "retry_after_seconds": self.s.retry_after_s, "target": None, "tier_a": None, "tier_b": None,
            "message": None, "replan": None, "queue_update": None, "safety": None, "warnings": warnings,
        }

        def finish(decision: Decision, reason: str, retry: Optional[int] = -1, **extra: Any) -> Dict[str, Any]:
            result["decision"], result["reason"] = decision.value, reason
            if retry != -1:
                result["retry_after_seconds"] = retry
            if decision == Decision.SPEAK:
                result["retry_after_seconds"] = None
            result.update(extra)
            if persist:
                tgt = result.get("target") or {}
                self.repo.log_evaluation({
                    "session_id": session_id, "place_id": tgt.get("place_id"), "decision": decision.value, "reason": reason[:96],
                    "trigger": result["trigger"], "tier_a": result.get("tier_a"), "tier_b": result.get("tier_b"), "created_at": t0})
            result["session"] = self._session_snapshot(session_id)
            return result

        # ---- 0. SAFETY OVERRIDE (only thing that may break through everything) ---------
        safety = self.safety.check(session, loc[0] if loc else None, loc[1] if loc else None, t0)
        result["safety"] = safety.to_dict()
        if safety.active:
            return self._handle_safety(session, safety, loc, t0, persist, finish)

        # ---- 1. session must be active ------------------------------------------
        if self.silence.session_gate(session):
            return finish(Decision.SILENT, "session_not_active", retry=None)

        # ---- 2. Quiet Hours -----------------------------------------------------
        q = self.silence.quiet_gate(session, t0)
        if q:
            return finish(Decision.SILENT, "quiet_hours", retry=max(q["remaining_seconds"], 1), quiet=q)

        # ---- 3. find the target slot ------------------------------------------------
        queue: List[Dict[str, Any]] = copy.deepcopy(session.get("queue") or [])
        if manual_trigger:
            cand = self.geofence.next_pending(queue, self.master, target_place_id)
            if not cand:
                return finish(Decision.SILENT, "no_pending_slot", retry=None)
            if loc:
                d = self.geofence.distance_to(cand.place, loc[0], loc[1])
                cand.distance_m = d if d is not None else -1.0
                if d is not None and d > 2000:
                    warnings.append(f"manual trigger is {int(d)} m from the next slot")
        else:
            if not loc:
                return finish(Decision.SILENT, "no_location")
            near = self.geofence.candidates(queue, self.master, loc[0], loc[1], only_within_radius=True)
            if not near:
                allc = self.geofence.candidates(queue, self.master, loc[0], loc[1], only_within_radius=False)
                nearest = {"place_id": allc[0].slot["place_id"], "name": place_name_of(allc[0].place),
                           "distance_m": round(allc[0].distance_m)} if allc else None
                return finish(Decision.SILENT, "no_slot_in_range", nearest_pending=nearest)
            cand = near[0]

        # ---- 4. Replan Trigger ----------------------------------------------------
        flagged = self._unavailable_ids()
        replan_info = None
        if self._is_unavailable(cand.place, flagged):
            cand, replan_info = self._do_replan(session, profile, queue, cand, loc, t0, flagged, visited_ids, persist)
            result["replan"] = replan_info
            if replan_info.get("queue_changed"):
                result["queue_update"] = {"queue": _ser(queue), "reason": "temporarily_unavailable"}
            if cand is None:
                return finish(Decision.SILENT, "replan_no_substitute")
        place, slot = cand.place, cand.slot
        d_now = self.geofence.distance_to(place, loc[0], loc[1]) if loc else None
        result["target"] = {"place_id": place_id_of(place), "name": place_name_of(place), "role": slot.get("role"),
                            "slot_index": cand.slot_index, "distance_m": None if d_now is None else round(d_now)}
        if replan_info:
            result["trigger"] = "replan"

        # ---- 5. geofence silence (inside a place we already told them about) ------------
        why, release = self.silence.geofence_silence(session, self.master, loc[0] if loc else None, loc[1] if loc else None, place_id_of(place))
        if release and persist:
            session = self.repo.update_session(session_id, geofence_lock_place_id=None, geofence_lock_since=None)  # type: ignore[assignment]
        if why:
            return finish(Decision.SILENT, why)

        # ---- 6. group gate (ANCHOR slot waits for the group) ---------------------------
        g = self.silence.group_gate(session, slot, place, t0)
        if g:
            return finish(Decision.SILENT, g["reason"], group=g)

        # ---- 7. Tier A --------------------------------------------------------------
        fatigue = self.tier_a.fatigue(session, t0)
        movement = self.tier_a.movement(pings, t0)
        safety_check = CheckResult("safety_override", True, {"sources": safety.sources})
        checks = [safety_check, fatigue, movement]
        tier_a_ok = all(c.passed for c in checks)
        result["tier_a"] = {"passed": tier_a_ok, "checks": {c.name: c.to_dict() for c in checks}}
        if not tier_a_ok:
            return finish(*self._silent_from(self.silence.arbitrate(checks, None)[1], fatigue))

        # ---- 8. Tier B ----------------------------------------------------------------
        tb = self.tier_b.evaluate(session, profile, place, t0, loc[0] if loc else None, loc[1] if loc else None, visited_ids)
        result["tier_b"] = tb.to_dict()
        decision, reason = self.silence.arbitrate(checks, tb)
        if decision != Decision.SPEAK:
            return finish(decision, reason)
        if self.s.enforce_open_hours:
            for sig in tb.signals:
                if sig.name == "time_of_day" and sig.detail.get("flag") == "closed_now_by_opening_hours":
                    return finish(Decision.SILENT, "place_closed_now")

        # ---- 9. SPEAK: exactly one companion_voice sentence ---------------------------------
        msg = self.voice.compose(place, session["voice"], session["language"], t0)
        payload = msg.to_dict()
        nid = uuid.uuid4().hex
        payload["notification_id"] = nid
        if persist:
            self.repo.add_notification({
                "notification_id": nid, "session_id": session_id, "place_id": place_id_of(place), "kind": "companion",
                "message": msg.text, "language": msg.language, "voice": msg.voice,
                "tier_b_score": tb.weighted_average, "payload": {"role": slot.get("role"), "replan": bool(replan_info)},
                "status": "sent", "created_at": t0})
            queue[cand.slot_index]["status"] = "notified"
            queue[cand.slot_index]["notified_at"] = iso(t0)
            self.repo.update_session(session_id, queue=queue, last_notification_at=t0, geofence_lock_place_id=place_id_of(place),
                                     geofence_lock_since=t0, current_slot_index=cand.slot_index)
        result["message"] = payload
        return finish(Decision.SPEAK, "all_clear", retry=None)

    # ------------------------------------------------------------------ evaluate helpers
    def _silent_from(self, arb_reason: str, fatigue: CheckResult):
        retry = self.s.retry_after_s
        if arb_reason == "tier_a_failed:fatigue_gap":
            retry = max(int(fatigue.detail.get("remaining_seconds", retry)), self.s.retry_after_s // 3)
        return Decision.SILENT, arb_reason, retry

    def _gather_pings(self, session_id: str, now: datetime, cur: Optional[Dict[str, Any]], extra: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        rows = self.repo.recent_pings(session_id, now - timedelta(minutes=15))
        seen = {(ensure_aware(r["ts"]).replace(microsecond=0), round(r["lat"], 6), round(r["lng"], 6)) for r in rows}
        merged = list(rows)
        cands = ([cur] if cur else []) + list(extra or [])
        for p in cands:
            try:
                ts = parse_dt(p.get("ts") or p.get("timestamp"))
                la, ln = float(p["lat"]), float(p["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if ts is None or not valid_latlng(la, ln) or ts > now + timedelta(seconds=5):
                continue
            key = (ts.replace(microsecond=0), round(la, 6), round(ln, 6))
            if key in seen:
                continue
            seen.add(key)
            merged.append({"lat": la, "lng": ln, "ts": ts, "accuracy_m": p.get("accuracy_m"), "speed_mps": p.get("speed_mps")})
        merged.sort(key=lambda r: ensure_aware(r["ts"]))
        return merged

    def _handle_safety(self, session, safety, loc, t0, persist, finish) -> Dict[str, Any]:
        sid = session["session_id"]
        kind = safety.kind.value  # type: ignore[union-attr]
        last = self.repo.last_safety_notification(sid, kind)
        if last and (t0 - ensure_aware(last["created_at"])).total_seconds() < self.s.safety_repeat_min * 60:
            return finish(Decision.SILENT, "safety_alert_active_repeat_suppressed", retry=self.s.retry_after_s)
        help_names: List[str] = []
        if kind == "sos" and loc:
            help_names = [place_name_of(p) for _, p in self.master.nearby(loc[0], loc[1], 5000, {"EMERGENCY"}, 3)]
        msg = self.voice.safety(kind, safety.reason_code, safety.reason_text, session["language"], help_names)
        nid = uuid.uuid4().hex
        payload = msg.to_dict()
        payload["notification_id"] = nid
        payload["safety_kind"] = kind
        payload["nearest_help"] = help_names
        if persist:
            self.repo.add_notification({"notification_id": nid, "session_id": sid, "place_id": None, "kind": "safety", "safety_kind": kind,
                                        "message": msg.text, "language": msg.language, "voice": "safety", "status": "sent", "created_at": t0,
                                        "payload": {"reason_code": safety.reason_code}})
        return finish(Decision.SAFETY_ALERT, f"safety:{kind}", retry=self.s.retry_after_s, message=payload)

    def _do_replan(self, session, profile, queue, cand: GeoCandidate, loc, t0, flagged, visited_ids, persist):
        sid = session["session_id"]
        original = cand.slot
        pid = original["place_id"]
        info: Dict[str, Any] = {"triggered": True, "reason": "temporarily_unavailable", "original": {
            "place_id": pid, "name": place_name_of(cand.place), "role": original.get("role")}, "substitute": None, "queue_changed": True}
        original["status"] = "replaced"
        sub = self.replan.find_substitute(
            role=original.get("role", "PERSONAL"), original_place_id=pid, profile=profile, queue=queue,
            visited_ids=set(visited_ids), unavailable_ids=flagged,
            lat=loc[0] if loc else None, lng=loc[1] if loc else None, now=t0,
            energy_band=session.get("energy_band"), wallet_remaining=session.get("wallet_remaining"))
        new_cand: Optional[GeoCandidate] = None
        if sub:
            sp = sub["place"]
            new_slot = {"slot_id": f"{original.get('slot_id', 's')}-r{uuid.uuid4().hex[:4]}", "day": original.get("day", 1),
                        "role": original.get("role"), "place_id": place_id_of(sp), "place_name": place_name_of(sp),
                        "status": "pending", "time_window": original.get("time_window"), "transport_tag": original.get("transport_tag"),
                        "replaced_from": pid, "personal_fit": sub["personal_fit"]}
            idx = cand.slot_index + 1
            queue.insert(idx, new_slot)
            for i, sl in enumerate(queue):
                sl["order"] = i
            new_cand = GeoCandidate(idx, new_slot, sp, self.geofence.distance_to(sp, loc[0], loc[1]) if loc else -1.0)  # type: ignore[arg-type]
            info["substitute"] = {"place_id": place_id_of(sp), "name": place_name_of(sp), "personal_fit": sub["personal_fit"], "rank_score": sub["rank_score"], "distance_km": sub["distance_km"],
                                  "raw_score": sub["raw_score"], "bias_index": sub["bias_index"], "components": sub["components"],
                                  "candidates_considered": sub.get("candidates_considered")}
        if persist:
            self.repo.update_session(sid, queue=queue)
            self.repo.add_replan({"session_id": sid, "original_place_id": pid, "substitute_place_id": place_id_of(sub["place"]) if sub else None,
                                  "role": original.get("role"), "reason": "temporarily_unavailable",
                                  "personal_fit": sub["personal_fit"] if sub else None, "created_at": t0})
        return new_cand, info

    # ======================================================================
    # notification feedback
    # ======================================================================
    def dismiss(self, session_id: str, notification_id: str) -> Dict[str, Any]:
        s = self._require_session(session_id)
        n = self._require_notification(session_id, notification_id)
        if n["status"] == "sent":
            self.repo.update_notification(notification_id, status="dismissed", responded_at=utcnow())
            if n["kind"] == "companion":
                self.repo.update_session(session_id, consecutive_dismissals=int(s.get("consecutive_dismissals") or 0) + 1,
                                         dismissed_count=int(s.get("dismissed_count") or 0) + 1)
        return {"ok": True, "session": self._session_snapshot(session_id)}

    def engage(self, session_id: str, notification_id: str, action: str = "tapped") -> Dict[str, Any]:
        self._require_session(session_id)
        self._require_notification(session_id, notification_id)
        self.repo.update_notification(notification_id, status="engaged", responded_at=utcnow())
        self.repo.update_session(session_id, consecutive_dismissals=0)
        return {"ok": True, "action": action, "session": self._session_snapshot(session_id)}

    def _require_notification(self, session_id: str, notification_id: str) -> Dict[str, Any]:
        n = self.repo.get_notification(notification_id)
        if not n or n["session_id"] != session_id:
            raise NotFound(f"Notification '{notification_id}' not found for this session", "notification_not_found")
        return n

    def tell_more(self, session_id: str, notification_id: Optional[str] = None, place_id: Optional[str] = None,
                  language: Optional[str] = None) -> Dict[str, Any]:
        s = self._require_session(session_id)
        if notification_id:
            n = self._require_notification(session_id, notification_id)
            place_id = place_id or n.get("place_id")
        place = self._resolve_place(s, place_id)
        res = self.voice.tell_more(place, language or s["language"], s["voice"])
        if notification_id:
            self.repo.update_notification(notification_id, status="engaged", responded_at=utcnow())
            self.repo.update_session(session_id, consecutive_dismissals=0)
        return {"place_id": place_id_of(place), "place_name": place_name_of(place), **res}

    def _resolve_place(self, session: Optional[Dict[str, Any]], place_id: Optional[str]) -> Dict[str, Any]:
        if not place_id and session:
            last = self.repo.last_place_notification(session["session_id"])
            place_id = (last or {}).get("place_id") or session.get("geofence_lock_place_id")
        if not place_id:
            raise LayerError("place_id is required (or a session with a recent notification)", 422, "place_required")
        return self.master.require(str(place_id))

    # ======================================================================
    # Ask Engine
    # ======================================================================
    def ask(self, question: str, *, session_id: Optional[str] = None, place_id: Optional[str] = None,
            language: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None, now: Any = None) -> Dict[str, Any]:
        session = self._require_session(session_id) if session_id else None
        place = self._resolve_place(session, place_id)
        lang = normalize_language(language or (session or {}).get("language"), "en")
        voice = normalize_voice((session or {}).get("voice"))
        res = self.ask_engine.ask(place, question, lang, self._now(now), lat, lng, voice)
        try:
            self.repo.add_ask({"session_id": session_id, "place_id": place_id_of(place), "question": question[:500], "answer": res["answer"][:2000],
                               "grounded": bool(res.get("grounded")), "mode": res.get("mode"), "language": lang})
        except Exception as e:  # logging must never break an answer
            log.warning("ask log failed: %s", e)
        return res

    # ======================================================================
    # Quiet Hours, SOS, visits, flags, conditions, health
    # ======================================================================
    def set_quiet(self, session_id: str, minutes: Optional[float], now: Any = None) -> Dict[str, Any]:
        self._require_session(session_id)
        t0 = self._now(now)
        if not minutes or minutes <= 0:
            self.repo.update_session(session_id, quiet_until=None)
            return {"quiet_until": None, "session": self._session_snapshot(session_id)}
        minutes = min(float(minutes), 24 * 60)
        self.repo.update_session(session_id, quiet_until=t0 + timedelta(minutes=minutes))
        return {"quiet_until": iso(t0 + timedelta(minutes=minutes)), "note": "Only a safety alert can break through Quiet Hours",
                "session": self._session_snapshot(session_id)}

    def sos(self, session_id: str, lat: Optional[float] = None, lng: Optional[float] = None, now: Any = None) -> Dict[str, Any]:
        t0 = self._now(now)
        self._require_session(session_id)
        self.repo.update_session(session_id, sos_active=True, sos_since=t0)
        return self.evaluate(session_id, lat=lat, lng=lng, now=now)

    def clear_sos(self, session_id: str) -> Dict[str, Any]:
        self._require_session(session_id)
        self.repo.update_session(session_id, sos_active=False, sos_since=None)
        return {"ok": True, "session": self._session_snapshot(session_id)}

    def record_visit(self, session_id: str, place_id: str, *, arrived_at: Any = None, exited_at: Any = None,
                     dwell_minutes: Optional[float] = None, satisfaction: Optional[str] = None) -> Dict[str, Any]:
        s = self._require_session(session_id)
        place_id = str(place_id)
        a, e = parse_dt(arrived_at), parse_dt(exited_at)
        if dwell_minutes is None and a and e:
            dwell_minutes = round((e - a).total_seconds() / 60.0, 1)
        if satisfaction not in (None, "up", "down", "skip"):
            raise LayerError("satisfaction must be up / down / skip", 422, "bad_satisfaction")
        queue = copy.deepcopy(s.get("queue") or [])
        for sl in queue:
            if sl.get("place_id") == place_id and sl.get("status") in ("pending", "notified"):
                sl["status"] = "visited"
                sl["visited_at"] = iso(e or utcnow())
                break
        visited = list(s.get("visited_place_ids") or [])
        if place_id not in visited:
            visited.append(place_id)
        nxt = next((i for i, sl in enumerate(queue) if sl.get("status") == "pending"), len(queue))
        upd: Dict[str, Any] = {"queue": queue, "visited_place_ids": visited, "current_slot_index": nxt}
        if s.get("geofence_lock_place_id") == place_id:
            upd.update(geofence_lock_place_id=None, geofence_lock_since=None)
        # Minimal Wallet Tracker (Blueprint §8.2): a first arrival at a paying
        # place subtracts its estimated_cost from wallet_remaining, once —
        # a re-arrival (already in `visited`, checked above building `visited`)
        # never double-charges. Silent no-op if wallet tracking isn't in use
        # (wallet_remaining was never set) or the place has no cost on record.
        wallet_remaining = s.get("wallet_remaining")
        spent = None
        if wallet_remaining is not None and place_id not in (s.get("visited_place_ids") or []):
            try:
                place = self.master.get(place_id)
                cost = place.get("estimated_cost") if place else None
                if cost:
                    spent = round(float(cost), 2)
                    upd["wallet_remaining"] = max(0, round(float(wallet_remaining) - spent, 2))
            except Exception:
                pass  # master data unavailable — wallet just doesn't move for this visit
        self.repo.update_session(session_id, **upd)
        vid = self.repo.add_visit({"session_id": session_id, "device_id": s.get("device_id"), "place_id": place_id, "arrived_at": a,
                                   "exited_at": e, "dwell_minutes": dwell_minutes, "satisfaction": satisfaction})
        if satisfaction:  # a 👍/👎 tap is real engagement — resets the dismissal streak
            self.repo.update_session(session_id, consecutive_dismissals=0)
        out = {"ok": True, "visit_id": vid, "visited_place_ids": visited, "current_slot_index": nxt}
        if "wallet_remaining" in upd:
            out["wallet_remaining"] = upd["wallet_remaining"]
            out["wallet_spent_this_visit"] = spent
        return out

    def visits_for_device(self, device_id: str) -> Dict[str, Any]:
        rows = self.repo.visits_for_device(device_id)
        return {"device_id": device_id, "place_ids": sorted({r["place_id"] for r in rows}), "visits": _ser(rows)}

    def visits_for_session(self, session_id: str) -> Dict[str, Any]:
        # Trip-owned alternative to visits_for_device (5th audit
        # response, Oct 2026): a Trip's real visits, keyed by the
        # Layer 3 session_id that Trip.layer3_session_id already
        # records -- no device_id trust model needed. The repository
        # method already existed (layer3_repository.py); only this
        # thin orchestrator wrapper was missing.
        rows = self.repo.visits_for_session(session_id)
        return {"session_id": session_id, "place_ids": sorted({r["place_id"] for r in rows}), "visits": _ser(rows)}

    def report_place_unavailable(self, place_id: str, unavailable: bool = True, reason: str = "", reported_by: Optional[str] = None,
                                 ttl_hours: Optional[float] = None) -> Dict[str, Any]:
        self.master.require(place_id)
        ttl = ttl_hours if ttl_hours is not None else self.s.place_flag_ttl_h
        self.repo.set_place_flag(place_id, unavailable, reason[:200], reported_by, ttl if unavailable else None)
        return {"place_id": place_id, "unavailable": unavailable, "expires_in_hours": ttl if unavailable else None,
                "note": "Layer 3 overlay only — Layer 0's data is not modified."}

    def add_advisory(self, title: str, severity: str = "warning", area: Optional[str] = None, ttl_hours: Optional[float] = 12) -> Dict[str, Any]:
        return {"id": self.repo.add_advisory(title[:300], severity, area, ttl_hours)}

    def clear_advisory(self, advisory_id: int) -> Dict[str, Any]:
        return {"cleared": self.repo.deactivate_advisory(advisory_id)}

    def conditions(self, lat: float, lng: float, place_id: Optional[str] = None) -> Dict[str, Any]:
        place = self.master.get(place_id) if place_id else None
        return _ser(self.sources.snapshot(lat, lng, place, self._now()))

    def health(self) -> Dict[str, Any]:
        mc = self.master.status()
        db_ok = self.repo.ping_db()
        return {
            "service": SERVICE_NAME, "version": LAYER3_VERSION, "status": "ok" if (db_ok and mc["place_count"] > 0) else "degraded",
            "database": {"ok": db_ok, "url": self.s.public_dict()["database_url"]},
            "master_data_core": mc,
            "layer0_db_flag_overlay": {"enabled": self.flags.enabled, "available": self.flags.available},
            "redis": {"configured": bool(self.s.redis_url), "connected": self.sources.redis.enabled},
            "llm": {"provider": self.s.llm_provider, "enabled": self.llm.enabled, "model": self.s.groq_model if self.llm.enabled else None,
                    "anthropic_model": None},   # kept for backward-compatible health consumers
            "safety_sources": {"weather_alert": "open-meteo", "advisory_feed_configured": self.sources.advisory_feed_configured(), "sos": "manual"},
            "settings": self.s.public_dict(),
        }
