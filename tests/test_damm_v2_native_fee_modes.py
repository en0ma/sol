import unittest
from arb.meteora_damm_v2_quote import quote_collection_mode
class Tests(unittest.TestCase):
 def test_quote_only_charges_b_on_either_direction(self):
  a=quote_collection_mode(100000,200000,1000,input_is_a=True,
      effective_fee_ppm=3000,collection_mode="QUOTE_ONLY")
  b=quote_collection_mode(100000,200000,1000,input_is_a=False,
      effective_fee_ppm=3000,collection_mode="QUOTE_ONLY")
  self.assertEqual(a["fee_denomination"],"output")
  self.assertEqual(b["fee_denomination"],"input")
  self.assertEqual(a["fee_input_units"],0)
  self.assertEqual(b["fee_output_units"],0)
 def test_base_quote_collection_takes_output_side(self):
  for direction in (True,False):
   r=quote_collection_mode(100000,200000,1000,input_is_a=direction,
      effective_fee_ppm=2500,collection_mode="BASE_AND_QUOTE")
   self.assertEqual(r["fee_denomination"],"output")
 def test_unknown_mode_is_rejected(self):
  with self.assertRaises(ValueError):
   quote_collection_mode(100000,200000,1000,input_is_a=True,
      effective_fee_ppm=2500,collection_mode="UNKNOWN")
if __name__=="__main__":unittest.main()
