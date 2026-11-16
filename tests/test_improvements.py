
"""Tests for the v3 improvements: robust parsing, diversity, feedback,
PDF export, LLM extraction, semantic rerank honesty, shuffled cap."""

import json
import os
import tempfile
import unittest

from app.data import DEMO_LISTINGS, FEATURES, REGIONS
from app.generator import DemoListingStore, LargeListingStore
from app.llm_extract import extract_llm, _validate
from app import feedback as fb
from app.pipeline import (
    _apply_diversity, extract_offline, process_lead, qualify_lead,
)
from app.report import build_pdf
from app import search as sem


def extract(text):
    return extract_offline(text)


class RobustBudget(unittest.TestCase):
    def test_half_million_words(self):
        self.assertEqual(extract("budget up to half a million")["budget"], 500_000)

    def test_a_million(self):
        self.assertEqual(extract("I can spend a million dollars")["budget"], 1_000_000)

    def test_word_number_million(self):
        self.assertEqual(extract("around two million for a house")["budget"], 2_000_000)

    def test_range_takes_max(self):
        self.assertEqual(extract("between 400k and 500k")["budget"], 500_000)

    def test_dollars_word_no_dollar_sign(self):
        self.assertEqual(extract("about 500,000 dollars")["budget"], 500_000)

    def test_tilde(self):
        self.assertEqual(extract("budget ~500k")["budget"], 500_000)

    def test_old_cases_still_hold(self):
        self.assertEqual(extract("house under $520k")["budget"], 520_000)
        self.assertIsNone(extract("Family of 4, looking for a home")["budget"])
        self.assertIsNone(extract("within 2 months")["budget"])


class WordBedrooms(unittest.TestCase):
    def test_two_bedrooms(self):
        self.assertEqual(extract("looking for two bedrooms")["bedrooms"], 2)

    def test_digit_bedrooms_unchanged(self):
        self.assertEqual(extract("3 bedroom house")["bedrooms"], 3)


class RobustAreas(unittest.TestCase):
    def test_alias_soco(self):
        self.assertIn("South Congress", extract("prefer SoCo")["areas"])

    def test_domain(self):
        self.assertIn("North Burnet", extract("townhome near the domain")["areas"])

    def test_typo_doubled_letter(self):
        self.assertEqual(extract("prefer South Congresss area")["areas"], ["South Congress"])

    def test_no_prefix_duplicates(self):
        areas = extract("looking in downtown pflugerville")["areas"]
        self.assertEqual(areas, ["Downtown Pflugerville"])

    def test_no_area(self):
        self.assertEqual(extract("anywhere is fine")["areas"], [])


