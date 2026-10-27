import unittest
from arb.m5_signed_start_mint_economics import signed_net_economics,WSOL
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class SignedStartMintEconomicsTests(unittest.TestCase):
    def receipt(self):
        return {"state_accounts_observed_slot":42,
            "planned_inputs":[100000,90000,80000,70000],
            "positive_post_balances_base_units":[0,0,0,0,120000],
            "signed_atomic_simulation_verified":True,
            "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
                "estimated_fee_lamports":5000,"fee_payer_asset":"SOL",**SAFE},**SAFE}
    def test_wsol_signer_payer_fee_converted_only_as_estimate(self):
        result=signed_net_economics(self.receipt(),start_mint=WSOL,source_slot=42)
        self.assertEqual(result["observed_local_fork_gross_delta_start_mint_base_units"],20000)
        self.assertEqual(result["estimated_cost_start_mint_base_units"],5000)
        self.assertEqual(result["estimated_net_delta_start_mint_base_units"],15000)
        self.assertFalse(result["net_profit_verified"])
        self.assertFalse(result["paid_network_fee_verified"])
    def test_non_sol_mint_requires_source_conversion(self):
        result=signed_net_economics(self.receipt(),start_mint="non-wsol",source_slot=42)
        self.assertIsNone(result["estimated_cost_start_mint_base_units"])
        self.assertIsNone(result["estimated_net_delta_start_mint_base_units"])
    def test_missing_or_untrusted_fee_never_becomes_zero(self):
        r=self.receipt()
        r["signed_message_fee_estimate"]["broadcast"]=True
        result=signed_net_economics(r,start_mint=WSOL,source_slot=42)
        self.assertIsNone(result["estimated_net_delta_start_mint_base_units"])
        r=self.receipt()
        r["signed_message_fee_estimate"]["estimated_fee_lamports"]=None
        result=signed_net_economics(r,start_mint=WSOL,source_slot=42)
        self.assertIsNone(result["estimated_net_delta_start_mint_base_units"])
    def test_cross_slot_receipt_refused(self):
        with self.assertRaisesRegex(ValueError,"source identity"):
            signed_net_economics(self.receipt(),start_mint=WSOL,source_slot=43)
    def test_incomplete_signed_post_balances_refused(self):
        r=self.receipt()
        r.pop("positive_post_balances_base_units")
        with self.assertRaisesRegex(ValueError,"accounting"):
            signed_net_economics(r,start_mint=WSOL,source_slot=42)
if __name__=="__main__":unittest.main()
