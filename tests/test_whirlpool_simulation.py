import unittest
from unittest.mock import patch
from arb.whirlpool_simulation import run, prepare_token_accounts

class SimulationTests(unittest.TestCase):
    @patch("arb.whirlpool_simulation.fetch_pool")
    def test_wrong_mints_blocked(self, fetch):
        fetch.return_value={"token_mint_a":"unsupported","token_mint_b":"unsupported2"}
        with self.assertRaises(ValueError):run("rpc","pool")

    @patch("arb.whirlpool_simulation.inspect_swap_requirements")
    @patch("arb.whirlpool_simulation.verify_oracle",return_value="oracle")
    @patch("arb.whirlpool_simulation.fetch_pool")
    def test_missing_arrays_block_without_funding(self,fetch,oracle,inspect):
        from arb.orca_whirlpool import SOL,USDC
        fetch.return_value={"token_mint_a":SOL,"token_mint_b":USDC,
                            "tick_spacing":8,"fee_tier_index_seed":8}
        inspect.return_value={"directions":{"a_to_b":{"available":False}}}
        self.assertEqual(run("rpc","pool")["status"],"BLOCKED_TICK_ARRAYS")
