import unittest
from unittest.mock import patch
from arb.whirlpool_preflight import verify_oracle, preflight

class OracleCompatibilityTests(unittest.TestCase):
    @patch("arb.whirlpool_preflight.oracle_address",return_value="derived-oracle")
    @patch("arb.whirlpool_preflight.call",return_value={"value":None})
    def test_nonadaptive_missing_oracle_allowed(self,call,address):
        self.assertEqual(verify_oracle("rpc","pool",False),"derived-oracle")

    @patch("arb.whirlpool_preflight.oracle_address",return_value="derived-oracle")
    @patch("arb.whirlpool_preflight.call",return_value={"value":None})
    def test_adaptive_missing_oracle_blocked(self,call,address):
        with self.assertRaisesRegex(ValueError,"Adaptive-fee"):
            verify_oracle("rpc","pool",True)

    @patch("arb.whirlpool_preflight.oracle_address",return_value="derived-oracle")
    @patch("arb.whirlpool_preflight.call",return_value={"value":{"owner":"malicious"}})
    def test_wrong_oracle_owner_blocked(self,call,address):
        with self.assertRaises(ValueError):
            verify_oracle("rpc","pool",False)

    @patch("arb.whirlpool_preflight.verify_oracle",return_value="derived")
    @patch("arb.whirlpool_preflight.fetch_pool",return_value={"tick_spacing":8,"fee_tier_index_seed":8})
    @patch("arb.whirlpool_preflight.inspect_swap_requirements",return_value={"directions":{"a_to_b":{"available":False}}})
    def test_missing_arrays_reported(self,inspect,pool,oracle):
        result=preflight("rpc","pool")
        self.assertEqual(result["status"],"BLOCKED_TICK_ARRAYS")
        self.assertFalse(result["swap_success"])
