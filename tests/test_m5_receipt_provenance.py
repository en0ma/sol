import unittest
from pathlib import Path
from arb.next_ten_atomic_evidence import assess
class TestM5ReceiptProvenance(unittest.TestCase):
 def test_signed_runner_emits_pool_addresses_but_never_invents_slot(self):
    src=Path("arb/next_ten_signed_atomic_offline.py").read_text()
    self.assertIn('"route_pool_addresses":[legs[0][1],legs[1][1]]',src)
    self.assertIn('"source_snapshot_slot":None',src)
    self.assertIn('"paired_pool_observed_slot":fixture.get("paired_pool_observed_slot")',src)
    self.assertIn('"quote_accuracy_verified":False',src)
 def test_contextual_pool_pair_is_not_full_source_quote_attestation(self):
    src=Path("arb/next_ten_pair_fixture_export.py").read_text()
    self.assertIn('paired_pool_observed_slot',src)
    self.assertIn('state_accounts_observed_slot',src)
    self.assertIn('contextual companion accounts differ',src)
    self.assertIn('addresses,{"encoding":"base64","commitment":"confirmed"}',src)
    self.assertIn('"full_source_snapshot_slot":None',src)
    self.assertIn('paired contextual pool accounts differ',src)
 def test_incomplete_receipt_is_not_atomic_or_quote_evidence(self):
    report=assess(("orca","raydium_cpmm"),{"first_venue":"orca",
                   "second_venue":"raydium_cpmm",
                   "route_pool_addresses":["first",123],
                   "quote_accuracy_verified":True})
    self.assertEqual(report["status"],"UNVERIFIED")
    self.assertTrue(any("provenance" in reason for reason in report["failure_reasons"]))
    self.assertTrue(any("self-certified" in reason for reason in report["failure_reasons"]))
if __name__=="__main__":unittest.main()
