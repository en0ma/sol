import base64
import unittest
from unittest.mock import patch
from arb.orca_whirlpool import (
    PROGRAM, SIZE, DISCRIMINATOR, b58, decode, fetch_pool, find_pair
)

def fixture():
    data = bytearray(SIZE)
    data[:8] = DISCRIMINATOR
    data[41:43] = (64).to_bytes(2, "little")
    data[45:47] = (300).to_bytes(2, "little")
    data[49:65] = (123456789).to_bytes(16, "little")
    data[65:81] = (2**64).to_bytes(16, "little")
    data[81:85] = (-12).to_bytes(4, "little", signed=True)
    data[101:133] = bytes([1])*32
    data[181:213] = bytes([2])*32
    return bytes(data)

class WhirlpoolTests(unittest.TestCase):
    def test_layout(self):
        state = decode(fixture())
        self.assertEqual(state["tick_spacing"], 64)
        self.assertEqual(state["fee_rate_hundredths_bps"], 300)
        self.assertEqual(state["liquidity"], "123456789")
        self.assertEqual(state["sqrt_price_x64"], str(2**64))
        self.assertEqual(state["tick_current_index"], -12)
        self.assertEqual(state["token_mint_a"], b58(bytes([1])*32))

    def test_discriminator_and_size(self):
        with self.assertRaises(ValueError):
            decode(bytes(SIZE))
        with self.assertRaises(ValueError):
            decode(fixture()[:-1])

    @patch("arb.orca_whirlpool.call")
    def test_fetch_rejects_wrong_owner(self, rpc):
        rpc.return_value = {"value": {"owner": "spoof", "data": [base64.b64encode(fixture()).decode(), "base64"]}}
        with self.assertRaises(ValueError):
            fetch_pool("http://127.0.0.1:8899", "PoolAddress")

    @patch("arb.orca_whirlpool.call")
    def test_filtered_rpc_queries_both_mint_orders(self, rpc):
        rpc.return_value = []
        self.assertEqual(find_pair("http://127.0.0.1:8899"), [])
        self.assertEqual(rpc.call_count, 2)
        for call_args in rpc.call_args_list:
            self.assertEqual(call_args.args[1], "getProgramAccounts")
            opts = call_args.args[2][1]
            self.assertEqual(opts["filters"][0], {"dataSize": 653})
            self.assertEqual(opts["filters"][1]["memcmp"]["offset"], 0)
            self.assertEqual(opts["filters"][2]["memcmp"]["offset"], 101)
            self.assertEqual(opts["filters"][3]["memcmp"]["offset"], 181)

    @patch("arb.orca_whirlpool.call")
    def test_cannot_accept_untrusted_candidate(self, rpc):
        rpc.return_value = [{"pubkey": "pool", "account": {"owner": "spoof", "executable": False, "data": [base64.b64encode(fixture()).decode(), "base64"]}}]
        with self.assertRaises(ValueError):
            find_pair("http://127.0.0.1:8899")
