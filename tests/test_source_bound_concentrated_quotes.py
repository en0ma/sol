import unittest
from arb.venue_quote_adapter import quote_concentrated_source_bound
class Tests(unittest.TestCase):
 def test_no_stale_ticks(self):
  for v in ("orca","raydium_clmm"):
   with self.assertRaises(ValueError):
    quote_concentrated_source_bound(v,{},"A",100,
       snapshot_slot=5,bounds_slot=6,fee_slot=5)
 def test_orca_requires_real_in_tick_trade(self):
  s={"token_mint_a":"A","token_mint_b":"B","liquidity":1000000,
     "sqrt_price_x64":1<<64,"fee_rate_hundredths_bps":3000}
  r=quote_concentrated_source_bound("orca",s,"A",1000,
    snapshot_slot=9,bounds_slot=9,
    lower_sqrt_x64=(1<<64)-10**17,upper_sqrt_x64=(1<<64)+10**17)
  self.assertGreater(r["amount_out"],0)
  self.assertTrue(r["tick_state_same_slot_checked"])
  self.assertFalse(r["protocol_exact_verified"])
 def test_clmm_fee_slot_must_match(self):
  with self.assertRaises(ValueError):
   quote_concentrated_source_bound("raydium_clmm",{},"A",100,
      snapshot_slot=10,bounds_slot=10,fee_slot=9)
if __name__=="__main__":unittest.main()
