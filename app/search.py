
"""Hybrid semantic rerank: TF-IDF pre-score (from the store) narrows the
pool, a local sentence-transformers model re-orders the shortlist by meaning.

Design rules:
- fully local, no API keys; sentence-transformers is an OPTIONAL dependency;
- `rerank` returns None (and the pipeline stays on TF-IDF) whenever the
  backend is unavailable or anything fails — the flag on the lead card is
  always honest, because it is set from the actual result, not intent.
"""

import importlib.util
import math

_MODEL = None
_EMBED_CACHE = {}
_CACHE_LIMIT = 20000


def backend_name():
    return "embeddings+tfidf" if _MODEL is not None else "tfidf"


def available():
    """True only if the package is actually importable (not just declared)."""
    try:
        __import__("sentence_transformers")
        return True
    except Exception:
        return False


def _load():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    from sentence_transformers import SentenceTransformer
    _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _listing_vec(model, listing):
    key = listing["id"]
    vec = _EMBED_CACHE.get(key)
    if vec is None:
        if len(_EMBED_CACHE) >= _CACHE_LIMIT:
            _EMBED_CACHE.clear()
        vec = model.encode([listing["description"]], normalize_embeddings=True)[0]
        _EMBED_CACHE[key] = vec
    return vec


def _cos(a, b):
    d = float(sum(x * y for x, y in zip(a, b)))
    return max(-1.0, min(1.0, d))


def rerank(query, listings, base_scores, weight=0.35):
    """Blend base scores with semantic similarity. Returns new scores or None."""
    if not listings:
        return None
    if not available():
        return None
    try:
        model = _load()
    except Exception:
        return None
    try:
        qv = model.encode([query], normalize_embeddings=True)[0]
        sims = [_cos(qv, _listing_vec(model, l)) for l in listings]
        lo, hi = min(sims), max(sims)
        if hi - lo < 1e-9:
            return None
        scaled = [100.0 * (s - lo) / (hi - lo) for s in sims]
        return [(1.0 - weight) * b + weight * s
                for b, s in zip(base_scores, scaled)]
    except Exception:
        return None
