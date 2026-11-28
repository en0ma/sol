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


class MultilegFeeConversionTests(unittest.TestCase):
    def test_forward_same_source_suffix_and_no_reverse_guess(self):
        from unittest.mock import patch
        fixture={"route_mints":["RAY",WSOL,"USDC","RAY"],
            "state_accounts_observed_slot":42,**SAFE}
        rows=[{"venue":"orca","address":"p0"},{"venue":"raydium_cpmm","address":"p1"},
              {"venue":"orca","address":"p2"}]
        seen=[]
        def quote(fixture,*,leg_index,amount_in,observed_unix):
            seen.append((leg_index,amount_in))
            row=rows[leg_index]
            return {"quote_status":"SOURCE_BOUND_INDICATIVE","predicted_output_base_units":amount_in//10,
                "venue":row["venue"],"pool":row["address"],"source_slot":42,**SAFE}
        with patch("arb.fixture_quote_execution_pipeline.extract_pool_states",return_value=rows),patch(
                "arb.fixture_all_venue_signed_quotes.quote_leg",side_effect=quote):
            result=signed_net_economics(SignedStartMintEconomicsTests().receipt(),start_mint="RAY",
                source_slot=42,fixture=fixture,observed_unix=100)
        self.assertEqual(seen,[(1,5000),(2,500)])
        self.assertEqual(result["estimated_cost_start_mint_base_units"],50)
        self.assertEqual(len(result["source_native_fee_conversion"]["conversion_legs"]),2)
        self.assertFalse(result["net_profit_verified"])


class SourceFeeModelReuseTests(unittest.TestCase):
    def test_damm_native_fee_conversion_reuses_existing_quote(self):
        from unittest.mock import patch
        from arb.m5_signed_start_mint_economics import source_native_fee_conversion
        fixture={"route_mints":["RAY",WSOL,"RAY"],"state_accounts_observed_slot":42,**SAFE}
        rows=[{"venue":"orca","address":"p0"},{"venue":"meteora_damm_v2","address":"p1"}]
        with patch("arb.fixture_quote_execution_pipeline.extract_pool_states",return_value=rows),patch(
                "arb.fixture_all_venue_signed_quotes.quote_leg",return_value={"quote_status":"SOURCE_BOUND_INDICATIVE",
                 "predicted_output_base_units":250,"venue":"meteora_damm_v2","pool":"p1","source_slot":42,**SAFE}) as quote:
            cost,proof,_=source_native_fee_conversion(fixture,start_mint="RAY",source_slot=42,
                fee_lamports=5000,observed_unix=100)
            self.assertEqual(cost,250)
            self.assertEqual(proof["source_fee_lamports"],5000)
            self.assertFalse(proof["paid_fee_verified"])
            quote.assert_called_once_with(fixture,leg_index=1,amount_in=5000,observed_unix=100)

class SelectedResearchFeeConversionTests(unittest.TestCase):
    def fixture(self,venue):
        return ({"route_mints":["RAY",WSOL,"RAY"],
                 "state_accounts_observed_slot":42,**SAFE},
                [{"venue":"orca","address":"p0"},
                 {"venue":venue,"address":"p1"}])

    def dlmm_quote(self):
        return {"venue":"meteora_dlmm","pool":"p1","source_slot":42,
            "quote_status":"NATIVE_QUOTE_SOURCE_DERIVED_NOT_EXACT",
            "predicted_output_base_units":None,
            "native_fee_envelope":{"pool":"p1","source_slot":42,
                "input_mint":WSOL,"output_mint":"RAY","input_base_units":5000,
                "source_derived_dynamic_fee_quote":{
                    "status":"SOURCE_VOLATILITY_DYNAMIC_FEE_MODELED",
                    "source_clock":100,"amount_out":250,
                    "protocol_exact_verified":False,**SAFE}},**SAFE}

    def convert(self,fixture,rows,quote):
        from unittest.mock import patch
        from arb.m5_signed_start_mint_economics import source_native_fee_conversion
        with patch("arb.fixture_quote_execution_pipeline.extract_pool_states",return_value=rows),patch(
                "arb.fixture_all_venue_signed_quotes.quote_leg",return_value=quote):
            return source_native_fee_conversion(fixture,start_mint="RAY",
                source_slot=42,fee_lamports=5000,observed_unix=100)

    def test_dlmm_fee_conversion_uses_original_clock_model_only(self):
        fixture,rows=self.fixture("meteora_dlmm")
        amount,proof,_=self.convert(fixture,rows,self.dlmm_quote())
        self.assertEqual(amount,250)
        self.assertTrue(proof["uses_unverified_dynamic_fee_model"])
        self.assertFalse(proof["protocol_exact_verified"])
        self.assertFalse(proof["paid_fee_verified"])
        self.assertFalse(proof["conversion_is_guaranteed_upper_bound"])
        for key,value in (("source_clock",101),("protocol_exact_verified",True),
                          ("broadcast",True)):
            q=self.dlmm_quote()
            q["native_fee_envelope"]["source_derived_dynamic_fee_quote"][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.convert(fixture,rows,q)

    def test_pumpswap_requires_source_selected_direction_and_full_input(self):
        from unittest.mock import patch
        fixture,rows=self.fixture("pumpswap")
        q={"venue":"pumpswap","pool":"p1","source_slot":42,
            "quote_status":"NATIVE_QUOTE_SELECTED_FEE_MODE_NOT_EXACT",
            "predicted_output_base_units":None,"native_fee_envelope":{},**SAFE}
        chosen={"pool":"p1","source_slot":42,"input_mint":WSOL,
                "output_mint":"RAY","amount_in":5000,"amount_out":220,**SAFE}
        with patch("arb.pumpswap_source_fee_envelope.selected_directional_model",
                   return_value=None):
            self.assertIsNone(self.convert(fixture,rows,q)[0])
        with patch("arb.pumpswap_source_fee_envelope.selected_directional_model",
                   return_value=chosen):
            amount,proof,_=self.convert(fixture,rows,q)
            self.assertEqual(amount,220)
            self.assertTrue(proof["uses_unverified_dynamic_fee_model"])
            self.assertFalse(proof["paid_fee_verified"])
        for key,value in (("input_mint","RAY"),("source_slot",43),("amount_in",4999)):
            with self.subTest(key=key),patch(
                    "arb.pumpswap_source_fee_envelope.selected_directional_model",
                    return_value={**chosen,key:value}),self.assertRaises(ValueError):
                self.convert(fixture,rows,q)

    def test_ambiguous_fee_scenarios_remain_unconverted(self):
        fixture,rows=self.fixture("pumpswap")
        q={"venue":"pumpswap","pool":"p1","source_slot":42,
            "quote_status":"NATIVE_QUOTE_MODELED_NOT_EXACT",
            "predicted_output_base_units":999,"native_fee_envelope":{},**SAFE}
        self.assertIsNone(self.convert(fixture,rows,q)[0])
