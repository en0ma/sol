import unittest
from arb.meteora_dlmm_bin_quote import quote_bins,Q
class Tests(unittest.TestCase):
 def test_per_bin_fee_rate_applies_after_crossing(self):
  bins=[{"bin_id":10,"price_q64":Q,"amount_x":1000,"amount_y":100,
          "effective_fee_rate":0},
        {"bin_id":9,"price_q64":Q,"amount_x":1000,"amount_y":1000,
          "effective_fee_rate":100000000}]
  x=quote_bins(amount_in=200,swap_x_for_y=True,bins=bins,total_fee_rate=0)
  self.assertEqual(x["bins_traversed"][0]["fee_input_base_units"],0)
  self.assertGreater(x["bins_traversed"][1]["fee_input_base_units"],0)
  self.assertEqual(sum(i["gross_input_base_units"] for i in x["bins_traversed"]),200)
 def test_corrupt_per_bin_fee_fails(self):
  with self.assertRaises(ValueError):
   quote_bins(amount_in=100,swap_x_for_y=True,total_fee_rate=0,
    bins=[{"bin_id":1,"price_q64":Q,"amount_x":1000,
           "amount_y":1000,"effective_fee_rate":1000000000}])
if __name__=="__main__":unittest.main()
