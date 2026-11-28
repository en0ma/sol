import json
import os
import tempfile
import unittest
from unittest.mock import patch
from arb.pool_report import main

class ReportTests(unittest.TestCase):
    def run_report(self, pools):
        with tempfile.TemporaryDirectory() as directory:
            manifest = os.path.join(directory, "pools.json")
            report = os.path.join(directory, "report.json")
            with open(manifest, "w") as f:
                json.dump({"pools": pools}, f)
            with patch.dict(os.environ, {"WHIRLPOOL_MANIFEST":manifest,
                                          "POOL_VERIFICATION_REPORT":report}):
                exit_code = main()
            with open(report) as f:
                return exit_code, json.load(f)

    def test_empty_manifest_is_not_reported_as_verified(self):
        code, status = self.run_report([])
        self.assertEqual(code, 0)
        self.assertEqual(status["status"], "NOT_CONFIGURED")
        self.assertEqual(status["verifiedPools"], 0)

    @patch("arb.pool_report.verify")
    def test_verified_pool_report(self, verify):
        verify.return_value = [{"address":"verified-pool"}]
        code, status = self.run_report([{"address":"verified-pool"}])
        self.assertEqual(code,0)
        self.assertEqual(status["status"],"PASS")
        self.assertEqual(status["verifiedPools"],1)

    @patch("arb.pool_report.verify",side_effect=ValueError("invalid pool"))
    def test_invalid_pool_fails_ci(self, verify):
        code, status = self.run_report([{"address":"bad-pool"}])
        self.assertEqual(code,1)
        self.assertEqual(status["status"],"FAIL")
