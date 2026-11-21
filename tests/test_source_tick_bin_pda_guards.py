import unittest
from unittest.mock import patch
from arb.fixture_all_venue_signed_quotes import quote_leg

class Tests(unittest.TestCase):
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 @patch("arb.fixture_aux_fee_decoder.decode_native_config_fee")
 def test_clmm_unavailable_tick_arrays_fail_closed(self,fees,states):
  states.return_value=[
   {"venue":"raydium_clmm","address":"CL","mints":["A","B"],
    "snapshot_slot":4,"decoded_pool_state":{
      "token_mint_0":"A","token_mint_1":"B",
      "tick_spacing":10,"tick_current":0,"amm_config":"CFG"}},
   {"venue":"orca","address":"O","mints":["B","C"],"snapshot_slot":4},
   {"venue":"raydium_cpmm","address":"CP","mints":["C","A"],"snapshot_slot":4}]
  fees.return_value={"trade_fee_ppm":3000}
  result=quote_leg({"route_mints":["A","B","C","A"],
     "state_accounts_observed_slot":4,"state_account_addresses":[],
     "accounts":{}},leg_index=0,amount_in=1000,observed_unix=1)
  self.assertEqual(result["quote_status"],"NATIVE_QUOTE_BLOCKED")
  self.assertIn("initialized source ticks unavailable",result["reason"])
  self.assertFalse(result["protocol_exact_verified"])
if __name__=="__main__":unittest.main()
