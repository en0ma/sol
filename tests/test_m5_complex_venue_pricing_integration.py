import unittest
from unittest.mock import patch
from arb.pumpswap_source_fee_envelope import quote_fee_candidates
from arb.meteora_damm_v2_source_scenarios import scenario_envelope
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

class ComplexVenuePricingIntegrationTests(unittest.TestCase):
    @patch("arb.pumpswap_source_fee_envelope.verify")
    @patch("arb.pumpswap_source_fee_envelope.extract_pool_states")
    @patch("arb.pumpswap_source_fee_envelope.extract")
    @patch("arb.pumpswap_source_fee_envelope.authenticated_address")
    @patch("arb.pumpswap_source_fee_envelope.decode_authenticated")
    @patch("arb.pumpswap_source_fee_envelope.global_decode")
    def test_pumpswap_real_account_mode_envelope_cannot_upgrade_effective_fee(
            self,global_decode,fees,address,extract,rows,verify):
        from arb.pumpswap_source_fee_envelope import ADDRESS
        address.return_value=("fee-account",255)
        rows.return_value=[{"venue":"pumpswap","address":"pool",
            "decoded_pool_state":{"base_mint":"X","quote_mint":"Y",
             "protocol_fees":50,"creator_fees":20,"virtual_quote_reserves":100}}]
        extract.return_value={"fundamentals":[{"address":"pool","vault_base_units":[1000,2000]}]}
        fees.return_value={"flat_fees":{"lp_fee_bps":10,"protocol_fee_bps":20,
                             "creator_fee_bps":30},"exotic_flat_fees":{"lp_fee_bps":0,
                             "protocol_fee_bps":20,"creator_fee_bps":10},
                           "fee_tiers":[{"market_cap_threshold":100,
                             "fees":{"lp_fee_bps":5,"protocol_fee_bps":15,
                                     "creator_fee_bps":10}}],"stable_fee_tiers":[]}
        global_decode.return_value={"lp_fee_bps":10,"protocol_fee_bps":10,
            "coin_creator_fee_bps":10,"sell_enabled":True,"buy_enabled":True}
        fixture={"state_accounts_observed_slot":123,"state_account_addresses":["fee-account",ADDRESS],
            "accounts":{"fee-account":{"owner":"pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
                "executable":False,"data":["AA==","base64"]},ADDRESS:{"owner":"6EF8rrecthR5Dkzon8Nwu78jEVPUzPyTXc6crF6uAjpm",
                "executable":False,"data":["AA==","base64"]}},**SAFE}
        with patch("arb.pumpswap_source_fee_envelope.PROGRAM","6EF8rrecthR5Dkzon8Nwu78jEVPUzPyTXc6crF6uAjpm"):
            result=quote_fee_candidates(fixture,pool="pool",mint_in="X",amount_in=100)
        self.assertGreater(result["candidate_count"],1)
        self.assertLessEqual(result["minimum_candidate_output"],result["maximum_candidate_output"])
        self.assertFalse(result["effective_fee_verified"])
        self.assertFalse(result["protocol_exact_verified"])
    @patch("arb.meteora_damm_v2_source_scenarios.verify")
    @patch("arb.meteora_damm_v2_source_scenarios.extract_pool_states")
    @patch("arb.meteora_damm_v2_source_scenarios.quote_pool_account",
           return_value={"amount_out":999})
    def test_damm_source_uses_only_official_sdk(self,quote,rows,verify):
        rows.return_value=[{"venue":"meteora_damm_v2","address":"pool"}]
        result=scenario_envelope({"state_accounts_observed_slot":123,
            "accounts":{"pool":{"data":["AA==","base64"]}},**SAFE},
            pool="pool",mint_in="X",amount_in=100000,observed_unix=1000)
        self.assertEqual(result["amount_out"],999)
        self.assertEqual(result["native_pricing_engine"],"OFFICIAL_METEORA_RUST_SDK")
        self.assertFalse(result["signed_execution_parity_verified"])
        self.assertTrue(quote.called)
    @patch("arb.meteora_damm_v2_source_scenarios.verify")
    @patch("arb.meteora_damm_v2_source_scenarios.extract_pool_states")
    def test_damm_rejects_missing_real_fork_clock(self,rows,verify):
        rows.return_value=[{"venue":"meteora_damm_v2","address":"pool"}]
        with self.assertRaisesRegex(ValueError,"observed fork unix"):
            scenario_envelope({"state_accounts_observed_slot":123,**SAFE},
                pool="pool",mint_in="X",amount_in=10)
if __name__=="__main__":unittest.main()
