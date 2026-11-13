import unittest
from arb.authenticated_quote_provider import from_snapshot
Q=1<<64
S={"venue":"orca","address":"pool","mints":["A","B"],"token_mint_a":"A",
"token_mint_b":"B","sqrt_price_x64":Q,"liquidity":1000000,
"fee_rate_hundredths_bps":2500,"lower_sqrt_x64":Q-Q//10,
"upper_sqrt_x64":Q+Q//10,"tick_bounds_authenticated":True,
"trade_fee_authenticated":True,"max_within_tick_input_by_mint":{"A":10000,"B":10000},
"slot":500,"observed_unix":1000,"verified":True,"source_authenticated":True,
"account_owner_verified":True,"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL"}
class OrcaQuoteTests(unittest.TestCase):
 def test_both_directions_use_actual_math(self):
    q,_=from_snapshot([S],now=1001)
    for a,b in (("A","B"),("B","A")):
      result=q({"venue":"orca","pool":"pool","input_mint":a,"output_mint":b},100)
      self.assertGreater(result["amount_out"],0)
      self.assertEqual(result["snapshot_slot"],500)
      self.assertIn("WITHIN_TICK",result["quote_model"])
 def test_unverified_bound_refused(self):
    q,_=from_snapshot([dict(S,tick_bounds_authenticated=False)],now=1001)
    with self.assertRaisesRegex(ValueError,"authenticated"):
      q({"venue":"orca","pool":"pool","input_mint":"A","output_mint":"B"},100)
 def test_cross_tick_refused(self):
    q,_=from_snapshot([S],now=1001)
    with self.assertRaisesRegex(ValueError,"tick boundary"):
      q({"venue":"orca","pool":"pool","input_mint":"A","output_mint":"B"},200000)
 def test_depth_and_orientation_guards(self):
    for replacement,error in (({"max_within_tick_input_by_mint":{"A":1,"B":1}},"insufficient liquidity"),
                              ({"token_mint_a":"B"},"orientation")):
      q,_=from_snapshot([dict(S,**replacement)],now=1001)
      with self.assertRaisesRegex(ValueError,error):
        q({"venue":"orca","pool":"pool","input_mint":"A","output_mint":"B"},100)
if __name__=="__main__":unittest.main()
