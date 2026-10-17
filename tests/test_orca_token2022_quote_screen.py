import unittest
from unittest.mock import patch
from arb.orca_token2022_quote_screen import screen, diagnostic_failure_category

A="So11111111111111111111111111111111111111112"
B="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
POOL="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"
STATE={"token_mint_a":A,"token_mint_b":B}
def observed():
    cfg={"older":{"epoch":0,"basis_points":100,"maximum_fee":1000},
         "newer":{"epoch":4,"basis_points":200,"maximum_fee":1000}}
    return {"pool":STATE,"slot":12,"mints":[A,B],
            "mint_accounts":[{"transfer_fee_config":cfg},{"transfer_fee_config":cfg}],
            "epoch_observation":{"epoch":4},
            "extension_risk":{"blocking_extension_ids":[1]}}
class QuoteScreenTests(unittest.TestCase):
    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_fees_use_single_snapshot_tick_arrays(self,snap,quote):
        state=observed()
        state["tick_arrays"]=[{"start_tick":0,"status":"FIXED_VALID","ticks":[]}]
        snap.return_value=state
        quote.return_value={"estimated_output_base_units":100,"tick_arrays_examined":1,"ticks_crossed":0}
        result=screen("rpc",POOL,A,101)
        self.assertEqual(result["pool_net_input_base_units"],98)
        self.assertEqual(result["recipient_net_output_base_units"],98)
        self.assertIs(quote.call_args.args[3],state["tick_arrays"])
        snap.assert_called_once_with("rpc",POOL,include_ticks=True)
        self.assertFalse(result["actionable"])

    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_missing_synchronized_ticks_fails_closed(self,snap):
        snap.return_value={**observed(),"tick_arrays":[]}
        with self.assertRaisesRegex(ValueError,"synchronized"):
            screen("rpc",POOL,A,100)

    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_default_direction(self,snap,quote):
        snap.return_value={**observed(),"tick_arrays":[{"status":"FIXED_VALID"}]}
        quote.return_value={"estimated_output_base_units":100,"tick_arrays_examined":1,"ticks_crossed":0}
        self.assertEqual(screen("rpc",POOL,None,101)["input_mint"],A)

class QuoteFailureCategoryTests(unittest.TestCase):
    def test_epoch_and_tick_mismatches_stay_distinct(self):
        self.assertEqual(diagnostic_failure_category(
            "epoch observations do not bracket pool snapshot: before_slot=12 snapshot_slot=11"),
            "EPOCH_OR_POOL_SLOT_MISMATCH")
        self.assertEqual(diagnostic_failure_category(
            "tick arrays and mint/vault snapshot are not same-slot: mint_vault_slot=12 tick_slot=13"),
            "TICK_SLOT_MISMATCH")
        self.assertEqual(diagnostic_failure_category("upstream RPC 429 Too Many Requests"),
                         "UPSTREAM_RATE_LIMIT")
        self.assertEqual(diagnostic_failure_category("unknown failure"),"OTHER_UNQUOTABLE")
