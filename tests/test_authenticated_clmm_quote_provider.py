import unittest
from arb.authenticated_quote_provider import from_snapshot
Q=1<<64
S={"venue":"raydium_clmm","address":"clmm-pool","mints":["A","B"],
   "token_mint_0":"A","token_mint_1":"B","sqrt_price_x64":Q,
   "liquidity":1000000,
   "next_initialized_sqrt_by_input_mint":{"A":Q-(Q//10),"B":Q+(Q//10)},
   "max_within_tick_input_by_mint":{"A":10000,"B":10000},
   "tick_boundary_authenticated":True,"trade_fee_authenticated":True,
   "trade_fee_ppm":2500,"slot":500,"observed_unix":1000,
   "verified":True,"source_authenticated":True,"account_owner_verified":True,
   "snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL"}
class TestCLMMContract(unittest.TestCase):
 def test_both_directional_exact_input_quotes(self):
    q,_=from_snapshot([S],now=1001)
    for a,b in [("A","B"),("B","A")]:
      out=q({"venue":"raydium_clmm","pool":"clmm-pool","input_mint":a,"output_mint":b},100)
      self.assertGreater(out["amount_out"],0)
      self.assertEqual(out["snapshot_slot"],500)
      self.assertIn("WITHIN_TICK",out["quote_model"])
 def test_missing_authenticated_tick_boundary_rejected(self):
    q,_=from_snapshot([dict(S,tick_boundary_authenticated=False)],now=1001)
    with self.assertRaisesRegex(ValueError,"authenticated"):
      q({"venue":"raydium_clmm","pool":"clmm-pool","input_mint":"A","output_mint":"B"},100)
 def test_cross_tick_rejected_without_extrapolation(self):
    q,_=from_snapshot([S],now=1001)
    with self.assertRaisesRegex(ValueError,"crosses initialized tick"):
      q({"venue":"raydium_clmm","pool":"clmm-pool","input_mint":"A","output_mint":"B"},200000)
 def test_wrong_orientation_rejected(self):
    q,_=from_snapshot([dict(S,token_mint_0="B")],now=1001)
    with self.assertRaisesRegex(ValueError,"orientation"):
      q({"venue":"raydium_clmm","pool":"clmm-pool","input_mint":"A","output_mint":"B"},100)
 def test_insufficient_within_tick_depth_rejected(self):
    q,_=from_snapshot([dict(S,max_within_tick_input_by_mint={"A":10,"B":10})],now=1001)
    with self.assertRaisesRegex(ValueError,"insufficient liquidity"):
      q({"venue":"raydium_clmm","pool":"clmm-pool","input_mint":"A","output_mint":"B"},100)
if __name__=="__main__":unittest.main()
