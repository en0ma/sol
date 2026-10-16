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

    @patch("arb.orca_quote_probe.crossing_target", return_value=None)
    @patch("arb.orca_quote_probe.probe")
    @patch("arb.orca_quote_probe.json.load")
    def test_report_separates_pool_and_amount_coverage(self, load, probe_mock, crossing_mock):
        from arb.orca_quote_probe import main
        from unittest.mock import mock_open
        import io
        from contextlib import redirect_stdout
        load.return_value={"pools":[{"address":"sample-pool"}]}
        probe_mock.return_value={"status":"QUOTE_UNAVAILABLE","quote_verified":False}
        output=io.StringIO()
        with patch("builtins.open", mock_open()), redirect_stdout(output):
            self.assertEqual(main(),0)
        import json
        report=json.loads(output.getvalue())
        self.assertEqual(report["attempted_pools"],1)
        self.assertEqual(report["attempted_pool_sizes"],5)
        self.assertEqual(report["status"],"NO_COMPARABLE_QUOTE")
        self.assertEqual(report["exact_matches"],0)
        self.assertEqual(report["matched_tick_crossing_quotes"],0)
        self.assertEqual(report["unavailable_quotes"],5)
        self.assertEqual([call.args[2] if len(call.args)>2 else call.kwargs.get("amount")
                          for call in probe_mock.call_args_list], [100000,1000000,5000000,20000000,50000000])

    @patch("arb.orca_quote_probe.inspect")
    @patch("arb.orca_quote_probe.fetch_pool")
    def test_dynamic_crossing_target_is_bounded(self, fetch, inspect):
        from arb.orca_quote_probe import crossing_target
        from arb.orca_tick_math import sqrt_price_from_tick_index
        from arb.orca_whirlpool import SOL
        state={"token_mint_a":SOL,"token_mint_b":"USDC",
               "tick_current_index":1,"tick_spacing":1,
               "sqrt_price_x64":str(sqrt_price_from_tick_index(1)),
               "liquidity":str(10**12),"fee_rate_hundredths_bps":3000}
        fetch.return_value=state
        inspect.return_value={"pool_state":state,"arrays":[
            {"start_tick":0,"status":"FIXED_VALID",
             "ticks":[{"tick_index":0,"liquidity_net":"0"}]}]}
        target=crossing_target("http://127.0.0.1:8899","pool")
        self.assertIsInstance(target,int)
        self.assertGreater(target,1000)
        self.assertIsNone(crossing_target("http://127.0.0.1:8899","pool",
                                          max_amount=1000))
