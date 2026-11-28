import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from arb.m5_three_venue_coverage_acceptance import check
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_coverage_acceptance.verify",return_value=True)
    @patch("arb.m5_three_venue_coverage_acceptance.compare",return_value={"signed_execution_accepted":True,"leg_comparisons":[1,2,3]})
    def test_counts_distinct_venue_triples_not_receipt_duplicates(self,_,__):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            src,dst=Path(a),Path(b)
            routes=[]
            for i,venues in enumerate((["orca","raydium_cpmm","raydium_amm_v4"],
                                      ["raydium_amm_v4","orca","raydium_cpmm"],
                                      ["orca","raydium_clmm","meteora_dlmm"])):
                name="triangle-%02d.json"%i
                routes.append({"index":i,"fixture":name,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE"})
                (src/name).write_text(json.dumps({"route_venues":venues,"route_pool_addresses":[str(i),"x","y"]}))
                (dst/name).write_text("{}")
            (src/"summary.json").write_text(json.dumps({"routes":routes}))
            (dst/"summary.json").write_text(json.dumps({"independent_signed_accepted":3}))
            result=check(src,dst,minimum_unique=2)
            self.assertEqual(result["distinct_venue_triples"],2)
            self.assertEqual(result["accepted_receipts"],3)
if __name__=="__main__":unittest.main()
