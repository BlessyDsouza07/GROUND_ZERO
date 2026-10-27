"""Talk to Guide — a grounded chat about Mangaluru.

How it answers (and why it can be trusted):
  1. The question is matched against GroundZero's own place catalog
     (Layer 0, ~700 places) — name, category, tags, description.
  2. The best matches are handed to the language model (Groq, free tier)
     as verified facts to prefer. It may also use well-established general
     knowledge about Mangaluru / coastal Karnataka, but must say so when it
     is unsure about hours, prices or anything time-sensitive.
  3. No GROQ_API_KEY, or Groq unreachable? The guide still answers —
     extractively, straight from the same place records — and says so in
     `mode`, instead of pretending a model replied.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user
from auth.models import User
from layer0.domain.repositories import PlaceRepository
from layer2.api.dependencies import get_place_repository
from shared.config import get_settings
from layer0.application.opening_hours_parser import OpeningHoursParser
from explore.hours import EAT, STAY, TRANSIT, open_info
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

logger = logging.getLogger("groundzero.guide")
_PARSER = OpeningHoursParser()


def _km(a, b, c, d) -> float:
    p1, p2 = radians(a), radians(c)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(d - b) / 2) ** 2
    return 12742 * asin(sqrt(h))

router = APIRouter(prefix="/guide", tags=["guide"])

LANGS = {"en": "English", "kn": "Kannada (ಕನ್ನಡ script)", "hi": "Hindi (Devanagari script)", "ta": "Tamil (தமிழ் script)", "te": "Telugu (తెలుగు script)"}
_STOP = {
    "the", "a", "an", "is", "are", "to", "of", "in", "on", "at", "for", "and", "or", "me", "my", "i", "we", "you", "what", "which",
    "where", "how", "can", "do", "does", "any", "some", "near", "best", "good", "place", "places", "mangaluru", "mangalore",
    "tell", "about", "show", "give", "suggest", "recommend", "should", "go", "visit", "there", "with", "this", "that", "it",
    "day", "days", "today", "time", "get", "know", "want", "need", "please", "hi", "hello", "hey", "from", "will", "would", "could",
    "have", "has", "be", "was", "were", "by", "as", "so", "if", "when", "why", "who", "much", "many", "far", "long", "like", "ok", "okay",
}


_KEY_NAMES = ("GROQ_API_KEY", "GROQ_KEY", "LAYER3_GROQ_API_KEY")
_BASE = Path(__file__).resolve().parent.parent  # backend root


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().strip('"').strip("'").strip()
    if v.lower().startswith("bearer "):
        v = v[7:].strip()
    return v or None


def _from_env_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.replace("export ", "").strip()
        if k in _KEY_NAMES or "GROQ" in k.upper() or v.strip().strip("\"'").startswith("gsk_"):
            v = v.split(" #")[0]
            got = _clean(v)
            if got:
                return got
    return None


def find_groq_key() -> tuple[str | None, str]:
    """Look everywhere a person could reasonably have put the key. Read on
    every call so editing .env then restarting is enough (and a live
    environment variable wins)."""
    for n in _KEY_NAMES:
        got = _clean(os.environ.get(n))
        if got:
            return got, f"environment ({n})"
    got = _clean(get_settings().groq_api_key)
    if got:
        return got, "settings"
    for v in os.environ.values():
        if v and v.strip().startswith("gsk_"):
            return _clean(v), "environment (value)"
    candidates: list[Path] = [_BASE / ".env", Path.cwd() / ".env", _BASE / "layer3" / ".env", _BASE / "live_events" / ".env", _BASE.parent / ".env"]
    for root in {_BASE, Path.cwd(), _BASE.parent}:
        try:
            for f in list(root.glob(".env*")) + list(root.glob("*.env")) + list(root.glob("*/.env*")):
                if f.is_file() and f.suffix not in (".py", ".pyc") and f not in candidates and ".example" not in f.name and "TEMPLATE" not in f.name.upper():
                    candidates.append(f)
        except OSError:
            pass
    for p in candidates:
        got = _from_env_file(p)
        if got:
            return got, str(p)
    return None, "not found"


_PREFERRED = ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "meta-llama/llama-4-scout-17b-16e-instruct",
              "openai/gpt-oss-20b", "gemma2-9b-it", "llama3-70b-8192", "llama3-8b-8192")
_models_cache: list[str] | None = None
_last_error: str | None = None


async def _available_models(client: httpx.AsyncClient, key: str, base: str) -> list[str]:
    """Ask Groq which chat models this key can use, so a retired model name
    can never break the guide."""
    global _models_cache
    if _models_cache:
        return _models_cache
    try:
        r = await client.get(base + "/models", headers={"Authorization": f"Bearer {key}"})
        ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
    except Exception:  # noqa: BLE001
        return list(_PREFERRED)
    chat = [i for i in ids if not any(x in i.lower() for x in ("whisper", "tts", "guard", "embed", "orpheus", "playai"))]
    ordered = [m for m in _PREFERRED if m in chat] + [m for m in chat if m not in _PREFERRED]
    _models_cache = ordered or list(_PREFERRED)
    return _models_cache


PRIMER = (
    "BACKGROUND (well-established general knowledge about Mangaluru, use it confidently): "
    "Mangaluru (Mangalore) is the main port city of Dakshina Kannada in coastal Karnataka, on the Arabian Sea, about 350 km west of Bengaluru "
    "(around 12.87 N, 74.84 E). The Netravati and Gurpura rivers meet the sea here; the Netravati estuary and Bengre and Tannirbhavi are on the river-sea edge. "
    "Getting there: Mangaluru International Airport (IXE) at Bajpe is about 20 km north of the city. Rail: Mangaluru Central (Hampankatta side) and Mangaluru Junction (Kankanady); "
    "Konkan Railway and the Bengaluru line via Sakleshpur and Subramanya. Bus: KSRTC and private stands at Lalbagh/State Bank (KSRTC at Kavoor/Bejai area, private buses at Service Bus Stand near State Bank). "
    "Getting around: city buses, auto-rickshaws (insist on the meter or agree the fare first), app cabs, and the ferry-like launches in the estuary. "
    "People and language: Tulu, Kannada, Konkani, Beary and English are all spoken; Hindi is understood in tourist areas. "
    "Food: neer dosa, kori rotti with chicken ghee roast, fish thali (bangude/pomfret/mackerel fry, anjal), prawn gassi, pork and bamboo-shoot dishes in some homes, "
    "buns (banana puri), Mangalorean cucumber (southekai) dishes, kadubu, patrode, Pabba's and Ideal ice cream (gadbad), tender-coconut and sugarcane juice, filter coffee. "
    "Famous eating areas: Hampankatta, Balmatta, Kadri, Bunder (near the old port) for seafood and wholesale markets. "
    "Sights: Kadri Manjunath Temple, Kudroli Gokarnath Temple, Mangaladevi Temple, Sri Venkataramana Temple, Our Lady of Rosary and St. Aloysius Chapel (famous paintings), "
    "Milagres Church, Jama Masjid and Zeenath Baksh Mosque in Bunder, Sultan Battery watchtower at Boloor, Tannirbhavi and Panambur beaches, Someshwara, Ullal and Surathkal beaches, "
    "Pilikula Nisargadhama (biological park, planetarium, Tulu village), Mangaluru Lighthouse, Kadri Park. "
    "Day trips: Udupi Krishna Temple and Malpe/St Mary's Island (about 60 km), Manipal, Dharmasthala (75 km), Kukke Subramanya, Kollur Mookambika, Agumbe, Karkala, Moodabidri (Thousand Pillar Basadi), Gokarna (3-4 hours north). "
    "Festivals and culture: Kambala (buffalo race, winter), Yakshagana, Pilivesha/tiger dance during Dasara and Krishna Janmashtami, Mangaluru Dasara, Bhuta Kola spirit worship, Nagamandala, Christmas and Monti Fest. "
    "Climate: tropical, humid. June to September is heavy monsoon (many beaches are closed to swimming then); October to February is the pleasant season; March to May is hot. Sunset is around 6 pm in winter and 6:45 pm in summer. "
    "Etiquette: cover shoulders and knees at temples; men may need to remove shirts in some temples (Kadri, Kudroli rules vary: check at the door); remove footwear; ask before photographing people. "
    "Safety: Mangaluru is generally safe; avoid swimming at beaches that are unguarded, especially in monsoon and after dark; keep valuables close in crowded bus stands."
)

class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class GuideChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    language: str = "en"
    history: list[Turn] = Field(default_factory=list, max_length=12)
    spoken: bool = False          # reply will be read aloud: keep it short and natural
    lat: float | None = None
    lng: float | None = None


class GuidePlaceOut(BaseModel):
    place_id: str | None
    name: str
    category: str


class GuideChatOut(BaseModel):
    reply: str
    mode: Literal["llm", "extractive"]
    places: list[GuidePlaceOut]
    note: str | None = None


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1]


def _val(x) -> str:
    return str(getattr(x, "value", x)) if x is not None else ""


def _score(place, toks: list[str]) -> float:
    name = (place.name or "").lower()
    cat = (place.category or "").lower()
    tags = " ".join(place.tags or []).lower()
    desc = ((place.description or "") + " " + (place.wiki_summary or "")).lower()
    score = 0.0
    for t in toks:
        if t in name:
            score += 5
        if t in cat:
            score += 3
        if t in tags:
            score += 2.5
        if t in desc:
            score += 1
    return score


def _facts(place) -> str:
    bits = [f"{place.name} — {place.category}"]
    bits.append("OPEN STATUS NOW: " + open_info(place, _PARSER).label)
    if place.tags:
        bits.append("tags: " + ", ".join(place.tags[:6]))
    bits.append(f"price: {_val(place.price_band)} (~₹{int(place.estimated_cost or 0)})")
    if place.best_time:
        bits.append(f"best time: {place.best_time}")
    bits.append(f"crowd: {_val(place.crowd_level)}; energy: {_val(place.energy_requirement)}; typical visit: {place.dwell_time_typical_minutes} min")
    flags = []
    for label, v in (("family friendly", place.family_friendly), ("kid friendly", place.kid_friendly), ("food available", place.food_available),
                     ("parking", place.parking), ("washrooms", place.washrooms), ("photography allowed", place.photography_allowed)):
        if v is True:
            flags.append(label)
    if flags:
        bits.append("has: " + ", ".join(flags))
    if place.etiquette_tag:
        bits.append(f"etiquette: {place.etiquette_tag}")
    text = (place.description or place.wiki_summary or "").strip()
    if text:
        bits.append("about: " + text[:320])
    return " | ".join(bits)


def _extractive(matches, lang: str) -> str:
    if not matches:
        return ("I don't have a specific GroundZero record for that, and the AI guide is offline right now. "
                "Mangaluru basics: a port city on the Arabian Sea in coastal Karnataka, best visited October–February; "
                "famous for seafood, ghee roast and neer dosa, and beaches like Panambur and Tannirbhavi. "
                "Try asking about a beach, temple, food or a place name.")
    lines = ["Here is what GroundZero has on that:"]
    for p in matches[:4]:
        extra = f" Best time: {p.best_time}." if p.best_time else ""
        blurb = (p.description or p.wiki_summary or "").strip()
        blurb = (" " + blurb[:160].rstrip() + ("…" if len(blurb) > 160 else "")) if blurb else ""
        lines.append(f"• {p.name} ({p.category}).{extra}{blurb}")
    return "\n".join(lines)


async def _groq(system: str, history: list[Turn], message: str) -> tuple[str | None, str | None]:
    global _last_error
    key, _src = find_groq_key()
    if not key:
        _last_error = "no key found"
        return None, "no_key"
    base = get_settings().groq_base_url.rstrip("/")
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": t.role, "content": t.content} for t in history[-8:]]
    msgs.append({"role": "user", "content": message})
    last_err = "network"
    async with httpx.AsyncClient(timeout=30) as client:
        models = await _available_models(client, key, base)
        preferred = get_settings().groq_model
        order = [preferred, *[m for m in models if m != preferred]][:4]
        for model in order:
            for attempt in (1, 2):
                try:
                    r = await client.post(
                        base + "/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={"model": model, "messages": msgs, "temperature": 0.6, "max_tokens": 600},
                    )
                except httpx.HTTPError as exc:
                    last_err = "network"
                    _last_error = f"network: {exc.__class__.__name__} {exc}"
                    logger.warning("Groq network error: %s", _last_error)
                    break
                if r.status_code in (401, 403):
                    _last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                    logger.warning("Groq rejected key: %s", _last_error)
                    return None, "http_401"
                if r.status_code == 429 or r.status_code >= 500:
                    last_err = f"http_{r.status_code}"
                    _last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                    if attempt == 1:
                        await asyncio.sleep(1.2)
                        continue
                    break
                if r.status_code >= 400:
                    last_err = f"http_{r.status_code}"
                    _last_error = f"HTTP {r.status_code} ({model}): {r.text[:200]}"
                    logger.warning("Groq %s", _last_error)
                    break
                try:
                    got = (r.json()["choices"][0]["message"]["content"] or "").strip()
                except (KeyError, IndexError, ValueError):
                    last_err = "bad_response"
                    break
                if got:
                    _last_error = None
                    return got, None
                break
    return None, last_err


@router.get("/status")
async def status(probe: bool = False) -> dict:
    """Developer check: is the AI wired up? Add ?probe=true to make a real test call."""
    key, src = find_groq_key()
    out = {"llm_configured": bool(key), "key_source": src,
           "key_hint": (key[:4] + "…" + key[-3:]) if key and len(key) > 10 else None, "last_error": _last_error}
    if probe and key:
        reply, err = await _groq("Reply with the single word: ready", [], "ping")
        out.update(probe_ok=bool(reply), probe_reply=reply, probe_error=err, last_error=_last_error)
    return out


class KeyIn(BaseModel):
    key: str = Field(min_length=10, max_length=200)


@router.post("/key")
async def set_key(body: KeyIn, user: User = Depends(get_current_user)) -> dict:
    """One-time setup from inside the app: verify the Groq key against Groq,
    then keep it for this run and write it to the backend .env so it survives
    restarts. For local development use."""
    key = _clean(body.key) or ""
    if not key.startswith("gsk_"):
        return {"ok": False, "detail": "That doesn't look like a Groq key (it starts with gsk_)."}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(get_settings().groq_base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError:
        return {"ok": False, "detail": "Couldn't reach Groq to check the key. Check your internet and try again."}
    if r.status_code in (401, 403):
        return {"ok": False, "detail": "Groq rejected that key. Copy it again from console.groq.com/keys."}
    os.environ["GROQ_API_KEY"] = key
    env = _BASE / ".env"
    try:
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        lines = [l for l in lines if not l.strip().startswith("GROQ_API_KEY")]
        lines.append(f"GROQ_API_KEY={key}")
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        saved = True
    except OSError:
        saved = False
    return {"ok": True, "saved_to_env": saved, "detail": "AI guide connected."}


@router.post("/chat", response_model=GuideChatOut)
async def chat(
    body: GuideChatIn,
    user: User = Depends(get_current_user),
    place_repo: PlaceRepository = Depends(get_place_repository),
) -> GuideChatOut:
    places = await place_repo.list_all()
    # Follow-ups ("what about food there?") need the earlier turns to match.
    context_text = " ".join([t.content for t in body.history[-4:] if t.role == "user"] + [body.message])
    toks = _tokens(context_text)
    scored = sorted(((_score(p, toks), p) for p in places), key=lambda x: x[0], reverse=True)
    top = scored[0][0] if scored else 0
    seen: set[str] = set()
    matches = []
    for sc, p in scored:
        if sc <= 0 or sc < max(2.5, top * 0.35):
            break
        norm = re.sub(r"[^a-z0-9]", "", (p.name or "").lower())
        if norm in seen:
            continue
        seen.add(norm)
        matches.append(p)
        if len(matches) >= 6:
            break
    out_places = [GuidePlaceOut(place_id=p.id, name=p.name, category=p.category) for p in matches[:4]]

    lang = LANGS.get(body.language, "English")
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    # Put open places first; closed ones stay visible (with their status) so the
    # model can say "that one is closed now, try ... instead".
    matches.sort(key=lambda p: open_info(p, _PARSER, now).state == "closed")
    pool = matches
    facts = "\n".join(f"- {_facts(p)}" for p in pool) or "(no specific GroundZero place matched this question)"

    nearby = ""
    if body.lat is not None and body.lng is not None:
        near = sorted(places, key=lambda p: _km(body.lat, body.lng, p.coordinates.latitude, p.coordinates.longitude))
        open_near = [p for p in near if open_info(p, _PARSER, now).state != "closed"][:8]
        nearby = "\nNEAR THE TRAVELLER RIGHT NOW (open or possibly open, closest first):\n" + "\n".join(
            f"- {p.name} ({p.category}), {_km(body.lat, body.lng, p.coordinates.latitude, p.coordinates.longitude):.1f} km, {open_info(p, _PARSER, now).label}"
            for p in open_near
        )

    style = (
        "The reply will be READ ALOUD, so talk the way a friendly local talks: short natural sentences, contractions, no lists, no symbols, "
        "no brackets, at most 70 words. Start with the answer. "
        if body.spoken else
        "Keep it conversational and under 140 words; a short hyphen list is fine, no markdown symbols like ** or #. "
    )
    system = (
        "You are the GroundZero Guide: a warm, very experienced local guide who knows Mangaluru better than anyone. "
        f"Right now it is {now.strftime('%A, %d %B %Y, %I:%M %p')} in Mangaluru. "
        "Answer exactly what was asked, in the first sentence, then add one useful local detail. You can cover anything a great guide would: "
        "places, food, getting around, buses and trains, weather and seasons, culture, festivals, etiquette, history, language, safety, day plans, and general questions. "
        "Never give the same answer to a different question. Never say you are an AI or mention records, data or databases. "
        "Only suggest going somewhere that is open at this time of day. If a place's OPEN STATUS says closed, say so and offer an open alternative. "
        "Prefer the PLACE FACTS and NEAR THE TRAVELLER lists for specific places. For exact prices or timings say they should confirm locally; "
        "never invent phone numbers, addresses or exact fares. If you truly don't know, say so in a few words and give the nearest useful tip. "
        + style +
        f"Reply in {lang}.\n\n{PRIMER}\n\nPLACE FACTS:\n{facts}{nearby}"
    )
    reply, err = await _groq(system, body.history, body.message)
    if reply:
        low = reply.lower()
        mentioned = []
        seen_names: set[str] = set()
        for p in places:
            nm = (p.name or "").strip()
            if len(nm) > 3 and nm.lower() in low and nm.lower() not in seen_names:
                seen_names.add(nm.lower())
                mentioned.append(GuidePlaceOut(place_id=p.id, name=nm, category=p.category))
            if len(mentioned) >= 4:
                break
        return GuideChatOut(reply=reply, mode="llm", places=mentioned)

    from guide.brain import answer as brain_answer

    text, used = brain_answer(body.message, places, now, body.lat, body.lng)
    if used:
        out_places = [GuidePlaceOut(place_id=p.id, name=p.name, category=p.category) for p in used[:4]]
    else:
        out_places = []
    logger.info("Guide answered from its own knowledge (reason=%s)", err)
    return GuideChatOut(reply=text, mode="extractive", places=out_places, note=None)


# ---------------------------------------------------------------------------
# Natural voice (Microsoft neural voices through edge-tts, free, no key)
# ---------------------------------------------------------------------------
_VOICES = {
    "en": "en-IN-NeerjaNeural", "kn": "kn-IN-SapnaNeural", "hi": "hi-IN-SwaraNeural",
    "ta": "ta-IN-PallaviNeural", "te": "te-IN-ShrutiNeural",
}


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    language: str = "en"


def _spoken(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text)
    t = re.sub(r"[*_#`>~|]", "", t)
    t = re.sub(r"^\s*[-•·]\s+", "", t, flags=re.M)
    t = t.replace("₹", "rupees ").replace("&", " and ")
    t = re.sub(r"(\d)\s?km\b", r"\1 kilometres", t)
    t = re.sub(r"\s*\n+\s*", ". ", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return re.sub(r"\s{2,}", " ", t).strip()


@router.post("/speak")
async def speak(body: SpeakIn, user: User = Depends(get_current_user)):
    """Returns MP3 audio of the guide's reply in a natural human voice."""
    from fastapi import HTTPException
    from fastapi.responses import Response

    try:
        import edge_tts
    except ImportError:
        raise HTTPException(501, "Voice not installed on the server (pip install edge-tts).")
    voice = _VOICES.get(body.language, _VOICES["en"])
    try:
        comm = edge_tts.Communicate(_spoken(body.text), voice, rate="-2%", pitch="+0Hz")
        chunks = bytearray()
        async for ch in comm.stream():
            if ch["type"] == "audio":
                chunks.extend(ch["data"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("edge-tts failed: %s", exc)
        raise HTTPException(503, "Voice service is unreachable right now.")
    if not chunks:
        raise HTTPException(503, "Voice service returned no audio.")
    return Response(bytes(chunks), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
