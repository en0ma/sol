import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from arb.pumpswap_indexed_discovery import candidates,scan
ADDR="HtoZbnFf7BDGvPg3RxwiXN5pPG7hLa78XVGscLF9fkYV"
class PumpSwapIndexedDiscoveryTests(unittest.TestCase):
    def test_only_unverified_pool_addresses_emitted(self):
        result=candidates({"data":[{"attributes":{"address":ADDR}},
                                   {"attributes":{"address":ADDR}},
                                   {"attributes":{"address":"invalid"}}]})
        self.assertEqual(len(result),1)
        self.assertFalse(result[0]["verified"])
        self.assertEqual(result[0]["venue"],"pumpswap")
    def test_known_other_dex_is_filtered_before_rpc(self):
        result=candidates({"data":[{"attributes":{"address":ADDR},
                                    "relationships":{"dex":{"data":{"id":"raydium"}}}}]})
        self.assertEqual(result,[])
    def test_invalid_structure_fails_closed(self):
        with self.assertRaises(ValueError):candidates({"data":{}})
    def test_invalid_pagination_fails_closed(self):
        with self.assertRaises(ValueError):
            scan("local",["mint"],limit=2,pages=11)

    @patch("arb.pool_registry.refresh")
    @patch("arb.pumpswap_indexed_discovery.fetch")
    def test_indexer_429_is_reported_not_confused_with_invalid_pools(self,fetch,refresh):
        fetch.side_effect=HTTPError("indexer",429,"Too Many Requests",{},None)
        refresh.return_value={"verified_count":0,"rejected_count":0,
                              "verified_pools":[],"rejected":[]}
        result=scan("local",["mint"],limit=2,pages=2,pace_seconds=0)
        self.assertEqual(result["indexer_errors"][0]["http_status"],429)
        self.assertEqual(result["checked_count"],0)
        self.assertEqual(result["rejected_count"],0)

    @patch("arb.pool_registry.refresh")
    @patch("arb.pumpswap_indexed_discovery.fetch")
    def test_rpc_validator_controls_admission(self,fetch,refresh):
        fetch.return_value=[{"venue":"pumpswap","address":ADDR,"verified":False}]
        refresh.return_value={"verified_count":0,"rejected_count":1,
                              "verified_pools":[],"rejected":[{"reason":"owner mismatch"}]}
        result=scan("local",["token"],limit=2)
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["verified_pumpswap_count"],0)
        self.assertEqual(result["rejected_count"],1)
        self.assertEqual(result["pages_per_mint"],1)
        self.assertFalse(result["simulation_verified"])
