import unittest
from arb.meteora_dlmm_bin_quote import quote_bins,Q
class Tests(unittest.TestCase):
 def test_crosses_directional_bins_with_full_input_accounting(self):
  bins=[{"bin_id":10,"price_q64":Q,"amount_x":1000,"amount_y":100},
        {"bin_id":9,"price_q64":Q,"amount_x":1000,"amount_y":500}]
  r=quote_bins(amount_in=250,swap_x_for_y=True,bins=bins,total_fee_rate=0)
  self.assertEqual(r["amount_out"],250)
  self.assertEqual(sum(b["gross_input_base_units"] for b in r["bins_traversed"]),250)
  self.assertEqual(len(r["bins_traversed"]),2)
 def test_insufficient_bins_cannot_partially_fill(self):
  with self.assertRaises(ValueError):
   quote_bins(amount_in=100,swap_x_for_y=True,total_fee_rate=0,
      bins=[{"bin_id":5,"price_q64":Q,"amount_x":1000,"amount_y":50}])
 def test_wrong_direction_rejected(self):
  with self.assertRaises(ValueError):
   quote_bins(amount_in=150,swap_x_for_y=True,total_fee_rate=0,
      bins=[{"bin_id":5,"price_q64":Q,"amount_x":1000,"amount_y":100},
            {"bin_id":6,"price_q64":Q,"amount_x":1000,"amount_y":100}])
if __name__=="__main__":unittest.main()
