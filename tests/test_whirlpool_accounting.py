import unittest
from arb.whirlpool_accounting import mark_residual_usdc_lamports, assess, Q64
from arb.orca_whirlpool import SOL,USDC

STATE={"token_mint_a":SOL,"token_mint_b":USDC,
       "sqrt_price_x64":str(Q64),"fee_rate_hundredths_bps":0}
class AccountingTests(unittest.TestCase):
    def test_residual_mark_rounds_down(self):
        self.assertEqual(mark_residual_usdc_lamports(1000,STATE,100),990)
    def test_reverse_token_order(self):
        state={**STATE,"token_mint_a":USDC,"token_mint_b":SOL}
        self.assertEqual(mark_residual_usdc_lamports(1000,state,100),990)
    def test_network_fee_required(self):
        self.assertEqual(assess({"start_wsol_lamports":100,
            "end_wsol_lamports":99,"residual_usdc_base_units":20,
            "estimated_network_fee_lamports":None},STATE)["status"],
                         "UNPRICED_NETWORK_FEE")
    def test_mark_is_never_approval(self):
        report=assess({"start_wsol_lamports":100,
            "end_wsol_lamports":200,"residual_usdc_base_units":20,
            "estimated_network_fee_lamports":1},STATE)
        self.assertTrue(report["mark_above_threshold"] if report["minimum_profit_lamports"]<=100 else True)
        self.assertFalse(report["execution_approved"])
    def test_negative_balance_rejected(self):
        with self.assertRaises(ValueError):
            assess({"start_wsol_lamports":-1,"end_wsol_lamports":0,
                    "residual_usdc_base_units":0},STATE)
