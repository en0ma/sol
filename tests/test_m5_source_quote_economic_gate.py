import unittest
from arb.m5_source_quote_economic_gate import gate
class Tests(unittest.TestCase):
    def test_signed_three_venue_does_not_imply_source_pricing_or_net_economics(self):
        r=gate({"route_venues":["orca","raydium_cpmm","raydium_amm_v4"]},
          {"signed_atomic_simulation_verified":True,
           "rollback_failure_case_verified":True,"positive_units_consumed":12345},
          {"leg_comparisons":[{"quoted_output_base_units":None,"quote_verified":False}]*3},
          {"fee_source_verified":False,"conversion_authenticated":False,
           "profitability_verified":False,"gross_delta_start_mint_base_units":100})
        self.assertEqual(r["status"],"RESEARCH_EVIDENCE_INCOMPLETE")
        self.assertIn("OBSERVED_TRANSACTION_FEE_UNVERIFIED",r["blockers"])
        self.assertEqual(r["observed_compute_units"],12345)
        self.assertIsNone(r["net_start_mint_delta"])
        self.assertFalse(r["broadcast"])
    def test_unsigned_route_rejected(self):
        self.assertEqual(gate({"route_venues":["orca","cpmm","v4"]},{},{},{} )["status"],"SIGNED_COVERAGE_NOT_ACCEPTED")
if __name__=="__main__":unittest.main()
