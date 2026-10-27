import unittest
from unittest.mock import patch
from arb.m5_four_to_six_source_signed_acceptance import assess
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class AuthenticatedSignedSourceAcceptanceTests(unittest.TestCase):
    def fixture(self):
        return {"fixture_kind":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE",
            "state_accounts_observed_slot":42,
            "state_account_manifest_sha256":"abc",
            "route_venues":["orca","raydium_cpmm","meteora_dlmm","pumpswap"],
            "route_pool_addresses":["poolA","poolB","poolC","poolD"],
            "route_mints":["A","B","C","D","A"],**SAFE}
    def rows(self):
        return [{"address":"pool"+str(i)} for i in range(4)]
    def receipt(self):
        f=self.fixture()
        return {"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
                "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
                "fixture_kind":f["fixture_kind"],"legs":4,
                "route_venues":f["route_venues"],"route_pool_addresses":f["route_pool_addresses"],
                "route_mints":f["route_mints"],"state_accounts_observed_slot":42,
                "state_account_manifest_sha256":"abc",
                "signed_cpi_per_leg_verified":True,
                "rollback_failure_case_verified":True,
                "signed_atomic_simulation_verified":True,
                "quote_accuracy_verified":False,
                "source_snapshot_slot":None,
                "planned_inputs":[100,90,80,70],
                "signed_prefix_observations":[{"index":i,
                    "venue":f["route_venues"][i],"pool":f["route_pool_addresses"][i],
                    "amount_in":amount,"observed_output":output,
                    "compute_units":15000} for i,(amount,output) in
                    enumerate(((100,90),(90,80),(80,70)))],
                "initial_balances_base_units":[100,0,0,0,0],
                "positive_post_balances_base_units":[0,0,0,0,60],
                "cpi_hops":[{"hop":i,"account":"user_token_"+str(i),
                    "planned_input_base_units":amount,
                    "received_base_units":amount,"consumed_base_units":amount}
                    for i,amount in enumerate((90,80,70),1)],
                "signed_packet_bytes":1100,
                "signed_transaction_sha256":"a"*64,
                "negative_signed_transaction_sha256":"b"*64,
                "signed_transaction_signature":"A"*88,
                "negative_signed_transaction_signature":"B"*88,
                "signed_packet_crypto_bound":True,
                "negative_error":"{'InstructionError': [3, 'Custom']}",
                "negative_failure_instruction_index":3,
                "negative_packet_bytes":1100,
                "hydrated_fork_state_readback":{"status":"HYDRATED_FORK_ACCOUNT_BYTES_MATCH",
                    "accounts_checked":30,"fork_readback_slot":123,
                    "captured_source_slot":42,
                    "source_mainnet_slot_independently_attested":False,**SAFE},**SAFE}
    @patch("arb.m5_four_to_six_source_signed_acceptance.extract_pool_states")
    @patch("arb.m5_four_to_six_source_signed_acceptance.verify")
    def test_source_bound_atomic_receipt_can_pass_without_claiming_profit(self,verify,states):
        states.return_value=self.rows()
        result=assess(self.fixture(),self.receipt())
        self.assertEqual(result["status"],"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK")
        self.assertEqual(result["failure_reasons"],[])
        self.assertFalse(result["net_profit_verified"])
    @patch("arb.m5_four_to_six_source_signed_acceptance.extract_pool_states")
    @patch("arb.m5_four_to_six_source_signed_acceptance.verify")
    def test_receipt_from_unrelated_source_cannot_pass(self,verify,states):
        states.return_value=self.rows()
        r=self.receipt()
        r["state_account_manifest_sha256"]="other"
        self.assertNotEqual(assess(self.fixture(),r)["status"],
                            "VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK")
    @patch("arb.m5_four_to_six_source_signed_acceptance.extract_pool_states")
    @patch("arb.m5_four_to_six_source_signed_acceptance.verify")
    def test_missing_middle_cpi_hop_must_fail(self,verify,states):
        states.return_value=self.rows()
        r=self.receipt()
        r["cpi_hops"][1]["consumed_base_units"]-=1
        self.assertTrue(assess(self.fixture(),r)["failure_reasons"])
    @patch("arb.m5_four_to_six_source_signed_acceptance.extract_pool_states")
    @patch("arb.m5_four_to_six_source_signed_acceptance.verify")
    def test_negative_failure_has_to_be_last_instruction(self,verify,states):
        states.return_value=self.rows()
        r=self.receipt()
        r["negative_error"]="{'InstructionError': [2, 'Custom']}"
        self.assertTrue(assess(self.fixture(),r)["failure_reasons"])
    @patch("arb.m5_four_to_six_source_signed_acceptance.extract_pool_states")
    @patch("arb.m5_four_to_six_source_signed_acceptance.verify")
    def test_replayed_identical_signed_negative_control_rejected(self,verify,states):
        states.return_value=self.rows()
        r=self.receipt()
        r["negative_signed_transaction_sha256"]=r["signed_transaction_sha256"]
        self.assertTrue(assess(self.fixture(),r)["failure_reasons"])
    @patch("arb.m5_four_to_six_source_signed_acceptance.extract_pool_states")
    @patch("arb.m5_four_to_six_source_signed_acceptance.verify")
    def test_fabricated_success_with_live_flag_is_rejected(self,verify,states):
        states.return_value=self.rows()
        r=self.receipt()
        r["broadcast"]=True
        self.assertTrue(assess(self.fixture(),r)["failure_reasons"])
if __name__=="__main__":unittest.main()