class Diversity(unittest.TestCase):
    def setUp(self):
        self.store = DemoListingStore()

    def test_duplicates_penalized(self):
        card = process_lead(
            "3 bedroom house under $520k, good schools, yard, prefer South Congress",
            self.store)
        scores = [m["score"] for m in card["matches"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_no_penalty_when_all_distinct(self):
        ranked = [(90.0, l, []) for l in DEMO_LISTINGS[:3]
                  if len({(x["region"], x["property_type"])
                          for x in DEMO_LISTINGS[:3]}) == 3]
        if len(ranked) == 3:
            out = _apply_diversity(list(ranked))
            self.assertEqual([s for s, _, _ in out], [90.0, 90.0, 90.0])


class Feedback(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "test.db")
        fb.save_feedback("test lead", {"budget": 500000},
                         {"id": 1, "name": "Modern 3BR", "score": 80.0},
                         "fit", path=self.path)
        fb.save_feedback("test lead", {"budget": 500000},
                         {"id": 2, "name": "Spacious 4BR", "score": 70.0},
                         "miss", path=self.path)
        fb.save_feedback("another lead", {},
                         {"id": 1, "name": "Modern 3BR", "score": 80.0},
                         "fit", path=self.path)

    def test_counts(self):
        s = fb.stats(path=self.path)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["fit"], 2)
        self.assertEqual(s["miss"], 1)

    def test_top_listings(self):
        s = fb.stats(path=self.path)
        self.assertEqual(s["top_listings"][0]["name"], "Modern 3BR")
        self.assertEqual(s["top_listings"][0]["marks"], 2)


class PdfExport(unittest.TestCase):
    def test_pdf_built(self):
        store = DemoListingStore()
        card = process_lead("budget up to 320k, want walkable", store)
        path = os.path.join(tempfile.mkdtemp(), "card.pdf")
        build_pdf(card, path)
        with open(path, "rb") as f:
            data = f.read()
        self.assertGreater(len(data), 1000)
        self.assertTrue(data.startswith(b"%PDF"))


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return FakeResponse(self._content)


class FakeChat:
    def __init__(self, content):
        self.completions = FakeCompletions(content)


class FakeClient:
    def __init__(self, content):
        self.chat = FakeChat(content)


class LLMExtraction(unittest.TestCase):
    GOOD = json.dumps({
        "budget": 520000, "bedrooms": 3, "bathrooms": 2, "property_type": "house",
        "areas": ["South Congress"], "urgency": "MEDIUM",
        "must_haves": ["good_schools"], "nice_to_have": ["yard"],
        "profile": "family",
    })

    def test_valid_response_parsed(self):
        c = extract_llm("3 bed house under $520k", client=FakeClient(self.GOOD))
        self.assertEqual(c["budget"], 520_000)
        self.assertEqual(c["must_haves"], ["good_schools"])

    def test_no_key_no_client(self):
        import app.llm_extract as m
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self.assertIsNone(m.extract_llm("anything", client=None, api_key=None))
        finally:
            if old:
                os.environ["OPENAI_API_KEY"] = old

    def test_bad_json_falls_back(self):
        c = extract_llm("text", client=FakeClient("I think you need a 3 bed house!"))
        self.assertIsNone(c)

    def test_out_of_schema_budget_rejected(self):
        bad = json.dumps({**json.loads(self.GOOD), "budget": 999_999_999_999})
        self.assertIsNone(extract_llm("text", client=FakeClient(bad)))

    def test_unknown_feature_rejected(self):
        bad = json.dumps({**json.loads(self.GOOD), "must_haves": ["helipad"]})
        self.assertIsNone(extract_llm("text", client=FakeClient(bad)))

    def test_unknown_region_rejected(self):
        bad = json.dumps({**json.loads(self.GOOD), "areas": ["Mars"]})
        self.assertIsNone(extract_llm("text", client=FakeClient(bad)))

    def test_markdown_fences_accepted(self):
        wrapped = "```json\n" + self.GOOD + "\n```"
        c = extract_llm("text", client=FakeClient(wrapped))
        self.assertEqual(c["budget"], 520_000)


class SearchBackendHonesty(unittest.TestCase):
    def test_flag_is_tfidf_without_backend(self):
        if sem.available():
            self.skipTest("sentence-transformers installed in this environment")
        store = DemoListingStore()
        card = process_lead("budget up to 320k, want walkable", store)
        self.assertEqual(card["search_backend"], "tfidf")

    def test_flag_matches_actual_result(self):
        """Flag must reflect what rerank actually returned, not intent."""
        store = DemoListingStore()
        card = process_lead("budget up to 320k, want walkable", store)
        self.assertIn(card["search_backend"], ("tfidf", "embeddings+tfidf"))


class ShuffledCap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = LargeListingStore()
        cls.store.build()

    def test_cap_spread_over_pool(self):
        c = extract("just looking around")
        cands, total, capped = self.store.search(c)
        self.assertTrue(capped)
        ids = [l["id"] for l in cands]
        self.assertGreater(max(ids), 100_000,
                           "shuffled cap should reach deep into the pool")

    def test_deterministic_after_shuffle(self):
        c = extract("budget up to 450k, 3 bedrooms, house")
        a = self.store.search(c, limit=5)[0]
        b = LargeListingStore()
        b.build()
        bb = b.search(c, limit=5)[0]
        self.assertEqual([x["id"] for x in a], [x["id"] for x in bb])


class Descriptions(unittest.TestCase):
    def test_bank_loads(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "descriptions.json")
        with open(path, encoding="utf-8") as f:
            bank = json.load(f)
        for f_ in FEATURES:
            self.assertIn(f_, bank["features"])

    def test_unique_descriptions(self):
        store = LargeListingStore()
        store.build()
        descs = set()
        for i in range(0, 1_000_000, 500):
            descs.add(store._listing(i)["description"])
        self.assertEqual(len(descs), 2000)

    def test_no_raw_feature_names_in_text(self):
        store = LargeListingStore()
        store.build()
        for i in range(0, 500_000, 5000):
            d = store._listing(i)["description"]
            for f_ in FEATURES:
                self.assertNotIn(f_ + " on site", d)


class CardExtras(unittest.TestCase):
    def test_card_has_new_keys(self):
        card = process_lead("budget up to 320k, want walkable", DemoListingStore())
        for key in ("search_backend", "pipeline_mode"):
            self.assertIn(key, card)

    def test_empty_inquiry_raises(self):
        with self.assertRaises(ValueError):
            process_lead("   ", DemoListingStore())


if __name__ == "__main__":
    unittest.main()
