import unittest
from arb.token_cycle_readiness import assess
from arb.orca_whirlpool import SOL, USDC

OTHER="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

def route(venue,token=OTHER,verified=True):
    return {"tokens":[SOL,token,SOL],"all_pools_onchain_verified":verified,
            "legs":[{"venue":venue,"pool":"pool-1","from":SOL,"to":token},
                    {"venue":venue,"pool":"pool-2","from":token,"to":SOL}]}

class ReadinessTests(unittest.TestCase):
    def test_orca_only_is_builder_present_but_not_executable(self):
        result=assess({"cycles":[route("orca")]})
        self.assertEqual(result["by_stage"],{"BUILDERS_PRESENT_ASSEMBLER_MISSING":1})
        self.assertFalse(result["cycles"][0]["generic_atomic_route_assembler_ready"])
        self.assertFalse(result["cycles"][0]["simulation_verified"])
        self.assertFalse(result["actionable"])

    def test_unclassified_venue_is_missing_builder(self):
        result=assess({"cycles":[route("raydium_unclassified")]})
        self.assertEqual(result["cycles"][0]["stage"],"LEG_BUILDERS_MISSING")

    def test_unverified_and_open_routes_are_rejected(self):
        result=assess({"cycles":[route("orca",verified=False)]})
        self.assertEqual(result["cycles"][0]["stage"],"POOL_VERIFICATION_BLOCKED")
        with self.assertRaises(ValueError):
            assess({"cycles":[{"tokens":[SOL,USDC],
                               "legs":[{"venue":"orca","pool":"pool",
                                        "from":SOL,"to":USDC}]}]})
