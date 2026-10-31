import unittest
from arb.atomic_missing_venue_candidates import enrich

class MissingVenueCandidateTests(unittest.TestCase):
    def test_adds_only_bounded_untrusted_amm4_leads(self):
        sources=["a"*32,"b"*32,"c"*32]
        got=enrich({"pools":[{"venue":"raydium_clmm","address":"a"*32}]},sources,limit=2)
        self.assertEqual(len(got["pools"]),3)
        self.assertEqual(got["pools"][-1]["venue"],"raydium_amm_v4")
        self.assertFalse(got["pools"][-1]["onchain_authenticated"])
        self.assertEqual(got["pools"][1]["address"],"b"*32)
    def test_does_not_change_pinned_registry(self):
        original={"pools":[{"venue":"orca","address":"x"*32}]}
        enriched=enrich(original,["y"*32],limit=1)
        self.assertEqual(len(original["pools"]),1)
        self.assertEqual(len(enriched["pools"]),2)
    def test_invalid_count_is_rejected(self):
        with self.assertRaises(ValueError):
            enrich({"pools":[]},[],limit=13)

if __name__=="__main__":unittest.main()
