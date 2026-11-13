import unittest
from unittest.mock import patch
from arb.third_leg_readiness import probe
class ThirdLegOwnerTests(unittest.TestCase):
    @patch("arb.third_leg_readiness.call")
    def test_unsupported_owner_reported(self,call):
        call.return_value={"value":{"owner":"unknown-program"}}
        x=probe("rpc","4c8jpn6sLMrZHMYNq6idFfMdLBWEqn1r1wFNtgsPqTwE")
        self.assertEqual(x["program_owner"],"unknown-program")
        self.assertIsNone(x["detected_venue"])
        self.assertFalse(x["route_closed"])
    @patch("arb.third_leg_readiness.refresh")
    @patch("arb.third_leg_readiness.call")
    def test_known_owner_rejects_wrong_mints(self,call,refresh):
        from arb.raydium_cpmm import PROGRAM
        call.return_value={"value":{"owner":PROGRAM}}
        refresh.return_value={"verified_count":0,"rejected":[{"reason":"mint mismatch"}]}
        x=probe("rpc","4c8jpn6sLMrZHMYNq6idFfMdLBWEqn1r1wFNtgsPqTwE")
        self.assertEqual(x["detected_venue"],"raydium_cpmm")
        self.assertEqual(x["status"],"UNVERIFIED")
