import unittest
from unittest.mock import patch
from arb.third_leg_readiness import probe
class ThirdLegTests(unittest.TestCase):
    @patch("arb.third_leg_readiness.call",return_value={"value":None})
    def test_missing_candidate_never_admitted(self,call):
        out=probe("rpc","4c8jpn6sLMrZHMYNq6idFfMdLBWEqn1r1wFNtgsPqTwE")
        self.assertEqual(out["status"],"UNVERIFIED")
        self.assertFalse(out["route_closed"])
        self.assertFalse(out["swap_simulated"])
