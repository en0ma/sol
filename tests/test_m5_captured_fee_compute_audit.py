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
        self.assertEqual(result["compute_source"],"SIGNED_OFFLINE_SIMULATE_TRANSACTION_RECEIPT")
        self.assertFalse(result["network_fee_lamports_verified"])
        self.assertFalse(result["start_mint_fee_cost_verified"])
        self.assertFalse(result["broadcast"])
    def test_missing_compute_is_not_zero(self):
        with patch("arb.m5_captured_fee_compute_audit.extract_pool_states",return_value=[]):
            result=diagnose(fixture(),{})
        self.assertIsNone(result["positive_units_consumed"])
        self.assertEqual(result["compute_blocker"],"POSITIVE_COMPUTE_UNAVAILABLE")
    def test_invalid_source_manifest_not_accepted(self):
        f=fixture();f["state_account_manifest_sha256"]="bad"
        with self.assertRaises(ValueError):diagnose(f,{})
if __name__=="__main__":unittest.main()
