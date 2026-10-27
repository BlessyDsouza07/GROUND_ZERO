"""HIVE v2 ranking pipeline (deterministic, explainable).

A candidates -> B non-negotiable constraints -> C component scores ->
D itinerary roles / fewer stops -> E MMR diversity -> F grounded explanation.

Honest limits: weights are hand-set defaults, not learned. Nothing here is
a trained model. Feedback is logged (learning.py) so a learned ranker could
be evaluated later against this one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .experience import EXPERIENCES, PlaceKnowledge, classify
from .intent import Intent

IST = ZoneInfo("Asia/Kolkata")

WEIGHTS = {
    "personal_fit": 0.22, "experience": 0.20, "authenticity": 0.14, "novelty": 0.10,
    "context": 0.14, "practical": 0.14, "confidence": 0.06,
}
MODE_WEIGHTS = {
    "surprise": {"personal_fit": 0.10, "novelty": 0.30, "experience": 0.12},
    "slow": {"practical": 0.20, "context": 0.18},
    "less_touristy": {"authenticity": 0.30, "novelty": 0.12, "personal_fit": 0.14},
}
JUNK = ("pharmacy", "charging", "fire station", "petrol", "atm", "police", "hospital", "clinic", "bank")
NON_VEG_HINTS = ("seafood", "non-veg", "non veg", "chicken", "mutton", "fish", "kebab", "biryani", "kori", "steak", "bbq")
VEG_HINTS = ("veg", "udupi", "tiffin", "vegetarian", "sweet", "bakery", "ice_cream", "dessert")
CITY_KMH = 18.0


def km(a_lat, a_lon, b_lat, b_lon) -> float:
    p = math.pi / 180
    x = math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lon - a_lon) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


@dataclass
class Context:
    lat: float
    lon: float
    now: datetime
    minutes: Optional[int] = None
    rain: Optional[bool] = None
    temp_c: Optional[float] = None
    mode: Optional[str] = None
    limit: int = 6
    intent: Intent = field(default_factory=Intent)


@dataclass
class Profile:
    affinities: dict = field(default_factory=dict)     # key -> {weight, confidence, source}
    constraints: dict = field(default_factory=dict)
    visited: set = field(default_factory=set)
    dismissed: set = field(default_factory=set)
    shown_counts: dict = field(default_factory=dict)   # place_id -> times shown (impression only)

    @property
    def cold(self) -> bool:
        return not self.affinities


@dataclass
class Scored:
    k: PlaceKnowledge
    dist_km: float
    travel_min: int
    open_state: str
    open_label: str
    open_source: str
    components: dict
    score: float
    reasons: list = field(default_factory=list)
    caveats: list = field(default_factory=list)
    role: str = "anchor"
    less_touristy_evidence: Optional[str] = None
    hidden_gem: bool = False
    confidence_label: str = "low"


@dataclass
class Result:
    items: list
    dropped: dict
    message: Optional[str]
    understood: list
    relaxed: list = field(default_factory=list)   # always empty: constraints are never silently relaxed


OpenFn = Callable[[object, datetime], tuple]


def _season(now: datetime) -> str:
    m = now.month
    return "monsoon" if 6 <= m <= 9 else ("winter" if m in (11, 12, 1, 2) else "summer")


def _merged_constraints(profile: Profile, ctx: Context) -> dict:
    c = dict(profile.constraints or {})
    it = ctx.intent
    # what the person said *now* adds to (never overrides to looser) saved constraints
    if it.with_kids:
        c["kids"] = True
    if it.budget_per_place is not None:
        c["max_spend_per_place"] = min(it.budget_per_place, c.get("max_spend_per_place") or 10**9)
    if it.diet:
        c["dietary"] = sorted(set((c.get("dietary") or []) + it.diet))
    if it.with_elderly or it.low_energy:
        c["low_energy"] = True
    return c


def hard_filter(places, ctx: Context, profile: Profile, open_fn: OpenFn, wants_stay=False):
    c = _merged_constraints(profile, ctx)
    out, dropped = [], {}

    def drop(why):
        dropped[why] = dropped.get(why, 0) + 1

    excluded = set(c.get("excluded_categories") or [])
    avoid = [a.lower() for a in (c.get("avoid") or [])]
    diet = set(c.get("dietary") or [])
    max_spend = c.get("max_spend_per_place")
    access = set(c.get("accessibility") or [])
    strict_access = bool(c.get("accessibility_strict"))
    season = _season(ctx.now)
    for p in places:
        pid = str(p.id)
        if getattr(p, "temporarily_unavailable", False) or getattr(p, "verification_status", "verified") == "pending":
            drop("unavailable"); continue
        name = (p.name or "").lower()
        if p.category == "uncategorized" or any(j in name for j in JUNK):
            drop("not a visitor place"); continue
        if pid in profile.visited:
            drop("already visited"); continue
        if pid in profile.dismissed:
            drop("you said not for you"); continue
        if p.category in excluded or any(a in name or a in p.category for a in avoid):
            drop("excluded by you"); continue
        k = classify(p, ctx.now)
        if k.role == "utility" and not (wants_stay and p.category == "lodging"):
            drop("utility place"); continue
        if wants_stay and p.category != "lodging":
            drop("not a stay"); continue
        st, src, label = open_fn(p, ctx.now)
        if st == "closed":
            drop("closed now"); continue
        late = ctx.now.hour >= 21 or ctx.now.hour < 5
        if st == "unknown" and late and p.category != "lodging":
            drop("hours unknown late at night"); continue
        ev = k.evidence
        if max_spend is not None and ev.estimated_cost is not None and ev.estimated_cost > max_spend:
            drop("over budget"); continue
        if max_spend is not None and max_spend <= 300 and ev.price_band == "premium":
            drop("over budget"); continue
        if "wheelchair" in access:
            if ev.wheelchair is False:
                drop("not wheelchair accessible"); continue
            if ev.wheelchair is None and strict_access:
                drop("accessibility unconfirmed"); continue
        if c.get("kids") and ev.kid_friendly is False:
            drop("not for children"); continue
        if diet and k.role == "food":
            tags = " ".join(t.lower() for t in p.tags) + " " + name + " " + p.category
            if diet & {"veg", "jain", "vegan"}:
                if any(h in tags for h in NON_VEG_HINTS) or not any(h in tags for h in VEG_HINTS):
                    drop("diet not confirmed"); continue
            if "halal" in diet and "halal" not in tags and "muslim" not in tags:
                drop("diet not confirmed"); continue
        if season == "monsoon" and ev.tide_dependent and ctx.rain:
            drop("unsafe in rough monsoon sea"); continue
        if ctx.rain and ev.outdoor and k.role != "food" and (ev.energy == "high"):
            drop("outdoor effort in rain"); continue
        if c.get("low_energy") and ev.energy == "high":
            drop("too strenuous"); continue
        d = km(ctx.lat, ctx.lon, k.lat, k.lon)
        tmin = int(d / CITY_KMH * 60 * 1.3) + 2     # 1.3 = road detour factor
        if ctx.minutes is not None:
            if tmin * 2 + min(ev.dwell_minutes, 40) > ctx.minutes + 15 and ctx.minutes < 240:
                drop("too far for your time"); continue
        elif d > 25:
            drop("too far"); continue
        out.append((p, k, d, tmin, st, src, label))
    return out, dropped


def _affinity(profile: Profile, k: PlaceKnowledge) -> tuple[float, float]:
    """-> (score 0..1, confidence 0..1)."""
    if profile.cold:
        return 0.5, 0.0
    tot, w_sum, conf = 0.0, 0.0, 0.0
    for key, s in k.experiences.items():
        a = profile.affinities.get(f"exp:{key}")
        if a:
            tot += s * a["weight"]; w_sum += s; conf = max(conf, a.get("confidence", 0.3))
    a = profile.affinities.get(f"cat:{k.category}")
    if a:
        tot += a["weight"]; w_sum += 1; conf = max(conf, a.get("confidence", 0.3))
    if w_sum == 0:
        return 0.5, 0.1
    raw = tot / w_sum                                  # -1..1
    return round((raw + 1) / 2, 3), conf


def score_all(rows, ctx: Context, profile: Profile):
    mode = ctx.mode or ctx.intent.mode
    w = dict(WEIGHTS)
    w.update(MODE_WEIGHTS.get(mode or "", {}))
    s = sum(w.values())
    w = {k: v / s for k, v in w.items()}
    visited_cats: dict = {}
    scored = []
    season = _season(ctx.now)
    hour = ctx.now.hour
    for p, k, d, tmin, st, src, label in rows:
        ev = k.evidence
        comp = {}
        fit, fconf = _affinity(profile, k)
        comp["personal_fit"] = fit
        want = ctx.intent.interests
        comp["experience"] = (max([k.experiences.get(i, 0) for i in want]) if want
                              else (max(k.experiences.values()) * 0.6 if k.experiences else 0.2))
        comp["authenticity"] = (ev.authenticity * (0.6 if ev.authenticity_basis == "heuristic" else 1.0)
                                if ev.authenticity is not None else 0.35)
        if ev.commercialisation is not None:
            comp["authenticity"] = max(0.0, comp["authenticity"] - 0.3 * ev.commercialisation)
        shown = profile.shown_counts.get(str(p.id), 0)
        comp["novelty"] = max(0.1, 1.0 - 0.15 * shown)
        # context
        cx = 0.5
        bt = (ev.best_time or "").lower()
        if bt in ("sunset", "evening") and 16 <= hour <= 19: cx += 0.3
        if bt in ("sunrise", "morning") and 5 <= hour <= 10: cx += 0.3
        if ctx.rain and ev.outdoor: cx -= 0.3
        if ctx.rain and not ev.outdoor: cx += 0.15
        if ctx.temp_c and ctx.temp_c >= 33 and ev.outdoor and 11 <= hour <= 15: cx -= 0.25
        if season not in ev.seasons and ev.seasons: cx -= 0.2
        if ctx.intent.avoid_crowds: cx += 0.25 if ev.crowd == "low" else (-0.3 if ev.crowd == "high" else 0)
        if src == "listed" and st == "open": cx += 0.1
        comp["context"] = max(0.0, min(1.0, cx))
        # practical: near + fits
        comp["practical"] = max(0.0, 1.0 - d / 12.0)
        if ctx.intent.low_energy or mode == "slow":
            comp["practical"] = comp["practical"] * 0.6 + (0.4 if ev.energy == "low" else 0.1)
        comp["confidence"] = round(ev.verification * 0.6 + ev.completeness * 0.4, 3)
        total = sum(w[c] * comp[c] for c in w)
        sc = Scored(k, round(d, 2), tmin, st, label, src, {a: round(b, 3) for a, b in comp.items()}, round(total, 4), role=k.role)
        _explain(sc, p, ctx, profile, fconf)
        scored.append(sc)
    return scored


def _explain(sc: Scored, p, ctx: Context, profile: Profile, fconf: float):
    k, ev, c = sc.k, sc.k.evidence, sc.components
    r, cav = sc.reasons, sc.caveats
    want = ctx.intent.interests
    for i in want:
        if k.experiences.get(i, 0) >= 0.5:
            r.append(f"Matches what you asked for: {EXPERIENCES[i].lower()}")
    if not profile.cold and c["personal_fit"] >= 0.65 and fconf >= 0.3:
        top = max(k.experiences, key=k.experiences.get, default=None)
        if top:
            r.append(f"You've leaned towards {EXPERIENCES[top].lower()} before")
    if sc.open_state == "open":
        r.append(sc.open_label)
    if sc.travel_min <= 10:
        r.append(f"About {max(sc.travel_min, 1)} min away")
    if ev.crowd == "low":
        r.append("Usually quiet")
    # evidence-backed "less touristy"
    if ev.authenticity_basis in ("community", "local_listing") and (ev.commercialisation or 0) <= 0.4:
        sc.less_touristy_evidence = ("Suggested by locals who contributed it" if ev.authenticity_basis == "community"
                                     else "Appears in local listings")
        sc.hidden_gem = True
        r.append(sc.less_touristy_evidence)
    elif not ev.commercial_signals and (ev.commercialisation or 0) <= 0.35 and ev.authenticity_basis != "none":
        sc.less_touristy_evidence = "No tourist-oriented or promotion signals on record (not proof of being a local favourite)"
    if ev.etiquette:
        cav.append(ev.etiquette)
    if sc.open_source != "listed":
        cav.append("Opening hours are typical for this kind of place, not confirmed")
    if ev.wheelchair is None and "wheelchair" in set((profile.constraints or {}).get("accessibility") or []):
        cav.append("Wheelchair access is not confirmed")
    if ev.kid_friendly is None and ctx.intent.with_kids:
        cav.append("Child-friendliness is not confirmed")
    if _season(ctx.now) == "monsoon" and k.category in ("beach",):
        cav.append("Monsoon sea is dangerous: stay out of the water and keep to the shore")
    if ctx.temp_c and ctx.temp_c >= 33 and ev.outdoor:
        cav.append("Hot out. Carry water and shade up")
    if ev.crowd is None:
        cav.append("Crowd level unknown")
    conf = c["confidence"]
    sc.confidence_label = "good" if conf >= 0.55 else ("fair" if conf >= 0.4 else "low")
    if not r:
        r.append("A solid nearby option that fits your constraints")


def _sim(a: Scored, b: Scored) -> float:
    ka, kb = a.k, b.k
    keys = set(ka.experiences) | set(kb.experiences)
    dot = sum(ka.experiences.get(x, 0) * kb.experiences.get(x, 0) for x in keys)
    na = math.sqrt(sum(v * v for v in ka.experiences.values())) or 1
    nb = math.sqrt(sum(v * v for v in kb.experiences.values())) or 1
    s = dot / (na * nb)
    if ka.category == kb.category: s = min(1.0, s + 0.3)
    if km(ka.lat, ka.lon, kb.lat, kb.lon) < 0.3: s = min(1.0, s + 0.2)
    return s


def mmr(scored: list, n: int, lam: float = 0.7) -> list:
    pool = sorted(scored, key=lambda s: -s.score)[:60]
    picked: list = []
    while pool and len(picked) < n:
        best, best_v = None, -9
        for s in pool:
            red = max((_sim(s, p) for p in picked), default=0.0)
            v = lam * s.score - (1 - lam) * red
            if v > best_v: best, best_v = s, v
        picked.append(best); pool.remove(best)
    return picked


def assign_roles(items: list, ctx: Context) -> list:
    """Stage D: a varied plan, not N copies of the same thing. Fewer stops
    are fine when the time budget or candidates are thin."""
    budget = ctx.minutes
    if budget is None:
        return items
    out, used = [], 0
    for s in items:
        cost = s.travel_min + min(s.k.evidence.dwell_minutes, 60)
        if used + cost > budget and out:
            continue
        out.append(s); used += cost
    cats = {}
    for s in out:
        cats[s.k.role] = cats.get(s.k.role, 0) + 1
    return out


def order_route(items: list, ctx: Context) -> list:
    rem, cur, route = list(items), (ctx.lat, ctx.lon), []
    while rem:
        nxt = min(rem, key=lambda s: km(cur[0], cur[1], s.k.lat, s.k.lon))
        route.append(nxt); rem.remove(nxt); cur = (nxt.k.lat, nxt.k.lon)
    return route


def rank(places, ctx: Context, profile: Profile, open_fn: OpenFn) -> Result:
    intent = ctx.intent
    rows, dropped = hard_filter(places, ctx, profile, open_fn, wants_stay=intent.wants_stay)
    mode = ctx.mode or intent.mode
    if mode == "slow":
        ctx = Context(**{**ctx.__dict__, "limit": min(ctx.limit, 3)})
    scored = score_all(rows, ctx, profile)
    if mode == "less_touristy":
        keep = [s for s in scored if s.less_touristy_evidence or s.k.evidence.commercialisation is None or s.k.evidence.commercialisation <= 0.35]
        dropped["tourist-oriented signals"] = len(scored) - len(keep)
        scored = keep
    picks = mmr(scored, ctx.limit)
    if mode == "surprise" and scored:
        # one deliberate wildcard from outside the usual pattern
        top_ids = {s.k.place_id for s in picks}
        wild = [s for s in scored if s.k.place_id not in top_ids and s.components["novelty"] >= 0.8]
        if wild:
            w = max(wild, key=lambda s: s.components["authenticity"] + s.components["practical"])
            w.role = "wildcard"; w.reasons.insert(0, "Wildcard: outside your usual pattern")
            picks = picks[:-1] + [w] if len(picks) >= ctx.limit else picks + [w]
    picks = assign_roles(picks, ctx)
    msg = None
    if not picks:
        top = sorted(dropped.items(), key=lambda kv: -kv[1])[:3]
        msg = ("Nothing fits all of your conditions right now. I haven't loosened them. "
               "Main reasons: " + ", ".join(f"{n} ({why})" for why, n in top) + ".")
    elif len(picks) < min(3, ctx.limit):
        msg = "Only a few places fit all your conditions, so that's all I'm showing."
    return Result(items=picks, dropped=dropped, message=msg, understood=list(intent.recognised))
