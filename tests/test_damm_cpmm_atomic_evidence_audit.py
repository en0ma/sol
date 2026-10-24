import unittest
from arb.damm_cpmm_atomic_evidence_audit import accept
from arb.damm_cpmm_atomic_offline import DAMM,CPMM,DAMM_POOL,CPMM_POOL

def valid():
    return {"status":"SIGNED_ATOMIC_TWO_VENUE_AND_ROLLBACK_VERIFIED",
            "damm_pool":DAMM_POOL,"cpmm_pool":CPMM_POOL,
            "signed_atomic_simulation_verified":True,
            "rollback_failure_case_verified":True,
            "intermediate_intra_transaction_consumption_verified":True,
            "instruction_order_verified":True,
            "failed_at_second_instruction_after_successful_first":True,
            "top_level_venue_events":[[DAMM,"invoke"],[DAMM,"success"],[CPMM,"invoke"],[CPMM,"success"]],
            "negative_top_level_venue_events":[[DAMM,"invoke"],[DAMM,"success"],[CPMM,"invoke"],[CPMM,"failed"]],
            "negative_error":"{'InstructionError': [1, {'Custom': 6005}]}",
            "negative_logs":["Program log: AnchorError ExceededSlippage 6005"],
            "initial_balances_base_units":[100000000,0,0],
            "positive_post_balances_base_units":[0,10246743,9742],
            "negative_persistent_balances_base_units":[100000000,0,0],
            "terminal_input_spent_base_units":100000000,
            "terminal_output_received_base_units":9742,
            "first_leg_intermediate_received_base_units":10247743,
            "second_leg_intermediate_consumed_base_units":1000,
            "negative_simulation_post_accounts_available":False,
            "rollback_evidence_mode":"atomic_abort_instruction_1_and_persistence",
            "signed_packet_bytes":824,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

class EvidenceAcceptanceTests(unittest.TestCase):
    def test_coherent_complete_evidence_accepts_exactly_one_direction(self):
        output=accept(valid())
        self.assertEqual(output["verified_ordered_pair_count"],1)
        self.assertEqual(output["verified_pair"]["first_venue"],"meteora_damm_v2")
        self.assertEqual(output["verified_pair"]["second_venue"],"raydium_cpmm")
    def test_malformed_cpi_amount_rejected(self):
        row=valid()
        row["second_leg_intermediate_consumed_base_units"]=2000
        self.assertEqual(accept(row)["verified_ordered_pair_count"],0)
    def test_failure_on_first_leg_rejected(self):
        row=valid()
        row["negative_error"]="{'InstructionError': [0, {'Custom': 6005}]}"
        self.assertEqual(accept(row)["verified_ordered_pair_count"],0)
    def test_missing_rollback_rejected(self):
        row=valid()
        row["rollback_failure_case_verified"]=False
        self.assertEqual(accept(row)["verified_ordered_pair_count"],0)
    def test_synthetic_incomplete_artifact_rejected(self):
        self.assertEqual(accept({"status":"SIGNED_ATOMIC_TWO_VENUE_AND_ROLLBACK_VERIFIED"})["verified_ordered_pair_count"],0)

if __name__=="__main__":
    unittest.main()
