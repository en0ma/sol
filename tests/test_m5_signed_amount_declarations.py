import unittest
from unittest.mock import patch
from arb.m5_signed_fixture_experiment_report import evaluate
from arb.source_snapshot_manifest import digest

class SignedAmountTests(unittest.TestCase):
    def test_unverified_declaration_cannot_override_signed_spl(self):
        accounts={"a":{"owner":"x","data":["AA==","base64"]}}
        fixture={"accounts":accounts,"state_account_addresses":["a"],"state_account_count":1,
                 "state_accounts_observed_slot":4,"state_account_manifest_sha256":digest(accounts,["a"],4),
                 "first_venue":"raydium_cpmm","second_venue":"raydium_amm_v4",
                 "first_pool":"x","second_pool":"y","route_mints":["A","B","A"]}
        receipt={"route_pool_addresses":["x","y"],"route_mints":["A","B","A"],
                 "initial_balances_base_units":[100,0,0],
                 "positive_post_balances_base_units":[0,0,110],
                 "first_leg_intermediate_received_base_units":80,
                 "declared_second_leg_input_base_units":1}
        with patch("arb.m5_signed_fixture_experiment_report.quote_experiment",
                   side_effect=ValueError("blocked")):
            result=evaluate(fixture,receipt,observed_unix=1)
        self.assertEqual(result["observed_legs"][1]["input"],80)
        self.assertIn("DECLARED_SECOND_INPUT_VS_SPL_CONSUMPTION_MISMATCH",result["reason_codes"])
        self.assertTrue(result["full_intermediate_consumption_observed"])
        self.assertFalse(result["broadcast"])
if __name__=="__main__": unittest.main()
