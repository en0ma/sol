import tempfile
import unittest
from arb.m5_n_hop_signed_acceptance import assess,audit,PAIRS
class Tests(unittest.TestCase):
    def receipt(self,n):
        pairs=PAIRS[0]
        amounts=[100]+[50-i for i in range(n-1)]
        return {"legs":n,"route_venues":[pairs[i%2] for i in range(n)],
                "status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
                "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
                "quote_accuracy_verified":False,"source_snapshot_slot":None,
                "signed_cpi_per_leg_verified":True,"rollback_failure_case_verified":True,
                "signed_atomic_simulation_verified":True,
                "planned_inputs":amounts,
                "cpi_hops":[{"hop":i,"account":f"acct{i}","planned_input_base_units":amounts[i],
                             "received_base_units":amounts[i],"consumed_base_units":amounts[i]}
                            for i in range(1,n)],
                "positive_post_balances_base_units":[0]*n+[10],
                "route_pool_addresses":["pool0" if i%2==0 else "pool1" for i in range(n)],
                "route_mints":["A" if i%2==0 else "B" for i in range(n+1)],
                "signed_packet_bytes":500,"negative_error":"{'InstructionError': [4, 'Custom']}",
                "actionable":False,"live_execution_approved":False,"broadcast":False}
    def test_every_length(self):
        for n in (4,5,6):
            self.assertEqual(assess(PAIRS[0],n,self.receipt(n))["status"],"VERIFIED_SIGNED_N_HOP")
    def test_missing_intermediate_consumption(self):
        r=self.receipt(6);r["cpi_hops"][3]["consumed_base_units"]-=1
        self.assertEqual(assess(PAIRS[0],6,r)["status"],"UNVERIFIED")
    def test_missing_rollback(self):
        r=self.receipt(4);r["rollback_failure_case_verified"]=False
        self.assertEqual(assess(PAIRS[0],4,r)["status"],"UNVERIFIED")
    def test_no_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(audit(root)["verified"],0)
if __name__=="__main__":unittest.main()
