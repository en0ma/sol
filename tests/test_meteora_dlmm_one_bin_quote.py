import unittest
from arb.meteora_dlmm_bin_quote import quote_one_bin,Q
class Tests(unittest.TestCase):
 def test_fixed_price_both_directions_and_fee(self):
  a=quote_one_bin(amount_in=1000,swap_x_for_y=True,price_q64=2*Q,
      bin_x=100000,bin_y=100000,total_fee_rate=1000000,active_bin_id=5,observed_bin_id=5)
  b=quote_one_bin(amount_in=1000,swap_x_for_y=False,price_q64=2*Q,
      bin_x=100000,bin_y=100000,total_fee_rate=1000000,active_bin_id=5,observed_bin_id=5)
  self.assertEqual(a["amount_out"],1998)
  self.assertEqual(b["amount_out"],499)
 def test_refuse_multi_bin_or_stale_active_bin(self):
  kwargs=dict(amount_in=1000,swap_x_for_y=True,price_q64=2*Q,
      bin_x=100000,bin_y=100,total_fee_rate=1000000,active_bin_id=5,observed_bin_id=5)
  with self.assertRaises(ValueError):quote_one_bin(**kwargs)
  kwargs["bin_y"]=100000;kwargs["observed_bin_id"]=4
  with self.assertRaises(ValueError):quote_one_bin(**kwargs)
if __name__=="__main__":unittest.main()
