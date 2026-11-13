import unittest
from unittest.mock import patch
from arb.fixture_native_aux_inventory import inspect

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
class CanonicalPumpSourceAuxiliaryTests(unittest.TestCase):
    def fixture(self,fee_address="FEE",global_address="GLOBAL"):
        return {"state_account_addresses":["POOL",fee_address,global_address],
                "accounts":{"POOL":{"owner":"PUMP","data":["","base64"]},
                            fee_address:{"owner":"FEE_OWNER","executable":False,"data":["AA==","base64"]},
                            global_address:{"owner":"PUMP","executable":False,"data":["AA==","base64"]}},
                "state_accounts_observed_slot":123}
    def row(self):
        return {"venue":"pumpswap","address":"POOL","snapshot_slot":123,
                "decoded_pool_state":{"protocol_fees":1,"creator_fees":1,
                   "virtual_quote_reserves":2,"base_mint":"A","quote_mint":"B"}}
    @patch("arb.pumpswap_global_config.ADDRESS","GLOBAL")
    @patch("arb.pumpswap_pool.PROGRAM","PUMP")
    @patch("arb.pumpswap_global_config.decode")
    @patch("arb.pumpswap_fee_account.decode_authenticated")
    @patch("arb.pumpswap_fee_account.authenticated_address",return_value=("FEE",254))
    @patch("arb.fixture_pool_fundamentals.extract")
    @patch("arb.fixture_native_aux_inventory.extract_pool_states")
    @patch("arb.fixture_native_aux_inventory.verify")
    def test_canonical_source_account_decode_is_not_effective_fee_proof(
        self,verify,states,fundamentals,address,decode_fee,decode_global):
        states.return_value=[self.row()]
        fundamentals.return_value={"fundamentals":[{"venue":"pumpswap","address":"POOL",
            "vault_base_units":[1000,1000]}]}
        decode_fee.return_value={"flat_fees":{"lp_fee_bps":10},"fee_tiers":[{}],
                                 "stable_fee_tiers":[]}
        decode_global.return_value={"lp_fee_bps":10,"protocol_fee_bps":20,
                  "coin_creator_fee_bps":30,"buy_enabled":True,"sell_enabled":True}
        result=inspect(self.fixture())
        record=result["venues"][0]
        self.assertEqual([x["type"] for x in record["decoded_auxiliary"]],
            ["pool_net_quote_liquidity","canonical_pump_fee_config","pump_global_config"])
        self.assertIn("source_authenticated_market_cap_fee_tier_and_fee_mode",record["missing"])
        self.assertFalse(record["fully_priced"])
        self.assertFalse(result["full_native_fee_pricing_verified"])
        decode_fee.assert_called_once()
        decode_global.assert_called_once()
    @patch("arb.pumpswap_global_config.ADDRESS","GLOBAL")
    @patch("arb.pumpswap_pool.PROGRAM","PUMP")
    @patch("arb.pumpswap_fee_account.decode_authenticated",return_value={"flat_fees":{},"fee_tiers":[],"stable_fee_tiers":[]})
    @patch("arb.pumpswap_fee_account.authenticated_address",return_value=("FEE",254))
    @patch("arb.fixture_pool_fundamentals.extract")
    @patch("arb.fixture_native_aux_inventory.extract_pool_states")
    @patch("arb.fixture_native_aux_inventory.verify")
    def test_forged_global_owner_refused(self,verify,states,fundamentals,address,decode_fee):
        states.return_value=[self.row()]
        fundamentals.return_value={"fundamentals":[{"venue":"pumpswap","address":"POOL",
            "vault_base_units":[1000,1000]}]}
        fixture=self.fixture()
        fixture["accounts"]["GLOBAL"]["owner"]="NOT_PUMP"
        with self.assertRaisesRegex(ValueError,"global config source owner"):
            inspect(fixture)

if __name__=="__main__":unittest.main()
