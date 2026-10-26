import unittest
from unittest.mock import patch
from arb.cpmm_creator_fee_quote import calculate
from arb.fixture_config_quote_projection import quote_cpmm_creator_fee_source
class Tests(unittest.TestCase):
 def test_direction_and_creator_fee_mint_are_venue_owned(self):
  for side in (0,1):
   inp=calculate(100000,200000,10000,2500,1000,1,side)
   self.assertEqual(inp["creator_fee_mint_side"],"input" if side==0 else "output")
   self.assertGreater(inp["trade_fee_input_base_units"],0)
   self.assertFalse(inp["protocol_exact_verified"])
 @patch("arb.fixture_config_quote_projection.derive")
 def test_authenticated_pool_direction_quote(self,derive):
  derive.return_value={"snapshots":[{"venue":"raydium_cpmm","address":"p",
   "mints":["A","B"],"slot":7,"vault_base_units":[100000,200000],
   "native_trade_fee_ppm":2500,"native_creator_fee_ppm":1000,
   "creator_fee_enabled":True,"creator_fee_on":1}]}
  report=quote_cpmm_creator_fee_source({},observed_unix=1,
      leg={"pool":"p","input_mint":"A","output_mint":"B"},amount_in=1000)
  self.assertGreater(report["quote"]["amount_out"],0)
  self.assertEqual(report["venue_fee_detail"]["creator_fee_mint_side"],"input")
  with self.assertRaises(ValueError):
   quote_cpmm_creator_fee_source({},observed_unix=1,
      leg={"pool":"p","input_mint":"A","output_mint":"A"},amount_in=1000)
if __name__=="__main__":unittest.main()
