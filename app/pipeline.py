
"""Lead qualification and listing matching pipeline (v2).

Extraction runs rule-based offline; an LLM extractor can be plugged in via
extract_llm(). Scoring is explainable: every match ships human-readable reasons.
"""

import math
import os
import re

try:
    from .data import FEATURES, PROPERTY_TYPES, REGIONS, feature_label
    from .generator import CANDIDATE_CAP
except ImportError:
    # скриптовый запуск (streamlit run app/ui.py) — пакет не виден
    from data import FEATURES, PROPERTY_TYPES, REGIONS, feature_label
    from generator import CANDIDATE_CAP


MUST_MARKERS = re.compile(r"\b(need|needs|must|require|requires|have to)\b")
CLAUSE_SPLIT = re.compile(r"[.!?;]|,\s*(?=want|would like|would love|prefer|ideally)")

FEATURE_ALIASES = {
    "good_schools": ["good school", "good schools", "school district", "top schools", "schools"],
    "yard": ["yard", "backyard", "garden"],
    "family_friendly": ["family friendly", "family-friendly", "for the kids", "kids", "family"],
    "quiet_street": ["quiet street", "quiet area", "quiet neighborhood", "quiet"],
    "pool": ["pool", "swimming"],
    "views": ["views", "view", "scenic"],
    "walkable": ["walkable", "walking distance", "walk score"],
    "modern": ["modern", "new construction", "newly built", "renovated", "updated", "new build"],
    "affordable": ["affordable", "budget-friendly", "starter", "cheap", "value"],
    "office_space": ["home office", "office", "study", "den"],
    "waterfront": ["waterfront", "water front", "lakefront", "lake", "river"],
    "garage": ["garage", "carport", "parking"],
}

# hard-plausible budget range; anything outside is a parsing artifact
BUDGET_MIN, BUDGET_MAX = 50_000, 20_000_000

TIER_HOT_MIN = 75
TIER_WARM_MIN = 55
LOW_URGENCY_CAP = 72


# ---------------------------------------------------------------- extraction

def _parse_budget(text):
    t = text.lower()
    found = []
    for num, suffix in re.findall(r"\$\s*([\d,]+(?:\.\d+)?)\s*(k|m|million)?\b", t):
        found.append((num, suffix))
    for num, suffix in re.findall(
            r"([\d,]+(?:\.\d+)?)\s*(million|millions|k)\b", t):
        found.append((num, suffix))
    for num in re.findall(
            r"budget(?:\s+(?:around|of|up to|max|under|about|no more than))?\s+\$?([\d,]+(?:\.\d+)?)\b", t):
        found.append((num, ""))
    best = None
    for num, suffix in found:
        value = float(num.replace(",", ""))
        if suffix in ("k",):
            value *= 1_000
        elif suffix in ("m", "million", "millions"):
            value *= 1_000_000
        if BUDGET_MIN <= value <= BUDGET_MAX:
            best = max(best or 0, int(value))
    return best


def _parse_bedrooms(text):
    m = re.search(r"(\d+)\s*\+?\s*bed(?:rooms?|s)?\b", text.lower())
    if not m:
        m = re.search(r"(\d+)\s*(?:br|brs)\b", text.lower())
    if not m:
        return None
    value = int(m.group(1))
    return value if 0 < value <= 10 else None


def _parse_bathrooms(text):
    m = re.search(r"(\d+)\s*(?:baths?|bathrooms?)\b", text.lower())
    return int(m.group(1)) if m else None


def _parse_property_type(text):
    t = text.lower()
    if re.search(r"\bcondos?\b", t):
        return "condo"
    if re.search(r"\btownh(?:ouse|ome)s?\b", t):
        return "townhouse"
    if re.search(r"\bhouses?\b", t):
        return "house"
    return None


def _parse_areas(text):
    t = text.lower()
    return [r for r in REGIONS if r.lower() in t]


def _parse_urgency(text):
    t = text.lower()
    if re.search(r"\b(not urgent|no rush|flexible|whenever|eventually)\b", t):
        return "LOW"
    if re.search(r"\b(asap|urgent|immediately|this week|next week)\b", t):
        return "HIGH"
    m = re.search(r"within\s+(\d+)\s*(day|week|month)s?", t)
    if m:
        return "HIGH" if m.group(2) in ("day", "week") else "MEDIUM"
    if re.search(r"\b(soon|quickly|fast)\b", t):
        return "MEDIUM"
    return "LOW"


