import base64
import unittest
from unittest.mock import patch
from arb.raydium_cpmm import decode,candidates,DISC,SIZE,PROGRAM
from arb.orca_whirlpool import SOL,USDC
class RaydiumCpmmTests(unittest.TestCase):
    def test_decode_and_flags(self):
        b=bytearray(SIZE);b[:8]=DISC
        for i in range(10):b[8+i*32:40+i*32]=bytes([i+1])*32
        b[329]=4
        state=decode(bytes(b))
        self.assertFalse(state["swap_enabled"])
        self.assertEqual(state["status"],4)
    def test_bad_discriminator(self):
        with self.assertRaises(ValueError):decode(bytes(SIZE))
    @patch("arb.raydium_cpmm.call")
    def test_memcmp_filters_and_limits(self,call):
        call.return_value=[]
        self.assertEqual(candidates("rpc"),{})
        self.assertEqual(call.call_count,2)
        args=call.call_args_list[0].args[2][1]
        self.assertEqual(args["filters"][1]["memcmp"]["offset"],168)
        self.assertEqual(args["filters"][2]["memcmp"]["offset"],200)
        with self.assertRaises(ValueError):candidates("rpc",0)
