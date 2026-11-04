import base64
import unittest
from arb.orca_swap_v2_offline_transfer_accounting import reconcile_transfer_simulation

def account(balance):
    raw = bytearray(165)
    raw[64:72] = balance.to_bytes(8, "little")
    raw[108] = 1
    return {"data": [base64.b64encode(raw).decode(), "base64"]}

class SignedTransferAccountingTests(unittest.TestCase):
    def test_exact_transfer_delta(self):
        report = reconcile_transfer_simulation(
            {"err": None, "accounts": [account(999999), account(1)]},
            amount=1, initial_source=1000000, initial_destination=0)
        self.assertTrue(report["post_token_balances_verified"])
        self.assertFalse(report["signed_swap_simulation_verified"])
        self.assertFalse(report["broadcast"])

    def test_balance_mismatch_not_verified(self):
        report = reconcile_transfer_simulation(
            {"err": None, "accounts": [account(1000000), account(0)]},
            amount=1, initial_source=1000000, initial_destination=0)
        self.assertFalse(report["post_token_balances_verified"])

    def test_missing_post_accounts_not_fabricated(self):
        report = reconcile_transfer_simulation(
            {"err": None}, amount=1, initial_source=1000000, initial_destination=0)
        self.assertEqual(report["status"], "POST_ACCOUNTS_NOT_RETURNED")
        self.assertFalse(report["post_token_balances_verified"])

    def test_failed_simulation_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_transfer_simulation(
                {"err": "IncorrectProgramId"}, amount=1,
                initial_source=1000000, initial_destination=0)
