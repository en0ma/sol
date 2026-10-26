import unittest
from arb.venue_quote_adapter import quote
class Tests(unittest.TestCase):
 def test_dlmm_bin_quote_requires_matching_fee_state(self):
  s={"token_x_mint":"A","token_y_mint":"B","active_id":9,"snapshot_slot":10}
  e={"source_authenticated":True,"bin_state_authenticated":True,
      "effective_dynamic_fee_authenticated":True,
      "bin_snapshot_slot":10,"fee_snapshot_slot":10,"active_bin_id":9,
      "active_bin_price_q64":1<<64,"active_bin_amount_x":100000,
      "active_bin_amount_y":100000,"total_fee_rate":1000000}
  a=quote("meteora_dlmm",s,"A",1000,evidence=e)
  self.assertEqual(a["amount_out"],999)
  self.assertFalse(a["protocol_exact_verified"])
  e["fee_snapshot_slot"]=9
  with self.assertRaises(ValueError):quote("meteora_dlmm",s,"A",1000,evidence=e)
 def test_damm_quote_requires_curve_and_fee_config(self):
  s={"token_a_mint":"A","token_b_mint":"B","vault_base_units":[100000,200000],
     "snapshot_slot":10}
  e={"source_authenticated":True,"dynamic_fee_authenticated":True,
      "fee_collection_mode_authenticated":True,"fee_snapshot_slot":10,
      "range_curve_compatible":True,"effective_fee_ppm":2500,
      "fee_token_side":"output"}
  r=quote("meteora_damm_v2",s,"A",1000,evidence=e)
  self.assertGreater(r["amount_out"],0)
  self.assertFalse(r["protocol_exact_verified"])
  e["range_curve_compatible"]=False
  with self.assertRaises(ValueError):quote("meteora_damm_v2",s,"A",1000,evidence=e)
if __name__=="__main__":unittest.main()