def _parse_profile(text):
    t = text.lower()
    if re.search(r"rent (it )?out|rental|investment|investor|cap rate|cash flow", t):
        return "investor"
    if re.search(r"first[- ]time", t):
        return "first_time"
    if re.search(r"relocat|family|kids|school", t):
        return "family"
    return None


def _split_features(text):
    """Split text into clauses and classify features as must-have vs nice-to-have.

    Conjunctions ('and') do not reset polarity inside a clause; a clause is a
    must only when it carries an explicit must-marker.
    """
    clauses = CLAUSE_SPLIT.split(text.lower())
    must, soft = [], []
    for clause in clauses:
        feats = [feat for feat, aliases in FEATURE_ALIASES.items()
                 if any(re.search(r"\b" + re.escape(a) + r"\b", clause)
                        for a in aliases)]
        is_must = bool(MUST_MARKERS.search(clause))
        for f in feats:
            (must if is_must else soft).append(f)
    return list(dict.fromkeys(must)), list(dict.fromkeys(soft))


def extract_offline(text):
    must, soft = _split_features(text)
    return {
        "budget": _parse_budget(text),
        "bedrooms": _parse_bedrooms(text),
        "bathrooms": _parse_bathrooms(text),
        "property_type": _parse_property_type(text),
        "areas": _parse_areas(text),
        "urgency": _parse_urgency(text),
        "must_haves": must,
        "nice_to_have": soft,
        "profile": _parse_profile(text),
    }


