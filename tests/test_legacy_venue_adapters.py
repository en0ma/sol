import unittest
from arb.orca_whirlpool import b58
from arb.token_vaults import TOKEN_PROGRAM
from arb.raydium_amm_v4 import decode as decode_amm
from arb.orca_token_swap_v1 import decode as decode_orca
from arb.orca_token_swap_v1_swap import build_swap

def key(n):
    return b58(bytes([n])*32)

class LegacyVenueAdapterTests(unittest.TestCase):
    def test_raydium_amm_v4_decode_rejects_invalid_state(self):
        with self.assertRaises(ValueError):
            decode_amm(bytes(751))
        with self.assertRaises(ValueError):
            decode_amm(bytes(752))

    def test_raydium_amm_v4_layout(self):
        data=bytearray(752)
        data[0:8]=(6).to_bytes(8,"little")
        data[8:16]=(1).to_bytes(8,"little")
        data[32:40]=(9).to_bytes(8,"little")
        data[40:48]=(6).to_bytes(8,"little")
        for n,offset in enumerate((336,368,400,432,496,528,560,688),1):
            data[offset:offset+32]=bytes([n])*32
        state=decode_amm(bytes(data))
        self.assertEqual(state["base_mint"],key(3))
        self.assertEqual(state["quote_mint"],key(4))
        self.assertEqual(state["status"],6)

    def test_orca_token_swap_v1_decode_and_rejections(self):
        data=bytearray(324)
        data[:3]=bytes([1,1,7])
        from solders.pubkey import Pubkey
        data[3:35]=bytes(Pubkey.from_string(TOKEN_PROGRAM))
        for n,offset in enumerate((35,67,99,131,163),1):
            data[offset:offset+32]=bytes([n])*32
        for offset in (235,251,267,283):
            data[offset:offset+8]=(10000).to_bytes(8,"little")
        state=decode_orca(bytes(data))
        self.assertEqual(state["token_a_mint"],key(4))
        self.assertEqual(state["bump"],7)
        data[0]=2
        with self.assertRaises(ValueError):
            decode_orca(bytes(data))

    def test_orca_swap_builder_exact_input_instruction(self):
        accounts=[key(i) for i in range(1,11)]
        ix=build_swap(*accounts,amount_in=100,min_amount_out=1)
        self.assertEqual(bytes(ix.data),bytes([1])+(100).to_bytes(8,"little")+(1).to_bytes(8,"little"))
        self.assertEqual(len(ix.accounts),10)
        self.assertTrue(ix.accounts[2].is_signer)
        with self.assertRaises(ValueError):
            build_swap(*accounts,amount_in=0,min_amount_out=1)
