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
    @patch("arb.orca_token2022_quote_screen.inspect")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_both_transfer_fees_with_exact_slot(self,snap,ticks,quote):
        snap.return_value=observed()
        ticks.return_value={"pool":POOL,"pool_state":STATE,"slot":12,"arrays":[{"validated":True}]}
        quote.return_value={"estimated_output_base_units":100,"tick_arrays_examined":1,"ticks_crossed":0}
        result=screen("rpc",POOL,A,101)
        self.assertEqual(result["pool_net_input_base_units"],98)
        self.assertEqual(quote.call_args.args[2],98)
        self.assertEqual(result["recipient_net_output_base_units"],98)
        self.assertFalse(result["executable_quote"])
        self.assertFalse(result["simulation_verified"])
        self.assertFalse(result["actionable"])

    @patch("arb.orca_token2022_quote_screen.inspect")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_different_slot_cannot_quote(self,snap,ticks):
        snap.return_value=observed()
        ticks.return_value={"pool":POOL,"pool_state":STATE,"slot":13}
        with self.assertRaisesRegex(ValueError,"same-slot"):
            screen("rpc",POOL,A,100)

    @patch("arb.orca_token2022_quote_screen.inspect")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_changed_pool_cannot_quote(self,snap,ticks):
        snap.return_value=observed()
        ticks.return_value={"pool":POOL,"pool_state":{"changed":True},"slot":12}
        with self.assertRaisesRegex(ValueError,"changed"):
            screen("rpc",POOL,A,100)

    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.inspect")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_diagnostic_default_mint_uses_one_snapshot(self,snap,ticks,quote):
        snap.return_value=observed()
        ticks.return_value={"pool":POOL,"pool_state":STATE,"slot":12,"arrays":[{"validated":True}]}
        quote.return_value={"estimated_output_base_units":100,"tick_arrays_examined":1,"ticks_crossed":0}
        result=screen("rpc",POOL,None,101)
        self.assertEqual(result["input_mint"],A)
        snap.assert_called_once_with("rpc",POOL)

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
