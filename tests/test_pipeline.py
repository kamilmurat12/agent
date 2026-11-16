
"""Unit tests for the lead-qualifying pipeline (offline mode)."""

import unittest

from app.data import DEMO_LISTINGS
from app.generator import DemoListingStore, LargeListingStore
from app.pipeline import (
    extract_offline, qualify_lead, process_lead, score_listing,
)


def extract(text):
    return extract_offline(text)


class BudgetParsing(unittest.TestCase):
    def test_under_dollar_k(self):
        self.assertEqual(extract("house under $520k")["budget"], 520000)

    def test_budget_around_plain(self):
        self.assertEqual(extract("Budget around 380000")["budget"], 380000)

    def test_max_k(self):
        self.assertEqual(extract("Max 300k")["budget"], 300000)

    def test_budget_up_to_k(self):
        self.assertEqual(extract("budget up to 950k")["budget"], 950000)

    def test_million(self):
        self.assertEqual(extract("Budget 2 million")["budget"], 2_000_000)

    def test_small_number_rejected(self):
        self.assertIsNone(extract("budget of 4")["budget"])

    def test_family_of_4_not_a_budget(self):
        self.assertIsNone(extract("Family of 4, looking for a home")["budget"])

    def test_timeline_not_a_budget(self):
        self.assertIsNone(extract("within 2 months")["budget"])

    def test_comma_price(self):
        self.assertEqual(extract("under $520,000")["budget"], 520000)


