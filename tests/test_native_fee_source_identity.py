import unittest
from unittest.mock import patch
from arb.m5_captured_fee_compute_audit import diagnose
from arb.source_snapshot_manifest import digest

class NativeAuditIdentityTests(unittest.TestCase):
    def fixture(self):
        accounts={"p":{"owner":"x","data":["AA==","base64"]}}
        return {"accounts":accounts,"state_account_addresses":["p"],"state_account_count":1,
                "state_accounts_observed_slot":21,
                "state_account_manifest_sha256":digest(accounts,["p"],21)}
    def test_decoder_config_identity_cannot_drift(self):
        state=[{"venue":"raydium_clmm","address":"p","snapshot_slot":21,
                "decoded_pool_state":{"amm_config":"cfg"}}]
        fees={"venue":"raydium_clmm","config_address":"wrong","trade_fee_ppm":2500,
              "trade_fee_authenticated":True,"total_effective_fee_authenticated":True,
              "effective_quote_fee_ppm":2500}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fees):
            row=diagnose(self.fixture(),{})["fee_rows"][0]
        self.assertIn("INVALID",row["blocker"])
        self.assertIsNone(row["effective_quote_fee_ppm"])
    def test_decoder_venue_identity_cannot_drift(self):
        state=[{"venue":"raydium_cpmm","address":"p","snapshot_slot":21,
                "decoded_pool_state":{"amm_config":"cfg"}}]
        fees={"venue":"raydium_clmm","config_address":"cfg","trade_fee_ppm":2500,
              "trade_fee_authenticated":True,"total_effective_fee_authenticated":True,
              "effective_quote_fee_ppm":2500}
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=state),patch(
             "arb.m5_captured_fee_compute_audit.decode_native_config_fee",return_value=fees):
            row=diagnose(self.fixture(),{})["fee_rows"][0]
        self.assertFalse(row["trade_fee_authenticated"])
        self.assertIn("INVALID",row["blocker"])
if __name__=="__main__":unittest.main()
