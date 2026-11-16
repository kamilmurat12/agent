
"""Deterministic synthetic listing store for scale testing.

Generates N listings (default 1,000,000) from a fixed seed as compact numpy
arrays. Nothing is persisted to disk: the same seed always produces the same
dataset, so the full inventory can be rebuilt in seconds at startup.
"""

import numpy as np

try:
    from .data import FEATURES, PROPERTY_TYPES, REGIONS, REGION_CITY
except ImportError:
    # прямой запуск: streamlit run app/ui.py — пакет не виден
    from data import FEATURES, PROPERTY_TYPES, REGIONS, REGION_CITY

FEATURE_BITS = {name: i for i, name in enumerate(FEATURES)}

# probability of each feature in the synthetic population
FEATURE_PROBS = {
    "good_schools": 0.35, "family_friendly": 0.30, "quiet_street": 0.20,
    "pool": 0.18, "views": 0.25, "walkable": 0.25, "modern": 0.25,
    "affordable": 0.20, "office_space": 0.15, "waterfront": 0.02,
    "garage": 0.30,
}

ADJECTIVES = [
    "Modern", "Charming", "Spacious", "Cozy", "Sunlit", "Updated", "Classic",
    "New Build", "Renovated", "Elegant", "Bright", "Serene", "Inviting",
    "Stylish", "Timeless",
]

TYPE_NOUN = {"house": "Home", "condo": "Condo", "townhouse": "Townhome"}

# number of candidates the store hands to the pipeline for full scoring
CANDIDATE_CAP = 20000


class LargeListingStore:
    """1M synthetic listings in RAM, built lazily from a fixed seed."""

    def __init__(self, size=1_000_000, seed=42):
        self.size = size
        self.seed = seed
        self.built = False

    def build(self):
        if self.built:
            return
        n = self.size
        rng = np.random.default_rng(self.seed)
        self.price = (rng.uniform(150_000, 2_500_000, n) // 1000 * 1000).astype(np.int32)
        self.beds = rng.integers(1, 7, n).astype(np.int8)
        self.baths = np.clip(self.beds - 1 + rng.integers(0, 3, n), 1, 5).astype(np.int8)
        self.sqft = (600 + self.beds.astype(np.int32) * 350
                     + rng.integers(0, 800, n)).astype(np.int16)
        self.region = rng.integers(0, len(REGIONS), n).astype(np.int8)
        self.ptype = rng.integers(0, len(PROPERTY_TYPES), n).astype(np.int8)

        self.feat = np.zeros(n, np.uint32)
        for name, prob in FEATURE_PROBS.items():
            self.feat |= ((rng.random(n) < prob).astype(np.uint32) << FEATURE_BITS[name])
        # yards are far more common in houses than in condos
        yard_p = np.where(self.ptype == 0, 0.70, 0.10)
        self.feat |= ((rng.random(n) < yard_p).astype(np.uint32) << FEATURE_BITS["yard"])

        self.built = True

    def _listing(self, i):
        region = REGIONS[int(self.region[i])]
        ptype = PROPERTY_TYPES[int(self.ptype[i])]
        beds = int(self.beds[i])
        feats = [FEATURES[b] for b in range(len(FEATURES)) if (int(self.feat[i]) >> b) & 1]
        year = 1970 + (int(i) * 2654435761) % 56
        return {
            "id": int(i),
            "name": "%s %dBR %s in %s" % (ADJECTIVES[i % len(ADJECTIVES)], beds,
                                          TYPE_NOUN[ptype], region),
            "region": region,
            "city": REGION_CITY.get(region, "Austin"),
            "property_type": ptype,
            "price": int(self.price[i]),
            "beds": beds,
            "baths": int(self.baths[i]),
            "sqft": int(self.sqft[i]),
            "features": feats,
            "description": "%d bedroom %s in %s, %d sqft. Features: %s. Built %d."
                           % (beds, ptype, region, int(self.sqft[i]),
                              ", ".join(feats) if feats else "none", year),
        }

    def search(self, criteria, limit=50):
        """Return (candidates, total_matched, capped). Same contract as the demo store."""
        if not self.built:
            self.build()
        mask = np.ones(self.size, dtype=bool)
        budget = criteria.get("budget")
        beds_req = criteria.get("bedrooms")
        type_req = criteria.get("property_type")
        if budget:
            mask &= self.price <= int(budget * 1.05)
        if beds_req:
            mask &= self.beds >= int(beds_req)
        if type_req:
            mask &= self.ptype == PROPERTY_TYPES.index(type_req)
        total = int(np.count_nonzero(mask))
        if total == 0:
            return [], 0, False
        idx = np.nonzero(mask)[0]
        capped = len(idx) > CANDIDATE_CAP
        if capped:
            # детерминированный равномерный сэмпл по всей базе,
            # чтобы «хвост» инвентаря не терялся при капе кандидатов
            step = int(np.ceil(len(idx) / CANDIDATE_CAP))
            idx = idx[::step][:CANDIDATE_CAP]
        order = self._prescore(idx, criteria)
        picked = [self._listing(int(i)) for i in idx[order[:limit]]]
        return picked, total, capped

    def _prescore(self, idx, criteria):
        """Vectorized pre-scoring; weights mirror pipeline.score_listing exactly."""
        s = np.full(len(idx), 25.0)
        budget = criteria.get("budget")
        if budget:
            s += np.where(self.price[idx] <= budget, 25.0,
                          np.where(self.price[idx] <= budget * 1.05, 10.0, 0.0))
        beds_req = criteria.get("bedrooms")
        if beds_req:
            s += (self.beds[idx] >= beds_req) * 15.0
        if criteria.get("areas"):
            best = np.zeros(len(idx), bool)
            for area in criteria["areas"]:
                if area in REGIONS:
                    best |= self.region[idx] == REGIONS.index(area)
            s += best * 22.0
        if criteria.get("property_type"):
            s += (self.ptype[idx] == PROPERTY_TYPES.index(criteria["property_type"])) * 10.0
        wanted = list(criteria.get("must_haves", [])) + list(criteria.get("nice_to_have", []))
        for f in dict.fromkeys(wanted):
            s += ((self.feat[idx] >> FEATURE_BITS[f]) & 1) * 8.0
        for f in criteria.get("must_haves", []):
            s -= (((self.feat[idx] >> FEATURE_BITS[f]) & 1) == 0) * 12.0
        np.clip(s, 0.0, 100.0, out=s)
        order = np.argsort(-s, kind="stable")
        return order


class DemoListingStore:
    """20 curated demo listings."""

    def __init__(self, listings=None):
        try:
            from .data import DEMO_LISTINGS
        except ImportError:
            from data import DEMO_LISTINGS
        self.listings = list(DEMO_LISTINGS if listings is None else listings)
        self.size = len(self.listings)
        self.built = True

    def build(self):
        pass

    def search(self, criteria, limit=200):
        budget = criteria.get("budget")
        beds_req = criteria.get("bedrooms")
        type_req = criteria.get("property_type")
        out = []
        for l in self.listings:
            if budget and l["price"] > budget * 1.05:
                continue
            if beds_req and l["beds"] < beds_req:
                continue
            if type_req and l["property_type"] != type_req:
                continue
            out.append(l)
        return out[:limit], len(out), False
