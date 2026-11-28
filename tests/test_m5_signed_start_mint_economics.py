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

class AuthenticatedSourceMintFeeConversionTests(unittest.TestCase):
    def receipt(self):
        return SignedStartMintEconomicsTests().receipt()

    def test_native_wsol_to_start_mint_cost_remains_model(self):
        from unittest.mock import patch
        fixture={"route_mints":["RAY",WSOL,"RAY"],
                 "state_accounts_observed_slot":42,**SAFE}
        rows=[{"venue":"raydium_cpmm","address":"p0"},
              {"venue":"orca","address":"p1"}]
        def quote(fixture,*,leg_index,amount_in,observed_unix):
            self.assertEqual((leg_index,amount_in,observed_unix),(1,5000,100))
            return {"quote_status":"SOURCE_BOUND_INDICATIVE",
                    "predicted_output_base_units":250,
                    "venue":"orca","pool":"p1","source_slot":42,**SAFE}
        with patch("arb.fixture_quote_execution_pipeline.extract_pool_states",
                   return_value=rows),patch("arb.fixture_all_venue_signed_quotes.quote_leg",
                                            side_effect=quote):
            result=signed_net_economics(self.receipt(),start_mint="RAY",
                source_slot=42,fixture=fixture,observed_unix=100)
        self.assertEqual(result["estimated_cost_start_mint_base_units"],250)
        self.assertFalse(result["net_profit_verified"])
        self.assertFalse(result["cost_conversion_protocol_exact_verified"])

    def test_cross_slot_fee_conversion_rejected(self):
        fixture={"route_mints":["RAY",WSOL,"RAY"],
                 "state_accounts_observed_slot":41,**SAFE}
        with self.assertRaisesRegex(ValueError,"fee conversion source"):
            signed_net_economics(self.receipt(),start_mint="RAY",
                source_slot=42,fixture=fixture,observed_unix=100)

    def test_no_conversion_source_preserves_unconverted_status(self):
        result=signed_net_economics(self.receipt(),start_mint="RAY",
            source_slot=42)
        self.assertIsNone(result["source_native_fee_conversion"])
        self.assertIsNone(result["estimated_cost_start_mint_base_units"])


class PrimaryEconomicEvidenceTests(unittest.TestCase):
    def test_rank_groups_preserve_units_and_unconverted_costs(self):
        from arb.m5_signed_start_mint_economics import compact_primary_economic_evidence,rank_primary_economic_evidence
        def make(rid,mint,amount,terminal):
            return compact_primary_economic_evidence({"id":rid,"start_mint":mint,
                "source_slot":42,"amount":amount,"fixture_sha256":"fixture",
                "receipt_sha256":"receipt","audit":{"positive_post_balances":[0,0,0,terminal],
                "planned_inputs":[amount,2,3],**SAFE}})
        rows=[make("a","A",100,102),make("b","A",100,105),make("c","B",100,1000000),make("d","A",200,201)]
        report=rank_primary_economic_evidence(rows,expected_ids=["a","b","c","d"])
        self.assertEqual(report["groups"][0]["gross_ranked_ids"],["b","a"])
        self.assertEqual(report["comparable_group_count"],3)
        self.assertEqual(report["unconverted_cost_count"],4)
        self.assertEqual(report["positive_estimated_net_count"],0)
        self.assertFalse(report["net_profit_verified"])
        with self.assertRaisesRegex(ValueError,"net mismatch"):
            rank_primary_economic_evidence([{**rows[0],"estimated_net":1},*rows[1:]],expected_ids=["a","b","c","d"])
