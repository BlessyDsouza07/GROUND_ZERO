import hashlib, json, re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import dateparser

def clean(v):
    if v is None:
        return None
    return re.sub(r"\s+", " ", str(v)).strip() or None

def first(v):
    return v[0] if isinstance(v, list) and v else v

def parse_dt(v):
    v = first(v)
    if not v:
        return None
    if isinstance(v, str):
        d = dateparser.parse(v, settings={"RETURN_AS_TIMEZONE_AWARE": True})
        if d:
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
    return None

def parse_location(loc):
    loc = first(loc) or {}
    if isinstance(loc, str):
        return clean(loc), None, None
    addr = loc.get("address") or {}
    if isinstance(addr, str):
        return clean(loc.get("name")), clean(addr), None
    return clean(loc.get("name")), clean(addr.get("streetAddress")), clean(addr.get("addressLocality"))

def mode_and_audience(obj):
    text = json.dumps(obj, ensure_ascii=False).lower()
    mode = "ONLINE" if any(x in text for x in ["online", "virtual", "webinar", "zoom", "google meet"]) else "PHYSICAL"
    if mode == "PHYSICAL" and "hybrid" in text:
        mode = "HYBRID"
    audience = "GENERAL_PUBLIC"
    if any(x in text for x in ["faculty development", "faculty members", "academic leaders", "research scholars", "teaching professionals"]):
        audience = "ACADEMIC"
    if "students" in text and "general public" not in text:
        audience = "STUDENTS"
    eligible = mode in {"PHYSICAL", "HYBRID"} and audience == "GENERAL_PUBLIC"
    return mode, audience, eligible

def iter_event_objects(obj):
    if isinstance(obj, dict):
        t = obj.get("@type")
        if t == "Event" or (isinstance(t, list) and "Event" in t):
            yield obj
        for v in obj.values():
            yield from iter_event_objects(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from iter_event_objects(x)

def parse_jsonld(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for s in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            obj = json.loads(s.string or s.get_text())
        except Exception:
            continue
        for e in iter_event_objects(obj):
            title = clean(e.get("name"))
            if not title:
                continue
            venue, address, city = parse_location(e.get("location"))
            start = parse_dt(e.get("startDate"))
            end = parse_dt(e.get("endDate"))
            source_key = clean(e.get("@id") or e.get("url") or page_url)
            mode, audience, eligible = mode_and_audience(e)
            status = str(e.get("eventStatus") or "").lower()
            status = "CANCELLED" if "cancel" in status else ("POSTPONED" if "postpon" in status else "ACTIVE")
            raw = json.dumps(e, sort_keys=True, ensure_ascii=False)
            out.append({
                "source_event_key": source_key,
                "title": title,
                "description": clean(e.get("description")),
                "start_at": start,
                "end_at": end,
                "venue": venue,
                "address": address,
                "city": city,
                "mode": mode,
                "audience": audience,
                "itinerary_eligible": eligible and status == "ACTIVE",
                "status": status,
                "source_url": urljoin(page_url, clean(e.get("url")) or page_url),
                "raw_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
    return out

def discover_links(html, page_url, base_host):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"])
        p = urlparse(u)
        if p.scheme in {"http", "https"} and p.netloc == base_host:
            txt = clean(a.get_text(" ", strip=True)) or ""
            href = u.lower()
            if any(k in (txt + " " + href) for k in ["event", "events", "conference", "fest", "programme", "seminar", "workshop", "register"]):
                links.append(u)
    return list(dict.fromkeys(links))[:80]
