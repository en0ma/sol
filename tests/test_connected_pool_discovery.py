import unittest
from unittest.mock import patch

from arb.connected_pool_discovery import candidate_pairs, expand, compact_pair, unique_venue_pairs
from arb.orca_whirlpool import SOL, USDC


class ConnectedPoolDiscoveryTests(unittest.TestCase):
    def test_committed_clean_snapshot_is_unique_and_short(self):
        import json
        from pathlib import Path
        file=Path(__file__).resolve().parents[1]/"arb"/"pool_registry_clean_snapshot.json"
        snapshot=json.loads(file.read_text())
        rows=snapshot["pools"]
        self.assertGreater(len(rows),0)
        self.assertEqual(len(rows),len({(x["venue"],x["pair"]) for x in rows}))
        self.assertEqual(len(rows),len({(x["venue"],tuple(sorted(x["mints"]))) for x in rows}))
        for x in rows:
            self.assertLessEqual(len(x["pair"]),9)
            self.assertEqual(len(x["mints"]),2)
            self.assertNotEqual(x["mints"][0],x["mints"][1])

    def test_display_pair_is_nine_characters_or_less(self):
        mint="x"*44
        self.assertLessEqual(len(compact_pair([SOL,mint])),9)
        self.assertEqual(compact_pair([SOL,USDC]),"SOL/USDC")
        self.assertLessEqual(len(compact_pair([mint,USDC],
           {mint:{"mint":mint,"symbol":"VERYLONGTOKEN"}})),9)
    def test_duplicate_pairs_per_venue_deduplicated_by_mint_not_symbol(self):
        mint="x"*44
        other="y"*44
        def entry(venue,address,mints,amounts):
            return {"venue":venue,"address":address,"mints":mints,
                    "vault_base_units":amounts,"verified":True}
        candidates=[entry("orca","a"*44,[SOL,mint],[10,10]),
                    entry("orca","b"*44,[mint,SOL],[20,20]),
                    entry("orca","c"*44,[SOL,other],[15,15]),
                    entry("raydium_clmm","d"*44,[SOL,mint],[9,9])]
        clean=unique_venue_pairs(candidates)
        self.assertEqual(len(clean),3)
        self.assertEqual({r["address"] for r in clean},{"b"*44,"c"*44,"d"*44})
        self.assertTrue(all(len(r["pair"])<=9 for r in clean))
        with self.assertRaises(ValueError):
            unique_venue_pairs([candidates[0],candidates[0]])
    def test_unverified_duplicate_cannot_override_real_pool(self):
        p={"venue":"orca","address":"a"*44,"mints":[SOL,USDC],
           "vault_base_units":[1,1],"verified":False}
        with self.assertRaises(ValueError): unique_venue_pairs([p])

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
