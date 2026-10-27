#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Layer 3 command-line entry point.

    python run_layer3.py --serve                 start the API   (port from LAYER3_PORT, default 8004; --port overrides)
    python run_layer3.py --demo                  offline scripted walkthrough on sample data (no internet, no other layers)
    python run_layer3.py --status                configuration + connection health
    python run_layer3.py --healthcheck           exit code 0 if healthy (for scripts / CI)
    python run_layer3.py --init-db               create Layer 3's own tables (idempotent)
    python run_layer3.py --ask "Is it spicy?" --place <place_id> [--lang kn]
    python run_layer3.py --test-voice --place <place_id>     print the companion voice in every language x personality
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):          # Windows consoles: print Kannada / Hindi without crashing
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from layer3_config import DEFAULT_PORT, LAYER3_VERSION, Settings, get_settings  # noqa: E402


def _j(x) -> str:
    return json.dumps(x, indent=2, ensure_ascii=False, default=str)


def cmd_serve(args) -> int:
    import uvicorn
    s = get_settings()
    port = args.port or s.port
    host = args.host or s.host
    print(f"Ground Zero Layer 3 v{LAYER3_VERSION} -> http://{host}:{port}   docs: http://localhost:{port}/docs")
    uvicorn.run("layer3_api:asgi", host=host, port=port, factory=True, log_level=s.log_level.lower())
    return 0


def cmd_status(args) -> int:
    from layer3_orchestrator import Layer3Orchestrator
    print(_j(Layer3Orchestrator().health()))
    return 0


def cmd_healthcheck(args) -> int:
    from layer3_orchestrator import Layer3Orchestrator
    h = Layer3Orchestrator().health()
    print(h["status"])
    return 0 if h["status"] == "ok" else 1


def cmd_init_db(args) -> int:
    from layer3_repository import SqlLayer3Repository
    s = get_settings()
    SqlLayer3Repository(s.database_url).create_all()
    print("Layer 3 tables ready:", s.public_dict()["database_url"])
    return 0


def cmd_ask(args) -> int:
    from layer3_orchestrator import Layer3Orchestrator
    o = Layer3Orchestrator()
    print(_j(o.ask(args.ask, place_id=args.place, language=args.lang)))
    return 0


def cmd_test_voice(args) -> int:
    from layer3_orchestrator import Layer3Orchestrator
    o = Layer3Orchestrator()
    place = o.master.require(args.place)
    for lang in ("en", "kn", "kok", "hi"):
        for voice in ("warm", "historian", "witty"):
            m = o.voice.compose(place, voice, lang)
            print(f"[{lang}/{voice}] {m.text}")
    return 0


