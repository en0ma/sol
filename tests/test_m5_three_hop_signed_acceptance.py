import unittest
from unittest.mock import patch
from arb.m5_three_hop_signed_acceptance import assess,audit,PAIRS
class Tests(unittest.TestCase):
    def receipt(self):
        return {"route_venues":["raydium_cpmm","raydium_amm_v4","raydium_cpmm"],
                "legs":3,"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
                "signed_cpi_per_leg_verified":True,"rollback_failure_case_verified":True,
                "signed_atomic_simulation_verified":True,"actionable":False,
                "live_execution_approved":False,"broadcast":False,
                "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
                "quote_accuracy_verified":False,"source_snapshot_slot":None,
                "planned_inputs":[100,85,74],
                "cpi_hops":[{"hop":1,"account":"intermediate1","planned_input_base_units":85,"received_base_units":85,"consumed_base_units":85},
                            {"hop":2,"account":"intermediate2","planned_input_base_units":74,"received_base_units":74,"consumed_base_units":74}],
                "positive_post_balances_base_units":[0,0,0,60],
                "signed_packet_bytes":1100,"negative_error":"{'InstructionError': [2, 30]}",
                "route_pool_addresses":["p","q","p"],
                "route_mints":["A","B","A","B"]}
    def test_real_shape_accepts(self):
        self.assertEqual(assess(PAIRS[0],self.receipt())["status"],"VERIFIED_THREE_HOP_SIGNED_OFFLINE")
    def test_short_consumption_fails(self):
        r=self.receipt();r["cpi_hops"][1]["consumed_base_units"]=70
        self.assertEqual(assess(PAIRS[0],r)["status"],"UNVERIFIED")
    def test_rollback_required(self):
        r=self.receipt();r["rollback_failure_case_verified"]=False
        self.assertEqual(assess(PAIRS[0],r)["status"],"UNVERIFIED")
    def test_missing_files_fail_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(audit(d)["verified"],0)
if __name__=="__main__":unittest.main()
