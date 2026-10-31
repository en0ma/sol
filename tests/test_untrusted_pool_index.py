import unittest
from unittest.mock import patch
from arb.untrusted_pool_index import pick_seeds,index_addresses,authenticate_owners,balance_candidates,pick_amm_v4_leads
from arb.orca_whirlpool import SOL,USDC
from arb.onchain_pool_discovery import VENUES

class UntrustedPoolIndexTests(unittest.TestCase):
    def test_real_source_mints_select_bounded_search_seeds(self):
        x="x"*44
        seeds=pick_seeds([{"mints":[SOL,USDC]},{"mints":[SOL,x]}],max_mints=3)
        self.assertEqual(seeds[:2],[SOL,USDC])
        self.assertIn(x,seeds)

    def test_undercovered_venue_seed_outweighs_common_orca_only_mint(self):
        rare="r"*44
        common="c"*44
        hints=([{"venue":"orca","mints":[SOL,common]} for _ in range(30)]
               +[{"venue":"pumpswap","mints":[SOL,rare]}])
        picks=pick_seeds(hints,max_mints=3)
        self.assertEqual(picks[0],SOL)
        self.assertEqual(picks[1],rare)
        self.assertNotIn(common,picks)
    def test_index_only_finds_untrusted_addresses_and_ignores_claimed_symbols(self):
        address=SOL
        def feed(mint):
            return [{"chainId":"solana","dexId":"forged",
                     "pairAddress":address,
                     "baseToken":{"address":mint,"symbol":"FAKE"},
                     "quoteToken":{"address":USDC},
                     "liquidity":{"usd":9000}},
                    {"chainId":"ethereum","pairAddress":USDC,
                     "baseToken":{"address":mint},"quoteToken":{"address":USDC}}]
        report=index_addresses([SOL],fetch=feed)
        self.assertEqual(report["addresses"],[address])
        self.assertNotIn("mints",str(report["addresses"]))
        self.assertFalse(report["broadcast"])

    def test_mint_stratification_prevents_sol_from_monopolizing_candidate_budget(self):
        from arb.onchain_pool_discovery import JUP
        # All account addresses are real Pubkey strings. The same mint can
        # return many more liquid addresses, but every seed earns a probe.
        addresses=[SOL,USDC,JUP]
        seed_a=SOL
        seed_b=USDC
        def source(mint):
            available=addresses[:2] if mint==seed_a else addresses[2:]
            return [{"chainId":"solana","pairAddress":a,
                     "baseToken":{"address":mint},
                     "quoteToken":{"address":JUP},
                     "liquidity":{"usd":10000 if mint==seed_a else 1}}
                    for a in available]
        result=index_addresses([seed_a,seed_b],max_addresses=2,fetch=source)
        self.assertEqual(result["selection_mode"],"MINT_STRATIFIED_ROUND_ROBIN")
        self.assertEqual(result["addresses"][1],JUP)
        self.assertIn(result["addresses"][0],[SOL,USDC])
        self.assertEqual(len(set(result["addresses"])),2)
    def test_only_actual_source_owner_assigns_venue(self):
        program=VENUES["orca"][0]
        response={"value":[{"owner":program,"executable":False},
                           {"owner":"forged","executable":False}]}
        with patch("arb.untrusted_pool_index.call",return_value=response) as rpc:
            result=authenticate_owners("rpc",[SOL,USDC])
        self.assertEqual(result["pools"],[{"venue":"orca","address":SOL}])
        self.assertEqual(len(result["rejections"]),1)
        self.assertEqual(rpc.call_args.args[1],"getMultipleAccounts")
        with patch("arb.untrusted_pool_index.call",return_value={"value":[None]}):
            with self.assertRaises(ValueError):
                authenticate_owners("rpc",[SOL,USDC])
    def test_balance_prefers_source_owner_verified_undercovered_venue(self):
        known=[{"venue":"orca"}]*40+[{"venue":"raydium_cpmm"}]*3
        rows=[{"venue":"orca","address":str(i).zfill(44)} for i in range(20)]
        rows+=[{"venue":"raydium_cpmm","address":"b"*43+str(i)} for i in range(5)]
        selected=balance_candidates(rows,known,limit=8)
        self.assertEqual(sum(x["venue"]=="raydium_cpmm" for x in selected),5)
        self.assertEqual(len(selected),8)
        self.assertEqual(len({(x["venue"],x["address"]) for x in selected}),8)
    def test_existing_registry_address_does_not_consume_discovery_quota(self):
        old={"venue":"orca","address":"a"*44}
        new={"venue":"orca","address":"b"*44}
        self.assertEqual(balance_candidates([old,new],[old],limit=2),[new])
    def test_untrusted_amm_v4_leads_only_provide_unverified_addresses(self):
        leads=[{"address":SOL,"matching_peer_mints":False,
                "programId":"FAKE","mints":[SOL,USDC]},
               {"address":USDC,"matching_peer_mints":True,
                "programId":"FAKE","mints":[USDC,SOL]},
               {"address":USDC,"matching_peer_mints":True}]
        self.assertEqual(pick_amm_v4_leads(leads,[],limit=2),[USDC,SOL])
        self.assertEqual(pick_amm_v4_leads(leads,[{"address":USDC}],limit=2),[SOL])
        with self.assertRaises(ValueError):
            pick_amm_v4_leads(leads,[],limit=50)
    def test_index_forgery_and_oversized_batch_fail(self):
        with self.assertRaises(ValueError):
            index_addresses([SOL],max_addresses=200)
        with self.assertRaises(ValueError):
            authenticate_owners("rpc",[SOL]*121)

if __name__=="__main__":
    unittest.main()