def extract_llm(text, api_key=None):
    """LLM extractor hook. Returns None when unavailable -> offline fallback."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    return None  # plug the model call here; offline path stays the fallback


# ------------------------------------------------------------------ scoring

def qualify_lead(c):
    """Qualification score with an explainable, hand-tuned component model.

    A lead without any timeline can never be HOT: at LOW urgency the score is
    hard-capped, because 'no rush' must not outweigh budget + bedrooms.
    """
    score = 28.0
    if c["budget"]:
        score += 24
    if c["bedrooms"]:
        score += 13
    if c["areas"]:
        score += 10
    score += min(20, 5 * len(c["must_haves"]))
    score += min(15, 4 * len(c["nice_to_have"]))
    if c["urgency"] == "MEDIUM":
        score += 3
    elif c["urgency"] == "HIGH":
        score += 6
    if c["profile"] == "investor":
        score -= 8
    if c["urgency"] == "LOW":
        score = min(score, LOW_URGENCY_CAP)
    score = int(round(max(0, min(100, score))))
    if score >= TIER_HOT_MIN:
        tier = "HOT"
    elif score >= TIER_WARM_MIN:
        tier = "WARM"
    else:
        tier = "COLD"
    return score, tier


def _matching_features(listing, criteria):
    wanted = list(criteria.get("must_haves", [])) + list(criteria.get("nice_to_have", []))
    return [f for f in dict.fromkeys(wanted) if f in listing["features"]]


def score_listing(listing, criteria):
    """Return (score 0..100, reasons as (icon, text) pairs)."""
    score, reasons = 25.0, []
    budget = criteria.get("budget")
    if budget:
        if listing["price"] <= budget:
            score += 25
            reasons.append(("✅", "price ${:,.0f} fits budget (≤ ${:,.0f})".format(
                listing["price"], budget)))
        elif listing["price"] <= budget * 1.05:
            score += 10
            reasons.append(("⚠️", "price ${:,.0f} slightly above budget (${:,.0f}) — flag for agent".format(
                listing["price"], budget)))
    if criteria.get("bedrooms") and listing["beds"] >= criteria["bedrooms"]:
        score += 15
        reasons.append(("✅", "{} BR matches request".format(listing["beds"])))
    if criteria.get("areas") and listing["region"] in criteria["areas"]:
        score += 22
        reasons.append(("✅", "located in requested area ({})".format(listing["region"])))
    if criteria.get("property_type") and listing["property_type"] == criteria["property_type"]:
        score += 10
        reasons.append(("✅", "property type matches ({})".format(listing["property_type"])))
    matched = _matching_features(listing, criteria)
    if matched:
        score += 8 * len(matched)
        reasons.append(("✅", "matches: " + ", ".join(feature_label(f) for f in matched)))
    for f in criteria.get("must_haves", []):
        if f not in listing["features"]:
            score -= 12
            reasons.append(("⚠️", "missing must-have: " + feature_label(f)))
    return max(0, min(100, score)), reasons


def _summary(c):
    parts = []
    if c["bedrooms"]:
        parts.append("{}BR".format(c["bedrooms"]))
    if c["budget"]:
        parts.append("budget ≤ ${:,.0f}".format(c["budget"]))
    if c["areas"]:
        parts.append(", ".join(a.lower() for a in c["areas"]))
    musts = [feature_label(f) for f in c["must_haves"]]
    softs = [feature_label(f) for f in c["nice_to_have"]]
    if musts:
        parts.append("must: " + ", ".join(musts))
    if softs:
        parts.append("wants: " + ", ".join(softs))
    return "Buyer: " + (", ".join(parts) if parts else "no clear criteria detected")


# ------------------------------------------------------------------ pipeline

def process_lead(text, store):
    if not (text or "").strip():
        raise ValueError("empty inquiry")
    llm_result = extract_llm(text)
    criteria = llm_result or extract_offline(text)
    mode = "llm" if llm_result else "offline-fallback"
    score, tier = qualify_lead(criteria)
    candidates, total, capped = store.search(criteria)
    ranked = []
    for l in candidates:
        s, reasons = score_listing(l, criteria)
        ranked.append((s, l, reasons))
    ranked.sort(key=lambda t: (-t[0], t[1]["id"]))
    top = ranked[:3]

    notes = []
    if total == 0:
        notes.append(
            "No listings passed the hard filters out of {:,} screened — consider relaxing "
            "budget, bedrooms or property type.".format(store.size))
    elif total <= 3:
        notes.append(
            "Only {} of {:,} listings passed the hard filters — inventory is tight.".format(
                total, store.size))
    if capped:
        notes.append(
            "Match pool exceeded {:,} candidates — ranking the best slice only.".format(
                CANDIDATE_CAP))
    unsatisfied = None
    if criteria["must_haves"] and top:
        for _, l, _ in top:
            missing = [f for f in criteria["must_haves"] if f not in l["features"]]
            if unsatisfied is None:
                unsatisfied = set(missing)
            else:
                unsatisfied &= set(missing)
    if unsatisfied:
        notes.append(
            "No candidate satisfies all must-haves: " +
            ", ".join(feature_label(f) for f in sorted(unsatisfied)))

    matches = []
    for s, l, reasons in top:
        matches.append({
            "id": l["id"], "name": l["name"], "region": l["region"], "city": l["city"],
            "property_type": l["property_type"], "price": l["price"],
            "beds": l["beds"], "baths": l["baths"], "sqft": l["sqft"],
            "features": l["features"],
            "score": round(float(s), 1),
            "reasons": [{"icon": i, "text": t} for i, t in reasons],
        })

    return {
        "score": score,
        "tier": tier,
        "urgency": criteria["urgency"],
        "summary": _summary(criteria),
        "pipeline_mode": mode,
        "extracted": criteria,
        "matches": matches,
        "agent_notes": notes,
        "listings_screened": store.size,
        "listings_matched": total,
        "candidates_capped": capped,
    }


SAMPLES = {
    "Relocating family (house, schools)":
        "We are relocating from Denver and looking for a 3 bedroom house under $520k. "
        "We need a good school district and a yard for the kids, prefer South Congress area. "
        "Hoping to move within 2 months.",
    "First-time buyer (condo, downtown)":
        "First time buyer here. Budget around 380000. Looking for a 2 bed condo downtown, "
        "want something modern and walkable to coffee shops. Flexible on timing.",
    "Investor (budget, rental)":
        "Looking for an affordable starter property I can rent out. Max 300k, 2 bedrooms minimum. "
        "Quiet area preferred. Not urgent.",
    "Luxury buyer (views, pool)":
        "Relocating for work, need something soon. 4+ bedrooms, pool and views would be great, "
        "budget up to 950k, want good schools for the kids.",
}
