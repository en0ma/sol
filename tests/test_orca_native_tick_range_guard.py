import unittest
from unittest.mock import patch
from arb.fixture_all_venue_signed_quotes import quote_leg

class Tests(unittest.TestCase):
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 def test_whirlpool_out_of_range_tick_span_blocks_native_quote(self,decode):
  decode.return_value=[
   {"venue":"orca","address":"O","mints":["A","B"],
    "snapshot_slot":10,"decoded_pool_state":{"tick_spacing":64,"tick_current_index":443630}},
   {"venue":"raydium_cpmm","address":"C","mints":["B","D"],"snapshot_slot":10},
   {"venue":"raydium_amm_v4","address":"V","mints":["D","A"],"snapshot_slot":10}]
  fixture={"route_mints":["A","B","D","A"],"state_accounts_observed_slot":10}
  result=quote_leg(fixture,leg_index=0,amount_in=1000,observed_unix=1)
  self.assertEqual(result["quote_status"],"NATIVE_QUOTE_BLOCKED")
  self.assertIn("tick span outside native protocol bounds",result["reason"])
  self.assertFalse(result["protocol_exact_verified"])
if __name__=="__main__":unittest.main()
