import unittest
from arb.pool_readiness import inspect

class ReadinessTests(unittest.TestCase):
    def test_not_configured_is_not_ready(self):
        self.assertFalse(inspect({"status":"NOT_CONFIGURED","verifiedPools":0})["ready"])
    def test_valid_pool_is_ready(self):
        self.assertTrue(inspect({"status":"PASS","verifiedPools":1})["ready"])
    def test_false_report_rejected(self):
        with self.assertRaises(ValueError):
            inspect({"status":"PASS","verifiedPools":True})
    def test_fail_not_ready(self):
        self.assertFalse(inspect({"status":"FAIL","verifiedPools":0})["ready"])
