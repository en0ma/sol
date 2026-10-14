import unittest
from unittest.mock import patch
from arb.whirlpool_preflight import verify_oracle, preflight

class PreflightTests(unittest.TestCase):
    @patch("arb.whirlpool_preflight.oracle_address",return_value="oracle")
    @patch("arb.whirlpool_preflight.call")
    def test_reject_missing_oracle(self,call,addr):
        call.return_value={"value":None}
        with self.assertRaises(ValueError):verify_oracle("rpc","pool",True)

    @patch("arb.whirlpool_preflight.verify_oracle",return_value="oracle")
    @patch("arb.whirlpool_preflight.fetch_pool",return_value={"tick_spacing":8,"fee_tier_index_seed":8})
    @patch("arb.whirlpool_preflight.inspect_swap_requirements")
    def test_missing_arrays_block(self,inspect,pool,oracle):
        inspect.return_value={"directions":{"a_to_b":{"available":False}}}
        report=preflight("rpc","pool")
        self.assertFalse(report["swap_success"])
        self.assertEqual(report["status"],"BLOCKED_TICK_ARRAYS")
