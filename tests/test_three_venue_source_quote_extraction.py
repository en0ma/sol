import unittest
from unittest.mock import patch
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_config_quote_projection import quote_cpmm_only
class Tests(unittest.TestCase):
    def fixture(self):
        return {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
         "fixture_kind":"THREE_DISTINCT_VENUE_CLOSED_ROUTE",
         "state_account_addresses":["one","two","three"],
         "state_accounts_observed_slot":42,
         "route_venues":["raydium_cpmm","orca","raydium_amm_v4"],
         "route_pool_addresses":["one","two","three"],
         "route_mints":["A","B","C","A"],
         "accounts":{k:{"owner":o,"executable":False,
                 "data":["AQ==","base64"]} for k,o in [
                 ("one","cpmm"),("two","orca"),("three","v4")]}}
    @patch("arb.fixture_quote_execution_pipeline.verify",return_value=True)
    @patch("arb.fixture_quote_execution_pipeline.PROGRAMS",
           {"raydium_cpmm":"cpmm","orca":"orca","raydium_amm_v4":"v4"})
    @patch("arb.fixture_quote_execution_pipeline.MINT_KEYS",{
        "raydium_cpmm":("a","b"),"orca":("a","b"),"raydium_amm_v4":("a","b")})
    @patch("arb.fixture_quote_execution_pipeline.DECODERS",{
        "raydium_cpmm":lambda raw:{"a":"A","b":"B"},
        "orca":lambda raw:{"a":"B","b":"C"},
        "raydium_amm_v4":lambda raw:{"a":"C","b":"A"}})
    def test_three_real_distinct_source_legs_match_own_token_boundaries(self,*_):
        rows=extract_pool_states(self.fixture())
        self.assertEqual([r["venue"] for r in rows],
            ["raydium_cpmm","orca","raydium_amm_v4"])
        self.assertEqual([r["mints"] for r in rows],
            [["A","B"],["B","C"],["C","A"]])
    @patch("arb.fixture_quote_execution_pipeline.verify",return_value=True)
    @patch("arb.fixture_quote_execution_pipeline.PROGRAMS",
           {"raydium_cpmm":"cpmm","orca":"orca","raydium_amm_v4":"v4"})
    @patch("arb.fixture_quote_execution_pipeline.MINT_KEYS",{
        "raydium_cpmm":("a","b"),"orca":("a","b"),"raydium_amm_v4":("a","b")})
    @patch("arb.fixture_quote_execution_pipeline.DECODERS",{
        "raydium_cpmm":lambda raw:{"a":"A","b":"B"},
        "orca":lambda raw:{"a":"A","b":"C"},
        "raydium_amm_v4":lambda raw:{"a":"C","b":"A"}})
    def test_wrong_second_pool_mint_is_rejected(self,*_):
        with self.assertRaisesRegex(ValueError,"decoded pool mints mismatch"):
            extract_pool_states(self.fixture())
    @patch("arb.fixture_config_quote_projection.derive")
    @patch("arb.fixture_config_quote_projection.from_snapshot")
    def test_cpmm_quote_uses_only_matched_pool_not_unpriced_third_venue(self,provider,derive):
        derive.return_value={"snapshots":[
            {"venue":"raydium_cpmm","address":"one","trade_fee_authenticated":True,
             "mints":["A","B"],"vault_base_units":[10000,20000],"trade_fee_ppm":2500},
            {"venue":"orca","address":"two","trade_fee_authenticated":False},
            {"venue":"raydium_amm_v4","address":"three","trade_fee_authenticated":False}]}
        provider.return_value=(lambda leg,n:{"amount_out":7},{"pool_count":1})
        result=quote_cpmm_only({},observed_unix=12,
            leg={"venue":"raydium_cpmm","pool":"one","input_mint":"A","output_mint":"B"},amount_in=5)
        self.assertEqual(result["quote"]["amount_out"],7)
        self.assertEqual(len(result["native_fee_rounding_reference"]["output_interval_base_units"]),2)
        self.assertEqual(len(provider.call_args.args[0]),1)
        self.assertFalse(result["protocol_exact_verified"])
if __name__=="__main__":unittest.main()
