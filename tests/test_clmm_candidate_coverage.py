import unittest
from unittest.mock import patch
import json
from arb.atomic_missing_venue_candidates import enrich,discover_clmm_candidates
from arb.raydium_clmm import PROGRAM
class CLMMCandidateCoverageTests(unittest.TestCase):
    def test_bounded_clmm_added_untrusted_without_removing_existing(self):
        registry={"pools":[{"venue":"raydium_clmm","address":"x"*32}]}
        x=enrich(registry,[],clmm_candidates=[{"address":"y"*32,"mints":["a"*32,"b"*32]}])
        self.assertEqual(len(x["pools"]),2)
        self.assertFalse(x["pools"][1]["onchain_authenticated"])
        self.assertEqual(x["pools"][1]["venue"],"raydium_clmm")
        self.assertEqual(len(registry["pools"]),1)
    def test_discovery_prioritizes_compatible_peer_mint_pairs(self):
        good={"id":"g"*32,"programId":PROGRAM,
              "mintA":{"address":"a"*32},"mintB":{"address":"b"*32}}
        other={"id":"h"*32,"programId":PROGRAM,
              "mintA":{"address":"c"*32},"mintB":{"address":"d"*32}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({"success":True,"data":{"data":[other,good]}}).encode()
        with patch("urllib.request.urlopen",return_value=Response()):
            result=discover_clmm_candidates({"pools":[{"venue":"orca","mints":["b"*32,"a"*32]}]})
        self.assertEqual(result[0]["address"],"g"*32)
        self.assertTrue(result[0]["matching_peer_mints"])
    def test_program_identity_is_mandatory(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({"success":True,"data":{"data":[{
                "id":"z"*32,"programId":"wrong","mintA":{"address":"a"*32},
                "mintB":{"address":"b"*32}}]}}).encode()
        with patch("urllib.request.urlopen",return_value=Response()):
            self.assertEqual(discover_clmm_candidates({"pools":[]}),[])
if __name__=="__main__":unittest.main()
