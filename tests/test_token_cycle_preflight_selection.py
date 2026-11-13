import unittest
from unittest.mock import patch
from arb.token_cycle_tick_preflight import preflight
from arb.orca_whirlpool import SOL, USDC

OTHER="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
def candidate(verified, venue="orca", token=OTHER):
    return {"all_pools_onchain_verified":verified,
            "tokens":[SOL,token,SOL],
            "legs":[{"venue":venue,"pool":"p1","from":SOL,"to":token},
                    {"venue":venue,"pool":"p2","from":token,"to":SOL}]}

class PreflightSelectionOrderTests(unittest.TestCase):
    @patch("arb.token_cycle_tick_preflight.verify_oracle",return_value="oracle")
    @patch("arb.token_cycle_tick_preflight.inspect_swap_requirements")
    @patch("arb.token_cycle_tick_preflight.fetch_pool")
    def test_verified_orca_after_first_fifteen_is_examined(self,fetch,inspect,oracle):
        fetch.return_value={"token_mint_a":SOL,"token_mint_b":OTHER,
                            "tick_spacing":64,"fee_tier_index_seed":64}
        inspect.return_value={"directions":{
            "a_to_b":{"available":True,"required_starts":[1,2,3]},
            "b_to_a":{"available":True,"required_starts":[4,5,6]}}}
        candidates=[candidate(False) for _ in range(16)]
        candidates.extend([candidate(True),candidate(True,token=USDC,venue="raydium_clmm")])
        report=preflight("http://127.0.0.1:8899",{"cycles":candidates})
        self.assertEqual(report["eligible_orca_cycles_before_cap"],1)
        self.assertEqual(report["routes_checked"],1)
        self.assertEqual(report["routes_with_ready_ticks"],1)
        self.assertEqual(oracle.call_count,2)
