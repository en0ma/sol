"""Adversarial tests for the shared seven-venue native quote evidence contract."""
import unittest
from arb.venue_quote_contract import validate

POOL = {"venue":"raydium_cpmm","address":"POOL","mints":["A","B"],"slot":500}
SAFE = {"actionable":False,"live_execution_approved":False,"broadcast":False}

def native_quote():
    return {"venue":"raydium_cpmm","pool":"POOL","input_mint":"A",
            "output_mint":"B","amount_in":100,"amount_out":99,
            "fee_input_units":1,"liquidity_input_units":100000,
            "price_impact_bps":10,"snapshot_slot":500,
            "source_authenticated":True,"observed_unix":999,
            "quote_model":"RAYDIUM_CPMM_NATIVE_SOURCE",**SAFE}

class NativeContractBoundaryTests(unittest.TestCase):
    def check(self, q, expected):
        outcome=validate(q,POOL,requested_input=100,now=1000)
        self.assertEqual(outcome["status"],expected)
        self.assertFalse(outcome["broadcast"])
        self.assertFalse(outcome["actionable"])
        self.assertFalse(outcome["live_execution_approved"])

    def test_source_native_quote_retained_as_indicative(self):
        self.check(native_quote(),"VALIDATED_INDICATIVE_QUOTE")

    def test_boolean_input_is_not_100_raw_units(self):
        q=native_quote()
        q["amount_in"]=True
        self.check(q,"UNASSESSABLE")

    def test_u64_inputs_are_bounded(self):
        q=native_quote()
        outcome=validate(q,POOL,requested_input=2**64,now=1000)
        self.assertEqual(outcome["status"],"UNASSESSABLE")
        self.assertIn("quote exact input mismatch",outcome["reason_codes"])

    def test_all_native_quantity_boundaries(self):
        for field in ("amount_out","fee_input_units","liquidity_input_units","price_impact_bps"):
            for value in (-1,2**64,True):
                with self.subTest(field=field,value=value):
                    q=native_quote()
                    q[field]=value
                    self.check(q,"UNASSESSABLE")

    def test_reject_fake_live_or_broadcast_assertions(self):
        for field in SAFE:
            with self.subTest(field=field):
                q=native_quote()
                q[field]=True
                outcome=validate(q,POOL,requested_input=100,now=1000)
                self.assertEqual(outcome["status"],"UNASSESSABLE")
                self.assertIn("unsafe quote authority assertion",outcome["reason_codes"])

    def test_legacy_internal_quote_may_omit_safe_flags(self):
        q=native_quote()
        for key in SAFE:
            q.pop(key)
        # Absence of a claim is not a claim of authorization.
        # The validated output always supplies explicit safe flags.
        self.check(q,"VALIDATED_INDICATIVE_QUOTE")

if __name__=="__main__":
    unittest.main()
