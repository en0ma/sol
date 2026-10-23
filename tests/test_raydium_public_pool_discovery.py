import unittest
from unittest.mock import patch
from arb.raydium_public_pool_discovery import parse_candidates,AMM_V4
from arb.orca_whirlpool import SOL,USDC

POOL="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
def response(program=AMM_V4,mint_a=SOL,mint_b=USDC):
    return {"success":True,"data":{"data":[{
        "id":POOL,"programId":program,"mintA":{"address":mint_a},
        "mintB":{"address":mint_b},"type":"Standard"}]}}

class RaydiumPublicPoolDiscoveryTests(unittest.TestCase):
    def test_accepts_exact_program_and_mints(self):
        self.assertEqual(parse_candidates(response()),[POOL])
        self.assertEqual(parse_candidates(response(mint_a=USDC,mint_b=SOL)),[POOL])

    def test_rejects_other_program_and_mints(self):
        self.assertEqual(parse_candidates(response(program="wrong")),[])
        self.assertEqual(parse_candidates(response(mint_b="wrong")),[])

    def test_rejects_malformed_response(self):
        for payload in ({}, {"success":False,"data":{}},
                        {"success":True,"data":[]}, {"success":True,"data":{}}):
            with self.assertRaises(ValueError):
                parse_candidates(payload)

    def test_api_candidates_are_not_execution_proof(self):
        from arb.eight_venue_onchain_probe import probe
        with patch("arb.eight_venue_onchain_probe.verify_legacy",
                   side_effect=ValueError("onchain owner mismatch")) as verify:
            report=probe("http://127.0.0.1:8899",{"pools":[]},
                         public_raydium_candidates=[POOL])
        ray=next(row for row in report["venues"] if row["venue"]=="raydium_amm_v4")
        self.assertEqual(verify.call_count,1)
        self.assertFalse(ray["decoder_onchain_verified"])
        self.assertFalse(ray["builder_onchain_execution_verified"])
        self.assertFalse(report["broadcast"])
