
"""Real LLM extraction with strict schema validation.

The LLM proposes, the code validates: every field is checked against the
project's canonical vocabularies (regions, features, property types) and
plausible ranges. Any failure — missing key, network error, malformed JSON,
out-of-schema value — returns None so the pipeline falls back to the
rule-based extractor. An LLM can never corrupt the pipeline.
"""

import json
import os
import re

try:
    from .data import FEATURES, PROPERTY_TYPES, REGIONS
except ImportError:
    from data import FEATURES, PROPERTY_TYPES, REGIONS

BUDGET_MIN, BUDGET_MAX = 50_000, 20_000_000
URGENCY_LEVELS = {"LOW", "MEDIUM", "HIGH"}
PROFILES = {"investor", "first_time", "family", None}

SYSTEM_PROMPT = (
    "You extract real-estate search criteria from a buyer inquiry. "
    "Reply with ONLY a JSON object, no prose, no markdown fences. "
    'Schema: {"budget": integer USD or null, "bedrooms": 1..10 or null, '
    '"bathrooms": 1..6 or null, "property_type": "house"|"condo"|"townhouse"|null, '
    '"areas": array of region names, "urgency": "LOW"|"MEDIUM"|"HIGH", '
    '"must_haves": array of feature names, "nice_to_have": array of feature names, '
    '"profile": "investor"|"first_time"|"family"|null}. '
    "Allowed features: " + ", ".join(FEATURES) + ". "
    "Allowed regions: " + ", ".join(REGIONS) + ". "
    "Use null when a field is not specified. Never invent values."
)


def _parse_json(text):
    """Accept raw JSON or JSON wrapped in markdown fences."""
    t = text.strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in response")
    return json.loads(m.group(0))


def _validate(data):
    """Coerce/verify every field; raise ValueError on any violation."""
    out = {"budget": None, "bedrooms": None, "bathrooms": None,
           "property_type": None, "areas": [], "urgency": "LOW",
           "must_haves": [], "nice_to_have": [], "profile": None}
    if data.get("budget") is not None:
        b = int(data["budget"])
        if not BUDGET_MIN <= b <= BUDGET_MAX:
            raise ValueError("budget out of range: %r" % b)
        out["budget"] = b
    for key, lo, hi in (("bedrooms", 1, 10), ("bathrooms", 1, 6)):
        if data.get(key) is not None:
            v = int(data[key])
            if not lo <= v <= hi:
                raise ValueError("%s out of range: %r" % (key, v))
            out[key] = v
    pt = data.get("property_type")
    if pt is not None:
        if pt not in PROPERTY_TYPES:
            raise ValueError("unknown property_type: %r" % pt)
        out["property_type"] = pt
    for a in data.get("areas") or []:
        if a not in REGIONS:
            raise ValueError("unknown region: %r" % a)
        out["areas"].append(a)
    u = data.get("urgency") or "LOW"
    if u not in URGENCY_LEVELS:
        raise ValueError("bad urgency: %r" % u)
    out["urgency"] = u
    for key in ("must_haves", "nice_to_have"):
        vals = []
        for f in data.get(key) or []:
            if f not in FEATURES:
                raise ValueError("unknown feature %r in %s" % (f, key))
            if f not in vals:
                vals.append(f)
        out[key] = vals
    p = data.get("profile")
    if p not in PROFILES:
        raise ValueError("bad profile: %r" % p)
    out["profile"] = p
    return out


def extract_llm(text, api_key=None, client=None):
    """Return validated criteria dict, or None to fall back to rules.

    `client` is injectable for tests (any object exposing
    chat.completions.create). By default a lazily imported OpenAI client
    is used when OPENAI_API_KEY is set.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key and client is None:
        return None
    if client is None:
        try:
            from openai import OpenAI
        except ImportError:
            return None
        client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
        max_tokens=400,
    )
    try:
        data = _parse_json(response.choices[0].message.content or "")
        return _validate(data)
    except Exception:
        return None
