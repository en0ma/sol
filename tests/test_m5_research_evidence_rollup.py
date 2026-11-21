import unittest
from arb.m5_research_evidence_rollup import summarize
class Tests(unittest.TestCase):
    def test_distinct_venues_and_real_pricing_blockers(self):
        rows=[{"independent_signed_accepted":True,"route_venues":["orca","raydium_cpmm","raydium_amm_v4"]},
              {"independent_signed_accepted":True,"route_venues":["orca","raydium_cpmm","raydium_amm_v4"]},
              {"independent_signed_accepted":True,"route_venues":["orca","meteora_dlmm","raydium_clmm"]}]
        r=summarize({"exported":3},{"routes":rows,"attempted":4},
          [{"signed_execution_accepted":True,"leg_comparisons":[
            {"quoted_output_base_units":100},{"quoted_output_base_units":None,"reason":"SOURCE_EXACT_QUOTE_BLOCKED: fee"}]}],
          [{"gross_delta_start_mint_base_units":-7,"status":"COST_EVIDENCE_BLOCKED","reason":"OBSERVED_TRANSACTION_FEE_LAMPORTS_MISSING"}])
        self.assertEqual(r["signed_accepted_routes"],3)
        self.assertEqual(r["distinct_accepted_venue_triples"],2)
        self.assertEqual(r["indicative_priced_legs"],1)
        self.assertEqual(r["independently_validated_quote_samples"],0)
        self.assertEqual(r["signed_gross_start_mint_deltas"],[-7])
    def test_bad_accepted_route_refused(self):
        with self.assertRaises(ValueError):
            summarize({},{"routes":[{"independent_signed_accepted":True,"route_venues":["orca","orca","clmm"]}]},[],[])
if __name__=="__main__":unittest.main()
