import unittest
from unittest.mock import patch
from arb.m5_captured_fee_compute_audit import diagnose
from arb.source_snapshot_manifest import digest

def fixture():
    accounts={"pool":{"data":["AA==","base64"],"owner":"x"}}
    return {"accounts":accounts,"state_account_addresses":["pool"],"state_account_count":1,
        "state_accounts_observed_slot":30,"state_account_manifest_sha256":digest(accounts,["pool"],30)}

class Tests(unittest.TestCase):
    def test_creator_fee_blocked_but_original_rate_retained(self):
        f=fixture()
        state=[{"venue":"raydium_cpmm","address":"pool","snapshot_slot":30,"decoded_pool_state":{"amm_config":"cfg"}}]
        fee={"config_address":"cfg","trade_fee_ppm":2500,"creator_fee_ppm":100,
             "trade_fee_authenticated":True,"total_effective_fee_authenticated":False,
             "creator_fee_placement_verified":False}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state), \
             patch("arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fee):
            result=diagnose(f,{"positive_units_consumed":12345})
        self.assertEqual(result["fee_rows"][0]["creator_fee_ppm"],100)
        self.assertEqual(result["fee_rows"][0]["blocker"],"CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED")
        self.assertEqual(result["positive_units_consumed"],12345)
        self.assertEqual(result["compute_headroom_units"],1_400_000-12345)
        self.assertIsNone(result["fee_rows"][0]["effective_quote_fee_ppm"])
        self.assertEqual(result["compute_source"],"SIGNED_OFFLINE_SIMULATE_TRANSACTION_RECEIPT")
        self.assertFalse(result["network_fee_lamports_verified"])
        self.assertFalse(result["start_mint_fee_cost_verified"])
        self.assertFalse(result["broadcast"])
    def test_clmm_native_fee_evidence_preserved_without_quote_claim(self):
        f=fixture()
        state=[{"venue":"raydium_clmm","address":"pool","snapshot_slot":30,
                "decoded_pool_state":{"amm_config":"clmmcfg","tick_spacing":16}}]
        fee={"config_address":"clmmcfg","trade_fee_ppm":2500,
             "trade_fee_authenticated":True,"total_effective_fee_authenticated":True,
             "effective_quote_fee_ppm":2500}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fee) as decoder:
            result=diagnose(f,{"positive_units_consumed":150000})
        decoder.assert_called_once_with("raydium_clmm",state[0]["decoded_pool_state"],f)
        self.assertEqual(result["fee_rows"][0]["effective_quote_fee_ppm"],2500)
        self.assertIsNone(result["fee_rows"][0]["creator_fee_ppm"])
        self.assertFalse(result["quote_accuracy_verified"])
        self.assertFalse(result["start_mint_fee_cost_verified"])
    def test_clmm_invalid_config_cannot_be_authenticated(self):
        f=fixture()
        state=[{"venue":"raydium_clmm","address":"pool","snapshot_slot":30,
                "decoded_pool_state":{"amm_config":"clmmcfg"}}]
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",side_effect=ValueError("invalid tick spacing")):
            result=diagnose(f,{})
        self.assertFalse(result["fee_rows"][0]["total_effective_fee_authenticated"])
        self.assertIn("INVALID",result["fee_rows"][0]["blocker"])
    def test_unverified_fee_must_not_publish_effective_ppm(self):
        f=fixture()
        state=[{"venue":"raydium_cpmm","address":"pool","snapshot_slot":30,"decoded_pool_state":{}}]
        fee={"config_address":"cfg","trade_fee_ppm":2500,"creator_fee_ppm":100,
             "trade_fee_authenticated":True,"total_effective_fee_authenticated":False,
             "creator_fee_placement_verified":False,"effective_quote_fee_ppm":2600}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fee):
            report=diagnose(f,{})
        self.assertIn("INVALID",report["fee_rows"][0]["blocker"])
        self.assertIsNone(report["fee_rows"][0].get("effective_quote_fee_ppm"))
        self.assertFalse(report["fee_rows"][0]["trade_fee_authenticated"])
        self.assertFalse(report["fee_rows"][0]["total_effective_fee_authenticated"])
    def test_authenticated_fee_must_have_numeric_ppm(self):
        f=fixture()
        state=[{"venue":"raydium_clmm","address":"pool","snapshot_slot":30,"decoded_pool_state":{}}]
        fee={"config_address":"cfg","trade_fee_ppm":2500,
             "trade_fee_authenticated":True,"total_effective_fee_authenticated":True,
             "effective_quote_fee_ppm":None}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fee):
            report=diagnose(f,{})
        self.assertFalse(report["fee_rows"][0]["total_effective_fee_authenticated"])
        self.assertIn("INVALID",report["fee_rows"][0]["blocker"])
    def test_partial_decoded_fee_conflict_not_leaked(self):
        f=fixture()
        state=[{"venue":"raydium_cpmm","address":"pool","snapshot_slot":30,"decoded_pool_state":{}}]
        fee={"config_address":"cfg","trade_fee_ppm":2200,"creator_fee_ppm":100,
             "trade_fee_authenticated":True,"total_effective_fee_authenticated":False,
             "creator_fee_placement_verified":False,"effective_quote_fee_ppm":2300}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fee):
            result=diagnose(f,{})
        row=result["fee_rows"][0]
        self.assertFalse(row["trade_fee_authenticated"])
        self.assertFalse(row["total_effective_fee_authenticated"])
        self.assertNotIn("trade_fee_ppm",row)
        self.assertIsNone(row["effective_quote_fee_ppm"])
    def test_duplicate_pool_fee_source_rejected(self):
        f=fixture()
        state={"venue":"raydium_cpmm","address":"pool","snapshot_slot":30,"decoded_pool_state":{}}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=[state,state]):
            with self.assertRaisesRegex(ValueError,"duplicate"):
                diagnose(f,{})
    def test_missing_compute_is_not_zero(self):
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=[]):
            result=diagnose(fixture(),{})
        self.assertIsNone(result["positive_units_consumed"])
        self.assertIsNone(result["compute_headroom_units"])
        self.assertEqual(result["compute_blocker"],"SIGNED_POSITIVE_COMPUTE_MISSING_OR_OVER_LIMIT")
    def test_positive_compute_budget_bounds(self):
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=[]):
            for candidate in (None,0,-1,True,1_400_001,"1200"):
                with self.subTest(candidate=candidate):
                    result=diagnose(fixture(),{"positive_units_consumed":candidate})
                    self.assertIsNone(result["positive_units_consumed"])
                    self.assertEqual(result["compute_blocker"],"SIGNED_POSITIVE_COMPUTE_MISSING_OR_OVER_LIMIT")
            for candidate in (1,1_400_000):
                result=diagnose(fixture(),{"positive_units_consumed":candidate})
                self.assertEqual(result["positive_units_consumed"],candidate)
    def test_invalid_source_manifest_not_accepted(self):
        f=fixture();f["state_account_manifest_sha256"]="bad"
        with self.assertRaises(ValueError):diagnose(f,{})
if __name__=="__main__":unittest.main()