class BedroomParsing(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(extract("3 bedroom house")["bedrooms"], 3)

    def test_plus_suffix(self):
        self.assertEqual(extract("4+ bedrooms")["bedrooms"], 4)

    def test_bed_shorthand(self):
        self.assertEqual(extract("2 bed condo")["bedrooms"], 2)

    def test_minimum(self):
        self.assertEqual(extract("2 bedrooms minimum")["bedrooms"], 2)

    def test_missing(self):
        self.assertIsNone(extract("looking for a place")["bedrooms"])


class PropertyTypeAndAreas(unittest.TestCase):
    def test_condo(self):
        self.assertEqual(extract("2 bed condo downtown")["property_type"], "condo")

    def test_townhouse(self):
        self.assertEqual(extract("townhome near the domain")["property_type"], "townhouse")

    def test_home_is_not_a_type(self):
        self.assertIsNone(extract("a home with a yard")["property_type"])

    def test_area_detected(self):
        self.assertEqual(extract("prefer South Congress area")["areas"], ["South Congress"])

    def test_no_area(self):
        self.assertEqual(extract("anywhere is fine")["areas"], [])


class UrgencyParsing(unittest.TestCase):
    def test_months_is_medium(self):
        self.assertEqual(extract("move within 2 months")["urgency"], "MEDIUM")

    def test_weeks_is_high(self):
        self.assertEqual(extract("move within 2 weeks")["urgency"], "HIGH")

    def test_soon_is_medium(self):
        self.assertEqual(extract("need something soon")["urgency"], "MEDIUM")

    def test_asap_is_high(self):
        self.assertEqual(extract("need it asap")["urgency"], "HIGH")

    def test_not_urgent_beats_urgency_word(self):
        self.assertEqual(extract("not urgent")["urgency"], "LOW")

    def test_flexible_is_low(self):
        self.assertEqual(extract("Flexible on timing")["urgency"], "LOW")

    def test_default_is_low(self):
        self.assertEqual(extract("just looking around")["urgency"], "LOW")


class ProfileParsing(unittest.TestCase):
    def test_investor(self):
        self.assertEqual(extract("I can rent out the property")["profile"], "investor")

    def test_first_time(self):
        self.assertEqual(extract("First time buyer here")["profile"], "first_time")

    def test_none(self):
        self.assertIsNone(extract("looking for a place")["profile"])


class MustHaveSplit(unittest.TestCase):
    def test_need_clause_is_must(self):
        c = extract("We need a good school district and a yard for the kids")
        self.assertEqual(c["must_haves"], ["good_schools", "yard", "family_friendly"])
        self.assertEqual(c["nice_to_have"], [])

    def test_want_clause_is_soft(self):
        c = extract("want something modern and walkable")
        self.assertEqual(c["nice_to_have"], ["walkable", "modern"])
        self.assertEqual(c["must_haves"], [])

    def test_must_have_phrase(self):
        c = extract("must have pool and home office")
        self.assertEqual(c["must_haves"], ["pool", "office_space"])

    def test_city_name_is_not_a_feature(self):
        c = extract("relocating from Denver")
        self.assertNotIn("office_space", c["nice_to_have"])
        self.assertNotIn("office_space", c["must_haves"])


class QualifyScoring(unittest.TestCase):
    def test_presets(self):
        samples = {
            "We are relocating from Denver and looking for a 3 bedroom house under $520k. "
            "We need a good school district and a yard for the kids, prefer South Congress area. "
            "Hoping to move within 2 months.": (93, "HOT"),
            "First time buyer here. Budget around 380000. Looking for a 2 bed condo downtown, "
            "want something modern and walkable to coffee shops. Flexible on timing.": (72, "WARM"),
            "Looking for an affordable starter property I can rent out. Max 300k, 2 bedrooms minimum. "
            "Quiet area preferred. Not urgent.": (65, "WARM"),
            "Relocating for work, need something soon. 4+ bedrooms, pool and views would be great, "
            "budget up to 950k, want good schools for the kids.": (83, "HOT"),
            "Family of 4, looking for a home with a yard near good schools": (40, "COLD"),
            "Budget 2 million, 5 bedrooms, must have pool and home office, waterfront": (72, "WARM"),
        }
        for text, (score, tier) in samples.items():
            got_score, got_tier = qualify_lead(extract(text))
            self.assertEqual((got_score, got_tier), (score, tier), text)

    def test_low_urgency_never_hot(self):
        c = extract("Budget 2 million, 5 bedrooms, must have pool and home office, waterfront")
        score, tier = qualify_lead(c)
        self.assertLessEqual(score, 72)
        self.assertEqual(tier, "WARM")

    def test_investor_penalty(self):
        base = dict(budget=300000, bedrooms=2, bathrooms=None, property_type=None,
                    areas=[], urgency="MEDIUM", must_haves=[], nice_to_have=[],
                    profile=None)
        investor = dict(base, profile="investor")
        self.assertEqual(qualify_lead(base)[0] - qualify_lead(investor)[0], 8)


class DemoMatching(unittest.TestCase):
    def setUp(self):
        self.store = DemoListingStore()
        self.size = self.store.size

    def test_filters_condo_budget(self):
        c = extract("budget up to 320k, condo")
        cands, total, capped = self.store.search(c)
        self.assertEqual(total, 3)
        self.assertFalse(capped)
        for l in cands:
            self.assertEqual(l["property_type"], "condo")
            self.assertLessEqual(l["price"], 320000 * 1.05)

    def test_investor_match_set(self):
        c = extract("Max 300k, 2 bedrooms minimum")
        cands, total, _ = self.store.search(c)
        ids = [l["id"] for l in cands]
        self.assertEqual(total, 2)
        self.assertIn(4, ids)   # bungalow 298k
        self.assertIn(7, ids)   # historic 315k, within 5%
        self.assertNotIn(6, ids)  # 1BR starter excluded

    def test_flag_for_above_budget(self):
        l = next(x for x in DEMO_LISTINGS if x["id"] == 5)
        c = extract("budget up to 320k, want walkable")
        score, reasons = score_listing(l, c)
        texts = " ".join(t for _, t in reasons)
        self.assertIn("flag for agent", texts)

    def test_missing_must_penalty(self):
        l = next(x for x in DEMO_LISTINGS if x["id"] == 8)
        c = dict(budget=2_000_000, bedrooms=None, bathrooms=None, property_type=None,
                 areas=[], urgency="LOW", must_haves=["pool", "office_space"],
                 nice_to_have=[], profile=None)
        score, reasons = score_listing(l, c)
        texts = " ".join(t for _, t in reasons)
        self.assertIn("missing must-have: home office", texts)
        self.assertLess(score, 50)

    def test_card_structure_and_funnel(self):
        card = process_lead("Budget 2 million, 5 bedrooms, must have pool and home office, "
                            "waterfront", self.store)
        for key in ("score", "tier", "urgency", "summary", "extracted", "matches",
                    "agent_notes", "listings_screened", "listings_matched",
                    "pipeline_mode"):
            self.assertIn(key, card)
        self.assertEqual(card["listings_screened"], 20)
        self.assertEqual(card["listings_matched"], 2)
        self.assertTrue(any("inventory is tight" in n for n in card["agent_notes"]))
        self.assertTrue(any("No candidate satisfies all must-haves" in n
                            for n in card["agent_notes"]))

    def test_zero_matches_note(self):
        card = process_lead("Budget 51000, 6 bedrooms, pool", self.store)
        self.assertEqual(card["listings_matched"], 0)
        self.assertTrue(any("No listings passed" in n for n in card["agent_notes"]))

    def test_summary_has_no_none(self):
        card = process_lead("budget up to 320k, want walkable", self.store)
        self.assertNotIn("None", card["summary"])


class LargeStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = LargeListingStore()
        cls.store.build()

    def test_size(self):
        self.assertEqual(self.store.size, 1_000_000)

    def test_deterministic(self):
        other = LargeListingStore()
        other.build()
        c = extract("budget up to 450k, 3 bedrooms, house")
        a = self.store.search(c, limit=5)[0]
        b = other.search(c, limit=5)[0]
        self.assertEqual([x["id"] for x in a], [x["id"] for x in b])
        self.assertEqual([x["name"] for x in a], [x["name"] for x in b])

    def test_broad_query_matches_many(self):
        c = extract("looking for a home with a yard near good schools")
        cands, total, capped = self.store.search(c)
        self.assertGreater(total, 100_000)
        self.assertTrue(cands)

    def test_candidate_cap(self):
        c = extract("just looking around")
        cands, total, capped = self.store.search(c)
        self.assertGreater(total, 20_000)
        self.assertTrue(capped)
        self.assertLessEqual(len(cands), 20_000)

    def test_empty_pool_note(self):
        card = process_lead("Budget 51000, 6 bedrooms, pool", self.store)
        self.assertEqual(card["listings_matched"], 0)
        self.assertTrue(any("No listings passed" in n for n in card["agent_notes"]))

    def test_top_matches_consistent(self):
        card = process_lead("budget up to 450k, need 3 bedrooms and a yard, good schools",
                            self.store)
        self.assertEqual(len(card["matches"]), 3)
        scores = [m["score"] for m in card["matches"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
