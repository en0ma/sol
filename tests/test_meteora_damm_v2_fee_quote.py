import unittest
from arb.meteora_damm_v2_quote import quote_exact_input
class Tests(unittest.TestCase):
 def test_fee_on_input_and_output_venues(self):
  base=dict(reserve_a=100000,reserve_b=200000,amount_in=1000,
            input_is_a=True,effective_fee_ppm=3000)
  inp=quote_exact_input(**base,fee_token_side="input")
  out=quote_exact_input(**base,fee_token_side="output")
  self.assertGreater(inp["fee_input_units"],0)
  self.assertEqual(inp["fee_output_units"],0)
  self.assertGreater(out["fee_output_units"],0)
  self.assertEqual(out["fee_input_units"],0)
  self.assertFalse(out["protocol_exact_verified"])
 def test_unknown_fee_side_rejected(self):
  with self.assertRaises(ValueError):
   quote_exact_input(100000,200000,1000,input_is_a=True,
       effective_fee_ppm=3000,fee_token_side="unknown")
if __name__=="__main__":unittest.main()
