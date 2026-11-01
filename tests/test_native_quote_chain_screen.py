import unittest
from copy import deepcopy
from arb.native_quote_chain_screen import check_quote_chain, compare_quote_to_signed_spl, screen_fee_bounded_candidates

A="a"*44
B="b"*44
C="c"*44
def sample():
    route={"legs":[
        {"venue":"orca","pool":"p1","from":A,"to":B},
        {"venue":"raydium_cpmm","pool":"p2","from":B,"to":C},
        {"venue":"meteora_dlmm","pool":"p3","from":C,"to":A}]}
    quotes=[{"venue":leg["venue"],"pool":leg["pool"],
             "input_mint":leg["from"],"output_mint":leg["to"],
             "amount_in_base_units":n,"amount_out_base_units":out,
             "swap_fee_input_base_units":1,"source_slot":456,
             "native_quote_origin_independently_verified":True}
            for leg,n,out in zip(route["legs"],[100,95,93],[95,93,90])]
    return route,quotes

class QuoteChainTests(unittest.TestCase):
    def test_three_hop_exact_unit_loss_stays_diagnostic(self):
        route,quotes=sample()
        r=check_quote_chain(route,quotes,initial_base_units=100)
        self.assertEqual(r["gross_quoted_delta_base_units"],-10)
        self.assertFalse(r["net_profitability_verified"])
        self.assertFalse(r["actionable"])
        self.assertEqual(len(r["legs"]),3)

    def test_positive_gross_is_not_net_profitable(self):
        route,quotes=sample()
        quotes[-1]["amount_out_base_units"]=110
        r=check_quote_chain(route,quotes,initial_base_units=100)
        self.assertEqual(r["gross_quoted_delta_base_units"],10)
        self.assertFalse(r["actual_paid_network_fees_verified"])
        self.assertFalse(r["net_profitability_verified"])

    def test_quote_to_signed_per_leg_exact_parity_is_diagnostic_only(self):
        route,quotes=sample()
        native=check_quote_chain(route,quotes,initial_base_units=100)
        observed=[{"hop":i+1,"pool":leg["pool"],"venue":leg["venue"],
                   "input_mint":leg["from"],"output_mint":leg["to"],
                   "observed_input_base_units":quote["amount_in_base_units"],
                   "observed_output_base_units":quote["amount_out_base_units"]}
                  for i,(leg,quote) in enumerate(zip(route["legs"],quotes))]
        equal=compare_quote_to_signed_spl(native,observed)
        self.assertTrue(equal["all_legs_numerically_equal"])
        self.assertFalse(equal["net_profitability_verified"])
        self.assertFalse(equal["signed_receipt_independently_authenticated_here"])
        observed[1]["observed_output_base_units"]-=2
        nonmatching=compare_quote_to_signed_spl(native,observed)
        self.assertFalse(nonmatching["all_legs_numerically_equal"])
        observed[1]["input_mint"]=A
        with self.assertRaises(ValueError):
            compare_quote_to_signed_spl(native,observed)

    def test_fee_bound_ranking_remains_hypothetical_and_fail_closed(self):
        route,quotes=sample()
        quotes[-1]["amount_out_base_units"]=120
        candidate=check_quote_chain(route,quotes,initial_base_units=100)
        low=screen_fee_bounded_candidates([candidate],fee_upper_bound_base_units=25)
        self.assertEqual(low["candidates_above_assumed_bound"],0)
        ranked=screen_fee_bounded_candidates([candidate],fee_upper_bound_base_units=10)
        self.assertEqual(ranked["candidates_above_assumed_bound"],1)
        self.assertEqual(ranked["candidates"][0]["hypothetical_surplus_base_units"],10)
        self.assertFalse(ranked["net_profitability_verified"])
        self.assertFalse(ranked["fee_bound_independently_verified"])
        with self.assertRaises(ValueError):
            screen_fee_bounded_candidates([{**candidate,"net_profitability_verified":True}],
                                          fee_upper_bound_base_units=0)
        with self.assertRaises(ValueError):
            screen_fee_bounded_candidates([candidate],fee_upper_bound_base_units=True)

    def test_forgery_and_disconnected_leg_are_rejected(self):
        for mutate in (
            lambda route,quotes:quotes[1].update(input_mint=A),
            lambda route,quotes:quotes[1].update(amount_in_base_units=94),
            lambda route,quotes:quotes[1].update(source_slot=457),
            lambda route,quotes:quotes[1].update(native_quote_origin_independently_verified=False),
            lambda route,quotes:route["legs"][2].update(to=B),
            lambda route,quotes:quotes[0].update(swap_fee_input_base_units=-1),
            lambda route,quotes:quotes[0].update(amount_out_base_units=True),
            lambda route,quotes:quotes.pop(),
        ):
            route,quotes=sample()
            mutate(route,quotes)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                check_quote_chain(route,quotes,initial_base_units=100)

if __name__=="__main__":unittest.main()
