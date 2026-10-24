import importlib.util
import unittest
from arb.orca_whirlpool import b58
from arb.meteora_damm_v2_swap import build_swap2,SWAP2_DISCRIMINATOR

def key(n):
    return b58(bytes([n])*32)

class DammV2SwapBuilderTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("solders"),"solders required for instruction construction")
    def test_swap2_exact_input_idl_layout(self):
        state={"pool_status":0,"token_a_flag":0,"token_b_flag":0,
               "liquidity":10,"sqrt_price":1,
               "token_a_mint":key(1),"token_b_mint":key(2),
               "token_a_vault":key(3),"token_b_vault":key(4)}
        ix=build_swap2(key(5),state,key(6),key(7),key(8),100,2,input_is_a=True)
        self.assertEqual(bytes(ix.data),SWAP2_DISCRIMINATOR+
                         (100).to_bytes(8,"little")+(2).to_bytes(8,"little")+bytes([0]))
        self.assertEqual(len(ix.accounts),14)
        self.assertTrue(ix.accounts[8].is_signer)
        self.assertEqual(str(ix.accounts[11].pubkey),str(ix.program_id))
        with self.assertRaises(ValueError):
            build_swap2(key(5),state,key(6),key(7),key(8),0,2,input_is_a=True)
        with self.assertRaises(ValueError):
            build_swap2(key(5),state,key(6),key(7),key(8),100,2,input_is_a=True,
                        referral_token_account=key(9))
