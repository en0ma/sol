import unittest
from unittest.mock import patch
from arb.next_ten_pair_fixture_export import export
class ReadOnlyPairedFixtureTests(unittest.TestCase):
    def test_remote_source_rejected_before_any_rpc(self):
        with patch("arb.next_ten_pair_fixture_export.call") as c:
            with self.assertRaises(ValueError):
                export("https://api.mainnet-beta.solana.com",{},0,"/tmp/x")
            c.assert_not_called()
    def test_invalid_source_provenance_rejected(self):
        with self.assertRaises(ValueError):
            export("http://localhost:8899",{"source":"fabricated"},0,"/tmp/x")
    def test_route_bounds_rejected(self):
        with self.assertRaises(ValueError):
            export("http://localhost:8899",{},10,"/tmp/x")
    def test_empty_candidates_rejected(self):
        from arb.next_ten_atomic_routes import BATCH_10
        rows=[{"first_venue":a,"second_venue":b,
               "authenticated_pool_pair_candidates":[]} for a,b in BATCH_10]
        with self.assertRaisesRegex(ValueError,"no authenticated compatible"):
            export("http://localhost:8899",
                   {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
                    "route_candidates":rows},0,"/tmp/x")
if __name__=="__main__":
    unittest.main()
