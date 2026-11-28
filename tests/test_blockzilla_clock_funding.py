import unittest
from arb.signed_cpi_native_funding import audit_funding,SYSTEM,WSOL
from arb.meteora_dlmm_signed_event_audit import stable_execution_timestamp,decode_swap
from arb.pumpswap_source_fee_envelope import selected_directional_model

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class ClockFundingTests(unittest.TestCase):
    def test_clock_requires_stable_timestamp(self):
        a={"slot":7,"unix_timestamp":100}
        self.assertEqual(stable_execution_timestamp({"positive_execution_clock_before":a,
            "positive_execution_clock_after":{"slot":8,"unix_timestamp":100}}),100)
        self.assertIsNone(stable_execution_timestamp({"positive_execution_clock_before":a,
            "positive_execution_clock_after":{"slot":8,"unix_timestamp":101}}))
    def test_real_dlmm_event_minimized(self):
        raw=bytes.fromhex("e445a52e51cb9a1d516ce3becdd00ac456b0dc2ee3d0ad7dd00f340ffa030abace762ff9cd52c13fd08c81ae0461c4ead8063c946de3560c1c299d36a4c3c07959fccba4513a72ba894f343c104527dcdfffffffdfffffffa086010000000000a57405000000000000d007000000000000c800000000000000002d31010000000000000000000000000000000000000000")
        x=decode_swap(raw)
        self.assertEqual((x["amount_in"],x["amount_out"],x["fee"],x["protocol_fee"],x["reported_fee_bps_raw"]),(100000,357541,2000,200,20000000))
    def test_funding_not_paid_fee_or_profit(self):
        response={"err":None,"preBalances":None,"postBalances":None,
            "innerInstructions":[{"index":0,"instructions":[{"programId":SYSTEM,
                "parsed":{"type":"createAccount","info":{"source":"payer","newAccount":"volume",
                    "owner":"pump","space":137,"lamports":1346200}}}]}]}
        x=audit_funding(response,["payer","volume"],"payer",
            {"start_mint":WSOL,"estimated_net_delta_start_mint_base_units":-5310})
        self.assertEqual(x["observed_creation_funding_lamports"],1346200)
        self.assertEqual(x["estimated_net_after_observed_funding_wsol_units"],-1351510)
        self.assertIsNone(x["recorded_payer_native_balance_delta_lamports"])
        self.assertFalse(x["full_wallet_cost_reconciled"])
        response["innerInstructions"][0]["instructions"][0]["parsed"]["info"]["newAccount"]="unknown"
        with self.assertRaisesRegex(ValueError,"signed keys"):
            audit_funding(response,["payer","volume"],"payer",{})
    def test_preselection_does_not_use_observed_output(self):
        e={"status":"PUMPSWAP_SOURCE_FEE_TIER_SCENARIOS_NOT_EXHAUSTIVE",
           "fee_mode_selected_from_source":True,"canonical_source_tier_selection":{
               "status":"PUMP_CANONICAL_SOURCE_MARKET_CAP_TIER_SELECTED","quote_asset":"WSOL",
               "source_tier_account_authenticated":True,"fees":{"lp_fee_bps":20,"protocol_fee_bps":5,"creator_fee_bps":5}},
           "direction":"BUY_WITH_QUOTE","pool":"p","source_slot":1,"input_mint":"a","output_mint":"b","amount_in":100,
           "candidates":[{"tier":"selected_onchain_source_tier","directional_fee_scenarios":[
               {"scenario":"BUY_NET_QUOTE_PLUS_COMPONENT_CEIL_MINUS_ONE","input_budget_unspent_base_units":0,
                "modeled_output_base_units":90,"fee_quote_base_units":3}]}],**SAFE}
        self.assertEqual(selected_directional_model(e)["amount_out"],90)
        e["candidates"][0]["directional_fee_scenarios"][0]["input_budget_unspent_base_units"]=1
        self.assertIsNone(selected_directional_model(e))
if __name__=="__main__":unittest.main()
