import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dlmm_bin_preflight import active_bin_array_index,bin_array_pda,check_active_bin_array
from arb.meteora_dlmm import PROGRAM

class DlmmBinPreflightTests(unittest.TestCase):
    def test_signed_floor_not_truncation(self):
        for bin_id,expected in [(-141,-3),(-71,-2),(-70,-1),(-1,-1),(0,0),(69,0),(70,1)]:
            with self.subTest(bin_id=bin_id):
                self.assertEqual(active_bin_array_index(bin_id),expected)

    def test_distinct_signed_pdas(self):
        pool=str(Pubkey.new_unique())
        self.assertNotEqual(bin_array_pda(pool,-1),bin_array_pda(pool,0))
        self.assertNotEqual(bin_array_pda(pool,0),bin_array_pda(pool,1))

    def test_disallows_remote_validator(self):
        with patch("arb.meteora_dlmm_bin_preflight.call") as rpc:
            with self.assertRaises(ValueError):
                check_active_bin_array("https://api.mainnet-beta.solana.com",
                                       str(Pubkey.new_unique()))
            rpc.assert_not_called()
