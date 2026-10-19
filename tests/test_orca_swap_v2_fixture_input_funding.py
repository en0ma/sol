import unittest
from arb.orca_swap_v2_fixture_input_funding import check_fixture_input_funding

def evidence():
    return {"status": "FIXTURE_USER_ACCOUNTS_READBACK_VERIFIED",
            "observed_balances_base_units": [100, 200],
            "balance_snapshot_slot": 42, "user_account_snapshot_slot": 42}

class FixtureFundingTests(unittest.TestCase):
    def test_directional_input_balance(self):
        a = check_fixture_input_funding(evidence(), a_to_b=True, required_amount=100)
        b = check_fixture_input_funding(evidence(), a_to_b=False, required_amount=201)
        self.assertTrue(a["input_balance_sufficient_for_gross_amount"])
        self.assertFalse(b["input_balance_sufficient_for_gross_amount"])
        self.assertFalse(a["fee_and_rent_coverage_verified"])
        self.assertFalse(a["signed_simulation_verified"])
        self.assertFalse(a["broadcast"])

    def test_invalid_context_and_amount_fail_closed(self):
        cases = [
            ({"status": "MISSING"}, True, 1),
            ({"status": "FIXTURE_USER_ACCOUNTS_READBACK_VERIFIED"}, True, 1),
            (evidence(), True, 0),
            (evidence(), 1, 1),
        ]
        for report, direction, amount in cases:
            with self.subTest(report=report, amount=amount), self.assertRaises(ValueError):
                check_fixture_input_funding(report, a_to_b=direction, required_amount=amount)
        bad=evidence()
        bad["balance_snapshot_slot"]=43
        with self.assertRaises(ValueError):
            check_fixture_input_funding(bad, a_to_b=True, required_amount=1)
