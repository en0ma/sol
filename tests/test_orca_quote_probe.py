import unittest
from unittest.mock import patch
from arb.orca_quote_probe import probe


class OrcaQuoteProbeTests(unittest.TestCase):
    @patch("arb.orca_quote_probe.inspect")
    @patch("arb.orca_quote_probe.run")
    @patch("arb.orca_quote_probe.fetch_pool")
    def test_changed_pool_state_blocks_quote_comparison(self, fetch, run, inspect):
        fetch.return_value={"tick_current_index":10,"liquidity":"1000"}
        run.return_value={"swap_success":True,"direction":"a_to_b"}
        inspect.return_value={"pool_tick":10,
                              "pool_state":{"tick_current_index":10,"liquidity":"999"}}
        outcome=probe("http://127.0.0.1:8899","pool")
        self.assertEqual(outcome["status"],"POOL_STATE_CHANGED")
        self.assertFalse(outcome["quote_verified"])

    def test_nonlocal_rpc_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"loopback"):
            probe("https://api.mainnet-beta.solana.com","pool")
