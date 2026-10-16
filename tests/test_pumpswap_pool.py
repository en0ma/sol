import hashlib
import unittest
from unittest.mock import patch
from arb.pumpswap_pool import BASE_LEN, DISC, decode, verify, PROGRAM
from arb.orca_whirlpool import b58

def raw_pool(virtual=0):
    raw=bytearray(261)
    raw[:8]=DISC
    for offset,val in ((11,1),(43,2),(75,3),(107,4),(139,5),(171,6),(211,7)):
        raw[offset:offset+32]=bytes([val])*32
    raw[203:211]=(12345).to_bytes(8,"little")
    raw[245:261]=virtual.to_bytes(16,"little",signed=True)
    return bytes(raw)

class PumpSwapPoolTests(unittest.TestCase):
    def test_decode_base_and_signed_extension(self):
        state=decode(raw_pool(-100))
        self.assertEqual(state["virtual_quote_reserves"],-100)
        self.assertEqual(state["base_mint"],b58(bytes([2])*32))
        self.assertEqual(state["quote_vault"],b58(bytes([6])*32))
        self.assertEqual(decode(raw_pool()[:BASE_LEN])["virtual_quote_reserves"],0)

    def test_reject_truncated_or_corrupt_layouts(self):
        for raw in (raw_pool()[:244],raw_pool()[:250],
                    bytes(261),raw_pool()[:8]+bytes(200)):
            with self.subTest(length=len(raw)):
                with self.assertRaises(ValueError):
                    decode(raw)

    @patch("arb.pumpswap_pool.call")
    def test_missing_rpc_snapshot_fails_closed(self, call):
        state=decode(raw_pool())
        call.return_value={"context":{"slot":100},"value":[None,None,None]}
        with self.assertRaisesRegex(ValueError,"owner or state"):
            verify("rpc","pool",state)
        call.return_value={"context":{},"value":[None,None,None]}
        with self.assertRaisesRegex(ValueError,"incomplete"):
            verify("rpc","pool",state)
