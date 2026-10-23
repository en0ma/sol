import unittest
from unittest.mock import patch
from arb.legacy_pool_discovery import discover,LEGACY_FILTERS

class LegacyPoolDiscoveryTests(unittest.TestCase):
    def test_exact_mint_offsets_and_program_ids(self):
        self.assertEqual(LEGACY_FILTERS["raydium_amm_v4"][2:],(400,432))
        self.assertEqual(LEGACY_FILTERS["orca_token_swap_v1"][2:],(131,163))

    def test_reject_nonlocal_rpc(self):
        with patch("arb.legacy_pool_discovery.call") as rpc:
            with self.assertRaises(ValueError):
                discover("https://api.mainnet-beta.solana.com","raydium_amm_v4")
            rpc.assert_not_called()

    def test_both_mint_orders_filtered(self):
        with patch("arb.legacy_pool_discovery.call",return_value=[]) as rpc:
            self.assertEqual(discover("http://127.0.0.1:8899","raydium_amm_v4",
                                      pairs=[("mintA","mintB")]),[])
            self.assertEqual(rpc.call_count,2)
            first=rpc.call_args_list[0].args[2][1]["filters"]
            second=rpc.call_args_list[1].args[2][1]["filters"]
            self.assertEqual(first[1]["memcmp"]["bytes"],"mintA")
            self.assertEqual(second[1]["memcmp"]["bytes"],"mintB")

    def test_wrong_program_owner_rejected(self):
        bad=[{"pubkey":"account","account":{"owner":"untrusted","executable":False}}]
        with patch("arb.legacy_pool_discovery.call",return_value=bad):
            with self.assertRaisesRegex(ValueError,"mismatched owner"):
                discover("http://127.0.0.1:8899","orca_token_swap_v1")
