import unittest
from arb.orca_multitick_quote import Q, quote_multitick, quote_from_decoded_arrays


class MultitickIndicativeTests(unittest.TestCase):
    def state(self):
        return {'token_mint_a': 'a', 'token_mint_b': 'b',
                'sqrt_price_x64': str(Q), 'liquidity': str(1000000000000),
                'fee_rate_hundredths_bps': 3000, 'tick_current_index': 15}

    def test_cross_and_partially_consume_next_tick_both_directions(self):
        for mint, target, net in [('a', Q - 1000000000000, 10000000000),
                                  ('b', Q + 1000000000000, -10000000000)]:
            with self.subTest(mint=mint):
                ticks = [{'tick_index': 10 if mint == 'a' else 20, 'sqrt_price_x64': target, 'liquidity_net': net},
                         {'tick_index': 0 if mint == 'a' else 30, 'sqrt_price_x64': target - 100000000000000 if mint == 'a' else target + 100000000000000, 'liquidity_net': 0}]
                q = quote_multitick(self.state(), mint, 1000000, ticks)
                self.assertEqual(q['ticks_crossed'], 1)
                self.assertEqual(q['steps'][0]['kind'], 'cross')
                self.assertEqual(q['steps'][1]['kind'], 'partial')
                self.assertGreater(q['estimated_output_base_units'], 0)
                self.assertFalse(q['actionable'])
                self.assertFalse(q['executable_quote'])

    def test_missing_tick_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing tick coverage'):
            quote_multitick(self.state(), 'b', 1000000,
                            [{'tick_index': 20, 'sqrt_price_x64': Q + 1000000000000, 'liquidity_net': 0}])

    def test_bad_order_and_liquidity_rejected(self):
        with self.assertRaises(ValueError):
            quote_multitick(self.state(), 'a', 100000,
                            [{'tick_index': 1, 'sqrt_price_x64': Q + 1, 'liquidity_net': 0}])
        with self.assertRaises(ValueError):
            quote_multitick(self.state(), 'b', 1000000,
                            [{'tick_index': 1, 'sqrt_price_x64': Q + 1000000000000,
                              'liquidity_net': -(10**12)}])

    def test_crossing_budget(self):
        with self.assertRaisesRegex(ValueError, 'crossing budget'):
            quote_multitick(self.state(), 'a', 1000000,
                            [{'tick_index': 10, 'sqrt_price_x64': Q - 1000000000000,
                              'liquidity_net': 0}], max_crossings=0)

    def test_reject_tick_index_reversal_despite_correct_prices(self):
        with self.assertRaisesRegex(ValueError, 'tick index'):
            quote_multitick(self.state(), 'a', 1000000,
                            [{'tick_index': 20, 'sqrt_price_x64': Q - 1000000000000,
                              'liquidity_net': 0}])

    def test_zero_crossings_allows_small_within_tick_quote(self):
        result = quote_multitick(self.state(), 'b', 10000,
                                 [{'tick_index': 20, 'sqrt_price_x64': Q + 100000000000000,
                                   'liquidity_net': 0}], max_crossings=0)
        self.assertEqual(result['ticks_crossed'], 0)
        self.assertEqual(result['steps'][0]['kind'], 'partial')

    def test_decoded_array_bridge_crosses_tick(self):
        state = self.state()
        state["tick_spacing"] = 1
        observed = [
            {"start_tick": 0, "status": "FIXED_VALID", "ticks": [
                {"tick_index": 10, "liquidity_net": "10000000000"},
                {"tick_index": 0, "liquidity_net": "0"}]}]
        def price(ix):
            return {10: Q - 1000000000000, 0: Q - 101000000000000}[ix]
        q = quote_from_decoded_arrays(state, "a", 1000000, observed, price)
        self.assertEqual(q["ticks_crossed"], 1)
        self.assertEqual(q["tick_arrays_examined"], 1)
        self.assertFalse(q["executable_quote"])

    def test_native_bridge_accepts_dynamic_initialized_array_with_same_liquidity(self):
        state=self.state()
        state["tick_spacing"]=1
        raw_ticks=[{"tick_index":10,"liquidity_net":"10000000000"},
                   {"tick_index":0,"liquidity_net":"0"}]
        def price(ix):
            return {10:Q-1000000000000,0:Q-101000000000000}[ix]
        fixed=quote_from_decoded_arrays(state,"a",1000000,
             [{"start_tick":0,"status":"FIXED_VALID","ticks":raw_ticks}],price)
        dynamic=quote_from_decoded_arrays(state,"a",1000000,
             [{"start_tick":0,"status":"DYNAMIC_VALID","ticks":raw_ticks}],price)
        self.assertEqual(fixed["estimated_output_base_units"],
                         dynamic["estimated_output_base_units"])
        self.assertEqual(fixed["ticks_crossed"],dynamic["ticks_crossed"])
        self.assertFalse(dynamic["executable_quote"])
    def test_decoded_array_bridge_rejects_missing_current_array(self):
        state = self.state()
        state["tick_spacing"] = 1
        observed = [{"start_tick": 88, "status": "FIXED_VALID", "ticks": [
            {"tick_index": 90, "liquidity_net": "0"}]}]
        with self.assertRaisesRegex(ValueError, "missing or unsupported"):
            quote_from_decoded_arrays(state, "a", 1000, observed, lambda _: Q-1)

    def test_decoded_array_bridge_rejects_bad_liquidity(self):
        state = self.state()
        state["tick_spacing"] = 1
        observed = [{"start_tick": 0, "status": "FIXED_VALID", "ticks": [
            {"tick_index": 10, "liquidity_net": "not-a-number"}]}]
        with self.assertRaisesRegex(ValueError, "invalid tick liquidity"):
            quote_from_decoded_arrays(state, "a", 1000, observed, lambda _: Q-1)

    def test_unused_missing_next_array_is_not_a_quote_blocker(self):
        from arb.orca_tick_math import sqrt_price_from_tick_index
        state = self.state()
        state["tick_spacing"] = 1
        state["tick_current_index"] = 1
        state["sqrt_price_x64"] = str(sqrt_price_from_tick_index(1))
        arrays = [
            {"start_tick": 0, "status": "FIXED_VALID",
             "ticks": [{"tick_index": 10, "liquidity_net": "0"}]},
            {"start_tick": 88, "status": "MISSING"}]
        result = quote_from_decoded_arrays(state, "b", 1000, arrays)
        self.assertEqual(result["ticks_crossed"], 0)
        self.assertEqual(result["first_unavailable_array_start"], 88)
        self.assertFalse(result["actionable"])

    def test_missing_next_array_blocks_trade_requiring_further_liquidity(self):
        from arb.orca_tick_math import sqrt_price_from_tick_index
        state = self.state()
        state["tick_spacing"] = 1
        state["tick_current_index"] = 1
        state["sqrt_price_x64"] = str(sqrt_price_from_tick_index(1))
        arrays = [
            {"start_tick": 0, "status": "FIXED_VALID",
             "ticks": [{"tick_index": 10, "liquidity_net": "0"}]},
            {"start_tick": 88, "status": "MISSING"}]
        with self.assertRaisesRegex(ValueError, "missing tick coverage"):
            quote_from_decoded_arrays(state, "b", 10000000000, arrays)

    def test_empty_verified_array_quotes_only_within_current_array(self):
        from arb.orca_tick_math import sqrt_price_from_tick_index
        state={**self.state(),"tick_spacing":1,
               "sqrt_price_x64":str(sqrt_price_from_tick_index(15))}
        arrays=[{"start_tick":0,"status":"FIXED_VALID","ticks":[]}]
        for mint in ("a","b"):
            with self.subTest(mint=mint):
                q=quote_from_decoded_arrays(state,mint,100000,arrays)
                self.assertEqual(q["ticks_crossed"],0)
                self.assertEqual(q["source"],"VERIFIED_CURRENT_ARRAY_NO_INITIALIZED_TICKS")
                self.assertGreater(q["estimated_output_base_units"],0)
                self.assertFalse(q["actionable"])
                self.assertFalse(q["executable_quote"])

    def test_empty_array_cannot_quote_across_its_boundary(self):
        from arb.orca_tick_math import sqrt_price_from_tick_index
        state={**self.state(),"tick_spacing":1,
               "sqrt_price_x64":str(sqrt_price_from_tick_index(15))}
        arrays=[{"start_tick":0,"status":"FIXED_VALID","ticks":[]}]
        with self.assertRaisesRegex(ValueError,"crossing budget exceeded"):
            quote_from_decoded_arrays(state,"a",100000000000,arrays)

    def test_missing_empty_array_is_never_assumed(self):
        state={**self.state(),"tick_spacing":1}
        with self.assertRaisesRegex(ValueError,"missing or unsupported"):
            quote_from_decoded_arrays(state,"a",100000,
                [{"start_tick":0,"status":"MISSING"}])

    def test_more_than_64_authenticated_ticks_uses_nearest_only(self):
        from arb.orca_tick_math import sqrt_price_from_tick_index
        state={**self.state(),"tick_spacing":1,"tick_current_index":1,
               "sqrt_price_x64":str(sqrt_price_from_tick_index(1))}
        arrays=[{"start_tick":0,"status":"FIXED_VALID",
                 "ticks":[{"tick_index":i,"liquidity_net":"0"} for i in range(2,88)]}]
        result=quote_from_decoded_arrays(state,"b",100,arrays)
        self.assertEqual(result["ticks_crossed"],0)
        self.assertGreater(result["estimated_output_base_units"],0)
        self.assertFalse(result["actionable"])