# ---------------------------------------------------------------------------------------------
# offline demo
# ---------------------------------------------------------------------------------------------
def cmd_demo(args) -> int:
    import httpx
    from layer3_orchestrator import Layer3Orchestrator

    def net(request: httpx.Request) -> httpx.Response:   # stand-in for Open-Meteo so the demo works offline
        url = str(request.url)
        if "marine" in url:
            return httpx.Response(200, json={"current": {"wave_height": 0.8, "wave_period": 8}})
        return httpx.Response(200, json={"current": {"temperature_2m": 28, "precipitation": 0, "rain": 0, "weather_code": 1,
                                                     "wind_speed_10m": 10, "wind_gusts_10m": 20, "is_day": 1}, "hourly": {"time": [], "weather_code": []}})

    tmp = Path(tempfile.mkdtemp(prefix="l3demo_"))
    s = Settings(database_url=f"sqlite:///{(tmp / 'demo.db').as_posix()}", master_core_path=HERE / "sample_data" / "master_data_core.sample.json",
                 layer0_data_dir=tmp, layer0_db_path=tmp / "none.db", allow_time_override=True, redis_url=None, groq_api_key=None)
    o = Layer3Orchestrator(s, http=httpx.Client(transport=httpx.MockTransport(net)))
    profile = json.loads((HERE / "sample_data" / "profile.sample.json").read_text(encoding="utf-8"))
    itin = json.loads((HERE / "sample_data" / "itinerary.sample.json").read_text(encoding="utf-8"))

    def hdr(t: str) -> None:
        print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)

    def stand_still(sid, lat, lng, end: datetime, minutes: float = 2.5):
        for i in range(int(minutes * 2), -1, -1):
            o.ping(sid, lat, lng, accuracy_m=10, timestamp=(end - timedelta(seconds=30 * i)).isoformat())

    ist = timezone(timedelta(hours=5, minutes=30))
    t = datetime(2026, 9, 22, 9, 45, tzinfo=ist).astimezone(timezone.utc)

    hdr("1. Start a session (Layer 1 profile + Layer 2 itinerary -> Layer 3 queue)")
    sess = o.start_session(profile=profile, itinerary=itin, session_id="demo")
    for sl in sess["queue"]:
        print(f"   {sl['order']}. {sl['role']:<13} {sl['place_id'] or '(meal break, no place)'}")

    hdr("2. Tourist walks past the church WITHOUT stopping -> Tier A movement blocker keeps the app silent")
    for i in range(6):
        o.ping("demo", 12.8698 + 0.0001 * i, 74.8433 + 0.00012 * i, timestamp=(t - timedelta(seconds=150 - 30 * i)).isoformat())
    r = o.evaluate("demo", lat=12.8703, lng=74.8439, timestamp=t.isoformat(), now=t.isoformat())
    print("   decision:", r["decision"], "| reason:", r["reason"], "| retry in", r["retry_after_seconds"], "s")

    hdr("3. She stops at Milagres Church for 2+ minutes -> all clear -> ONE sentence")
    stand_still("demo", 12.8698, 74.8433, t + timedelta(minutes=4))
    r = o.evaluate("demo", lat=12.8698, lng=74.8433, timestamp=(t + timedelta(minutes=4)).isoformat(), now=(t + timedelta(minutes=4)).isoformat())
    print("   decision:", r["decision"], "| Tier B:", r["tier_b"]["weighted_average"], "(threshold 0.75)")
    print("   >>", r["message"]["text"])
    nid = r["message"]["notification_id"]
    print("   'Tell me more' >>", o.tell_more("demo", notification_id=nid)["text"])
    print("   Ask 'Is this wheelchair accessible?' >>", o.ask("Is this wheelchair accessible?", session_id="demo")["answer"])

    hdr("4. A second stop 3 minutes later -> notification-fatigue gap (8 min) blocks it")
    t2 = t + timedelta(minutes=7)
    stand_still("demo", 12.8690, 74.8420, t2, 3)          # standing at Janata Idli Shop
    o.record_visit("demo", "gz_milagres", satisfaction="up")
    r = o.evaluate("demo", lat=12.8690, lng=74.8420, timestamp=t2.isoformat(), now=t2.isoformat())
    print("   decision:", r["decision"], "| reason:", r["reason"], "| gap check:", r["tier_a"]["checks"]["fatigue_gap"]["remaining_seconds"], "s left")

    hdr("5. 12 minutes later at St. Ann's Chapel, which is temporarily_unavailable -> silent Replan Trigger")
    t3 = t + timedelta(minutes=16)
    stand_still("demo", 12.8712, 74.8449, t3, 3)
    r = o.evaluate("demo", lat=12.8712, lng=74.8449, timestamp=t3.isoformat(), now=t3.isoformat())
    print("   replan:", r["replan"]["original"]["name"], "->", (r["replan"]["substitute"] or {}).get("name"), "| decision:", r["decision"])
    print("   >>", (r["message"] or {}).get("text"))

    hdr("6. Same moment in Kannada / Hindi / Konkani voices (Calm Historian)")
    place = o.master.require("gz_kadri")
    for lang in ("kn", "hi", "kok"):
        print(f"   [{lang}]", o.voice.compose(place, "historian", lang).text)

    hdr("7. Quiet Hours: 30 minutes muted, then a severe-weather alert breaks through")
    o.set_quiet("demo", 30, now=(t + timedelta(minutes=40)).isoformat())
    r = o.evaluate("demo", lat=12.8705, lng=74.8440, now=(t + timedelta(minutes=41)).isoformat())
    print("   during quiet hours:", r["decision"], "|", r["reason"])
    o.sos("demo", 12.8705, 74.8440, now=(t + timedelta(minutes=42)).isoformat())
    r = o.evaluate("demo", lat=12.8705, lng=74.8440, now=(t + timedelta(minutes=53)).isoformat())
    print("   SOS pressed (safety bypasses Quiet Hours):", r["decision"], "|", (r["message"] or {}).get("text"))

    print("\nDemo complete. Database was in", tmp)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ground Zero Layer 3 — Context Engine + Silence Filter + Ask Engine")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=None, help=f"override LAYER3_PORT (default {DEFAULT_PORT})")
    ap.add_argument("--host", default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--healthcheck", action="store_true")
    ap.add_argument("--init-db", action="store_true")
    ap.add_argument("--ask", metavar="QUESTION")
    ap.add_argument("--place", metavar="PLACE_ID")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--test-voice", action="store_true")
    a = ap.parse_args()
    if a.serve:
        return cmd_serve(a)
    if a.demo:
        return cmd_demo(a)
    if a.status:
        return cmd_status(a)
    if a.healthcheck:
        return cmd_healthcheck(a)
    if a.init_db:
        return cmd_init_db(a)
    if a.ask:
        if not a.place:
            ap.error("--ask needs --place")
        return cmd_ask(a)
    if a.test_voice:
        if not a.place:
            ap.error("--test-voice needs --place")
        return cmd_test_voice(a)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
