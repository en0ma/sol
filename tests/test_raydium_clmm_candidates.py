import unittest
from unittest.mock import patch
from arb.raydium_clmm_candidates import probe
class ClmmFixtureTests(unittest.TestCase):
    @patch("arb.raydium_clmm_candidates.call",return_value={"value":None})
    def test_missing_pool_not_tradable(self,call):
        out=probe("rpc",[{"address":"61R1ndXxvsWXXkWSyNkCxnzwd3zUNB8Q2ibmkiLPC8ht"}])
        self.assertEqual(out["status"],"UNVERIFIED")
        self.assertFalse(out["results"][0]["pool_verified"])
        self.assertFalse(out["results"][0]["swap_executed"])
