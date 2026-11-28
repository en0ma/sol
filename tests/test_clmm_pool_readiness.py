import unittest
from unittest.mock import patch
from arb.clmm_pool_readiness import report
class ClmmReadinessTests(unittest.TestCase):
    def test_missing_fixture_visible(self):
        out=report("rpc",[{"venue":"orca","address":"1"*32}])
        self.assertEqual(out["status"],"NOT_CONFIGURED")
        self.assertEqual(out["tick_ready_directions"],0)
    @patch("arb.clmm_pool_readiness.refresh")
    def test_invalid_pool_not_admitted(self,refresh):
        refresh.return_value={"verified_count":0,"rejected":[{"reason":"bad"}]}
        out=report("rpc",[{"venue":"raydium_clmm","address":"1"*32}])
        self.assertEqual(out["status"],"PARTIAL")
        self.assertFalse(out["swap_executed"])
        self.assertEqual(out["verified_pools"],0)
