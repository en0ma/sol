import unittest
from unittest.mock import patch
from arb.orca_swap_v2_offline_probe import run

class OfflineProbeTests(unittest.TestCase):
    @patch("arb.orca_swap_v2_offline_probe.call")
    def test_missing_token_accounts_are_blockers_with_same_slot_evidence(self,call):
        call.return_value={"context":{"slot":42},"value":[None,None]}
        result=run("http://127.0.0.1:8899")
        self.assertEqual(result["status"],"BLOCKED_NO_LOCAL_TOKEN_PAIR")
        self.assertEqual(result["observed_slot"],42)
        self.assertTrue(result["associated_account_creation_required"])
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["actionable"])

    @patch("arb.orca_swap_v2_offline_probe.call")
    def test_missing_slot_fails_closed(self,call):
        call.return_value={"value":[None,None]}
        with self.assertRaisesRegex(ValueError,"context slot"):
            run("http://127.0.0.1:8899")

if __name__=="__main__":
    unittest.main()
