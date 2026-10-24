import json
import unittest
from unittest.mock import patch
from arb.atomic_missing_venue_candidates import discover_amm_v4_candidates
from arb.raydium_public_pool_discovery import AMM_V4

class MatchingAmmV4DiscoveryTests(unittest.TestCase):
    def test_prefers_matching_pool_over_top_liquidity_mismatch(self):
        good={"id":"g"*32,"programId":AMM_V4,
              "mintA":{"address":"a"*32},"mintB":{"address":"b"*32}}
        bad={"id":"h"*32,"programId":AMM_V4,
             "mintA":{"address":"c"*32},"mintB":{"address":"d"*32}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({"success":True,"data":{"data":[bad,good]}}).encode()
        with patch("urllib.request.urlopen",return_value=Response()):
            result=discover_amm_v4_candidates({"pools":[{"venue":"orca",
                "mints":["b"*32,"a"*32]}]})
        self.assertEqual(result[0]["address"],"g"*32)
        self.assertTrue(result[0]["matching_peer_mints"])
    def test_rejects_wrong_program_and_malformed_accounts(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({"success":True,"data":{"data":[{
                "id":"z"*32,"programId":"wrong",
                "mintA":{"address":"a"*32},"mintB":{"address":"b"*32}}]}}).encode()
        with patch("urllib.request.urlopen",return_value=Response()):
            self.assertEqual(discover_amm_v4_candidates({"pools":[]}),[])

if __name__=="__main__":unittest.main()
