import unittest
from unittest.mock import patch
from arb.next_ten_signed_atomic_offline import run_three_venue
class Tests(unittest.TestCase):
    def fixture(self):
        return {"fixture_kind":"THREE_DISTINCT_VENUE_CLOSED_ROUTE",
                "source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
                "route_venues":["raydium_cpmm","orca","raydium_amm_v4"],
                "route_pool_addresses":["p","q","r"],
                "route_mints":["A","B","C","A"],
                "leg_evidence_by_index":[{"venue":"raydium_cpmm","pool":"p"},
                                         {"venue":"orca","pool":"q"},
                                         {"venue":"raydium_amm_v4","pool":"r"}]}
    def test_disconnected_route_rejected_before_hydration(self):
        f=self.fixture();f["route_mints"]=["A","B","B","A"]
        with patch("arb.next_ten_signed_atomic_offline.hydrate") as hydrate,patch(
            "arb.source_snapshot_manifest.verify"):
            with self.assertRaisesRegex(ValueError,"topology"):
                run_three_venue("http://127.0.0.1:8899",f)
            hydrate.assert_not_called()
    def test_duplicate_venue_rejected_before_hydration(self):
        f=self.fixture();f["route_venues"][2]="orca"
        with patch("arb.next_ten_signed_atomic_offline.hydrate") as hydrate,patch(
            "arb.source_snapshot_manifest.verify"):
            with self.assertRaisesRegex(ValueError,"topology"):
                run_three_venue("http://127.0.0.1:8899",f)
            hydrate.assert_not_called()
    def test_mismatched_source_proof_rejected(self):
        f=self.fixture();f["leg_evidence_by_index"][2]["pool"]="wrong"
        with patch("arb.next_ten_signed_atomic_offline.hydrate") as hydrate,patch(
            "arb.source_snapshot_manifest.verify"):
            with self.assertRaisesRegex(ValueError,"evidence identity"):
                run_three_venue("http://127.0.0.1:8899",f)
            hydrate.assert_not_called()
    def test_untrusted_source_rejected(self):
        f=self.fixture();f["source"]="unknown"
        with self.assertRaises(ValueError):
            run_three_venue("http://127.0.0.1:8899",f)
if __name__=="__main__":unittest.main()
