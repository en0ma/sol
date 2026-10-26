import unittest
from unittest.mock import patch
from arb.fixture_all_venue_signed_quotes import quote_leg,VENUES
class Tests(unittest.TestCase):
 def test_seven_distinct_supported_venues_registered(self):
  self.assertEqual(len(VENUES),7)
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 def test_missing_native_dynamic_state_blocks_without_quote(self,extract):
  for venue in ("raydium_clmm","meteora_dlmm","meteora_damm_v2","pumpswap"):
   extract.return_value=[{"venue":venue,"address":"POOL",
      "mints":["A","B"],"snapshot_slot":33,"decoded_pool_state":{}}]+[
      {"venue":"orca","address":"OTHER"+str(i),"mints":["X","Y"],
       "snapshot_slot":33,"decoded_pool_state":{}} for i in range(2)]
   f={"route_mints":["A","B","X","A"],"state_accounts_observed_slot":33}
   result=quote_leg(f,leg_index=0,amount_in=100,observed_unix=1)
   self.assertEqual(result["quote_status"],"NATIVE_QUOTE_BLOCKED")
   self.assertIsNone(result["predicted_output_base_units"])
   self.assertIn("MISSING_NATIVE_AUXILIARY_STATE",result["reason"])
if __name__=="__main__":unittest.main()
