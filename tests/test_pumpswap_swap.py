import importlib.util
import unittest
from arb.orca_whirlpool import b58
from arb.pumpswap_swap import build_swap_v2,BUY_V2,SELL_V2

def key(n):
    return b58(bytes([n])*32)

class PumpSwapV2BuilderTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("solders"),"solders required for instruction construction")
    def test_buy_sell_v2_idl_encoding(self):
        state={"base_mint":key(1),"quote_mint":key(2),
               "base_vault":key(3),"quote_vault":key(4),
               "is_mayhem_mode":0,"is_cashback_coin":0}
        for buy,disc in ((True,BUY_V2),(False,SELL_V2)):
            ix=build_swap_v2(key(5),state,key(6),key(7),key(8),
                             key(9),key(10),100,2,buy=buy)
            self.assertEqual(bytes(ix.data),disc+
                (100).to_bytes(8,"little")+(2).to_bytes(8,"little"))
            self.assertEqual(len(ix.accounts),17)
            self.assertTrue(ix.accounts[1].is_signer)
            with self.assertRaises(ValueError):
                build_swap_v2(key(5),state,key(6),key(7),key(8),
                              key(9),key(10),0,2,buy=buy)
