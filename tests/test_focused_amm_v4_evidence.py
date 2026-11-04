import tempfile,unittest
from arb.focused_amm_v4_evidence import audit,TARGET
class FocusedAuditTests(unittest.TestCase):
    def test_no_proof_for_missing_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            report=audit(d)
        self.assertEqual(len(TARGET),12)
        self.assertEqual(report["current_run_verified"],0)
        self.assertFalse(report["fresh_full_42_verified"])
        self.assertTrue(all(x["status"]=="UNVERIFIED" for x in report["routes"]))
if __name__=="__main__":unittest.main()
