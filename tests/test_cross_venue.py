import unittest
from arb.raydium_swap import encode
from arb.orca_whirlpool import SOL,USDC,PROGRAM as ORCA
from arb.raydium_cpmm import PROGRAM as RAYDIUM
from arb.cross_venue import measure
class CrossVenueTests(unittest.TestCase):
    def test_both_venues_required(self):
        with self.assertRaisesRegex(ValueError,"venue invocation missing"):
            measure({"err":None,"logs":["Program "+ORCA+" invoke [1]",
                "Program "+ORCA+" success"],"accounts":[]},100)
    def test_failure_rejected(self):
        with self.assertRaisesRegex(ValueError,"simulation errored"):
            measure({"err":{"InstructionError":[1,1]}},100)
    def test_reverse_swap_payload(self):
        self.assertEqual(len(encode(10000,1)),24)
