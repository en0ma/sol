import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.m5_focused_signed_experiment_batch import audit, PAIRS

class BatchTests(unittest.TestCase):
    def test_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            report = audit(Path(d), Path(d), observed_unix=1)
        self.assertEqual(report["attempted"], 2)
        self.assertEqual(report["independently_validated_quote_samples"], 0)
        self.assertIn("SOURCE_FIXTURE_MISSING", report["routes"][0]["reason_codes"])
        self.assertFalse(report["broadcast"])
    def test_dispatches_real_pairs_without_synthetic_proof(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/"fixtures").mkdir();(root/"receipts").mkdir()
            for pair in PAIRS:
                (root/"fixtures"/(pair+".json")).write_text('{"source":"fixture"}')
                (root/"receipts"/(pair+".json")).write_text('{"source":"receipt"}')
            with patch("arb.m5_focused_signed_experiment_batch.evaluate",return_value={
                "status":"DIAGNOSTIC_ONLY","reason_codes":["SOURCE_TO_EXECUTION_PROVENANCE_UNVERIFIED"],
                "signed_proof_status":"VERIFIED","provenance_status":"UNVERIFIED",
                "actionable":False,"live_execution_approved":False,"broadcast":False}) as f:
                report=audit(root/"fixtures",root/"receipts",observed_unix=123)
        self.assertEqual(f.call_count,2)
        self.assertEqual(report["signed_receipts_with_evidence"],2)
        self.assertEqual(report["independently_validated_quote_samples"],0)
    def test_malformed_json_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/"fixtures").mkdir();(root/"receipts").mkdir()
            name=PAIRS[0]+".json"
            (root/"fixtures"/name).write_text("{")
            (root/"receipts"/name).write_text("{}")
            result=audit(root/"fixtures",root/"receipts",observed_unix=12)
        self.assertTrue(result["routes"][0]["reason_codes"][0].startswith("EXPERIMENT_INPUT_OR_DECODER_BLOCKED"))
if __name__=="__main__": unittest.main()
