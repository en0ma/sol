import unittest
from unittest.mock import patch
from arb.raydium_public_pool_discovery import parse_candidates,discover,AMM_V4

POOL="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
MINT_A="So11111111111111111111111111111111111111112"
MINT_B="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def response(program=AMM_V4,mint_a=MINT_A,mint_b=MINT_B,tvl=12000):
    return {"success":True,"data":{"data":[{
        "id":POOL,"programId":program,"mintA":{"address":mint_a},
        "mintB":{"address":mint_b},"tvl":tvl,"type":"Standard"}]}}

class RaydiumPublicPoolDiscoveryTests(unittest.TestCase):
    def test_accepts_arbitrary_valid_mints_and_liquidity(self):
        self.assertEqual(parse_candidates(response()),[POOL])
        self.assertEqual(parse_candidates(response(mint_a=MINT_B,mint_b=MINT_A)),[POOL])
        self.assertEqual(parse_candidates(response(tvl=9000)),[])
        self.assertEqual(parse_candidates(response(tvl=float("nan"))),[])

    def test_rejects_other_program_and_invalid_mints(self):
        self.assertEqual(parse_candidates(response(program="wrong")),[])
        self.assertEqual(parse_candidates(response(mint_b=MINT_A)),[])

    def test_rejects_malformed_response(self):
        for payload in ({}, {"success":False,"data":{}},
                        {"success":True,"data":[]}, {"success":True,"data":{}}):
            with self.assertRaises(ValueError):
                parse_candidates(payload)

    def test_no_token_mint_filters_in_list_request(self):
        import json
        from unittest.mock import MagicMock
        mock_response=MagicMock()
        mock_response.__enter__.return_value.read.return_value=json.dumps(response()).encode()
        with patch("arb.raydium_public_pool_discovery.urlopen",return_value=mock_response) as url:
            self.assertEqual(discover(max_pages=1),[POOL])
        requested=url.call_args.args[0].full_url
        self.assertIn("/pools/info/list?",requested)
        self.assertNotIn("mint1=",requested)
        self.assertNotIn("mint2=",requested)

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
