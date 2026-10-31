import unittest
from unittest.mock import patch

from arb.connected_pool_discovery import candidate_pairs, expand
from arb.orca_whirlpool import SOL, USDC


class ConnectedPoolDiscoveryTests(unittest.TestCase):
    def test_shared_pair_preferred(self):
        mint="x"*44
        hints=[{"venue":"orca","mints":[SOL,mint]},
               {"venue":"raydium_clmm","mints":[mint,SOL]},
               {"venue":"pumpswap","mints":[SOL,USDC]}]
        self.assertEqual(set(candidate_pairs(hints,max_pairs=1)[0]),{SOL,mint})

    def test_cross_hub_sol_usdc_usdt_pair_queries_not_invented_pools(self):
        from arb.onchain_pool_discovery import USDT
        mint="x"*44
        hints=[{"venue":"orca","mints":[SOL,mint]},
               {"venue":"raydium_clmm","mints":[SOL,USDC]}]
        pairs=candidate_pairs(hints,max_pairs=30)
        self.assertIn(sorted([mint,USDT]),[sorted(x) for x in pairs])
        self.assertEqual(len(pairs),len(set(tuple(x) for x in pairs)))
        self.assertTrue(all(len(pair)==2 and pair[0]!=pair[1] for pair in pairs))
    def test_only_new_independently_verified_pools_are_admitted(self):
        initial=[{"venue":"orca","address":"a"*44,"mints":[SOL,USDC]}]
        base={"venue":"orca","address":"a"*44,"mints":[SOL,USDC],
              "verified":True,"slot":10,"vault_base_units":[10,20]}
        new={"venue":"raydium_clmm","address":"b"*44,"mints":[SOL,USDC],
             "slot":10,"vault_base_units":[15,25]}
        discovery={"status":"COMPLETE","pools":[new],"errors":[],
                   "venue_attempts":{}}
        with patch("arb.connected_pool_discovery.refresh",
                   return_value={"verified_pools":[base],"rejected":[]}) as ref,\
             patch("arb.connected_pool_discovery.discover",
                   return_value=discovery) as find:
            result=expand("http://127.0.0.1:8899",initial,max_pairs=1,target=20)
        self.assertEqual(result["admitted"],2)
        self.assertFalse(result["seven_venue_target_met"])
        self.assertEqual(len(result["cross_venue_shared_pairs"]),1)
        self.assertEqual(len(find.call_args.args[1]),1)
        self.assertEqual(result["venue_coverage"]["raydium_clmm"]["authenticated"],1)
        self.assertFalse(result["broadcast"])

    def test_no_verified_seeds_no_fabricated_discovery(self):
        initial=[{"venue":"orca","address":"a"*44}]
        with patch("arb.connected_pool_discovery.refresh",
                   return_value={"verified_pools":[],"rejected":[]}),\
             patch("arb.connected_pool_discovery.discover") as discovery:
            report=expand("http://127.0.0.1:8899",initial)
        discovery.assert_not_called()
        self.assertEqual(report["admitted"],0)
        self.assertEqual(report["discovery_status"],"NO_VERIFIED_SEEDS")

if __name__=="__main__":
    unittest.main()
