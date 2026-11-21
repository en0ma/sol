import unittest
from arb.venue_quote_adapter import quote
from arb.meteora_dlmm_bin_quote import Q
class Tests(unittest.TestCase):
 def test_multi_bin_venue_owned_quote(self):
  s={"token_x_mint":"X","token_y_mint":"Y","active_id":10,"snapshot_slot":33}
  e={"source_authenticated":True,"bin_state_authenticated":True,
     "effective_dynamic_fee_authenticated":True,"bin_snapshot_slot":33,
     "fee_snapshot_slot":33,"bin_array_pda_authenticated":True,
     "total_fee_rate":0,"authenticated_directional_bins":[
       {"bin_id":10,"price_q64":Q,"amount_x":100,"amount_y":100},
       {"bin_id":9,"price_q64":Q,"amount_x":200,"amount_y":200}]}
  x=quote("meteora_dlmm",s,"X",150,evidence=e)
  self.assertEqual(x["amount_out"],150)
  self.assertEqual(len(x["venue_quote"]["bins_traversed"]),2)
  self.assertFalse(x["protocol_exact_verified"])
  e["bin_array_pda_authenticated"]=False
  with self.assertRaises(ValueError):quote("meteora_dlmm",s,"X",150,evidence=e)
if __name__=="__main__":unittest.main()
