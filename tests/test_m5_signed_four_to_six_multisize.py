import unittest
from unittest.mock import patch
from arb.next_ten_signed_atomic_offline import run_four_to_six_size_sweep
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class SignedMultisizeSourceTests(unittest.TestCase):
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_tries_distinct_signed_sizes_even_when_first_fails(self,run):
        def signed(rpc,fixture,*,amount_in,program_cache):
            if amount_in==10:raise ValueError("first swap unfillable")
            return {"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
                "signed_atomic_simulation_verified":True,
                "rollback_failure_case_verified":True,
                "signed_cpi_per_leg_verified":True,
                "planned_inputs":[amount_in]*4,**SAFE}
        run.side_effect=signed
        report=run_four_to_six_size_sweep("http://127.0.0.1:8899",{},
            amounts=(10,100,1000))
        self.assertEqual(report["attempt_count"],3)
        self.assertEqual(report["atomic_and_rollback_receipt_count"],2)
        self.assertEqual(report["selected_receipt"]["planned_inputs"][0],100)
        self.assertEqual(run.call_count,3)
        self.assertFalse(report["broadcast"])
        self.assertEqual(report["independently_audited_receipt_count"],0)
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_requires_independent_cpi_and_rollback(self,run):
        run.return_value={"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
            "signed_atomic_simulation_verified":True,
            "rollback_failure_case_verified":False,
            "signed_cpi_per_leg_verified":True,**SAFE}
        report=run_four_to_six_size_sweep("http://127.0.0.1:8899",{},
            amounts=(100,))
        self.assertIsNone(report["selected_receipt"])
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_rejects_unsafe_signed_receipts(self,run):
        run.return_value={"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
            **{**SAFE,"broadcast":True}}
        with self.assertRaisesRegex(ValueError,"unsafe"):
            run_four_to_six_size_sweep("http://127.0.0.1:8899",{},amounts=(100,))
    def test_duplicate_and_large_size_sets_rejected(self):
        for amounts in ((100,100),(),tuple(range(1,10)),(0,100)):
            with self.assertRaises(ValueError):
                run_four_to_six_size_sweep("http://127.0.0.1:8899",{},
                    amounts=amounts)
if __name__=="__main__":unittest.main()
