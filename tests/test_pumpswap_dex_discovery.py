import unittest
from unittest.mock import patch
from arb.pumpswap_dex_discovery import resolve_pumpswap_dex_id,scan

POOL="5wNu5QhdpRGrL37ffcd6TMMqZugQgxwafgz477rShtHy"

class DexDiscoveryTests(unittest.TestCase):
    def test_resolves_only_pumpswap(self):
        self.assertEqual(resolve_pumpswap_dex_id({"data":[
            {"id":"raydium","attributes":{"name":"Raydium"}},
            {"id":"pump-swap","attributes":{"name":"PumpSwap"}}]}),"pump-swap")
    def test_ambiguous_directory_fails_closed(self):
        with self.assertRaises(ValueError):
            resolve_pumpswap_dex_id({"data":[{"id":"pump-swap"},{"id":"pumpswap"}]})
    @patch("arb.pool_registry_batches.refresh")
    @patch("arb.pumpswap_dex_discovery.read_json")
    def test_uses_pool_owner_validator_not_indexer_claim(self,read,refresh):
        read.side_effect=[{"data":[{"id":"pump-swap"}]},
                          {"data":[{"attributes":{"address":POOL}}]}]
        refresh.return_value={"verified_count":0,"rejected_count":1,"verified_pools":[],
                              "rejected":[{"reason":"owner mismatch"}]}
        result=scan("local",pages=1,limit=2,pace_seconds=0)
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["verified_count"],0)
        self.assertEqual(result["rejected_count"],1)
        self.assertEqual(result["rpc_validation_batches"],1)
        self.assertFalse(result["actionable"])
