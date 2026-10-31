import unittest
from unittest.mock import patch
from arb.untrusted_pool_index import pick_seeds,index_addresses,authenticate_owners
from arb.orca_whirlpool import SOL,USDC
from arb.onchain_pool_discovery import VENUES

class UntrustedPoolIndexTests(unittest.TestCase):
    def test_real_source_mints_select_bounded_search_seeds(self):
        x="x"*44
        seeds=pick_seeds([{"mints":[SOL,USDC]},{"mints":[SOL,x]}],max_mints=3)
        self.assertEqual(seeds[:2],[SOL,USDC])
        self.assertIn(x,seeds)

    def test_index_only_finds_untrusted_addresses_and_ignores_claimed_symbols(self):
        address="A"*44
        def feed(mint):
            return [{"chainId":"solana","dexId":"forged",
                     "pairAddress":address,
                     "baseToken":{"address":mint,"symbol":"FAKE"},
                     "quoteToken":{"address":USDC},
                     "liquidity":{"usd":9000}},
                    {"chainId":"ethereum","pairAddress":"B"*44,
                     "baseToken":{"address":mint},"quoteToken":{"address":USDC}}]
        report=index_addresses([SOL],fetch=feed)
        self.assertEqual(report["addresses"],[address])
        self.assertNotIn("mints",str(report["addresses"]))
        self.assertFalse(report["broadcast"])

    def test_only_actual_source_owner_assigns_venue(self):
        program=VENUES["orca"][0]
        response={"value":[{"owner":program,"executable":False},
                           {"owner":"forged","executable":False}]}
        with patch("arb.untrusted_pool_index.call",return_value=response) as rpc:
            result=authenticate_owners("rpc",["A"*44,"B"*44])
        self.assertEqual(result["pools"],[{"venue":"orca","address":"A"*44}])
        self.assertEqual(len(result["rejections"]),1)
        self.assertEqual(rpc.call_args.args[1],"getMultipleAccounts")
        with patch("arb.untrusted_pool_index.call",return_value={"value":[None]}):
            with self.assertRaises(ValueError):
                authenticate_owners("rpc",["A"*44,"B"*44])
    def test_index_forgery_and_oversized_batch_fail(self):
        with self.assertRaises(ValueError):
            index_addresses([SOL],max_addresses=200)
        with self.assertRaises(ValueError):
            authenticate_owners("rpc",["A"*44]*121)

if __name__=="__main__":
    unittest.main()
