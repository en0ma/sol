import unittest
from unittest.mock import patch
from arb.fixture_config_quote_projection import derive
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

class NativeFourToSixPoolProjectionTests(unittest.TestCase):
 def fixture(self,n=4):
  return {"fixture_kind":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE",
          "route_pool_addresses":["pool"+str(i) for i in range(n)],
          "state_accounts_observed_slot":77,**SAFE}
 def states(self,n):
  return [{"venue":"orca","address":"pool"+str(i),
           "mints":["A"+str(i),"A"+str(i+1)],
           "snapshot_slot":77,"decoded_pool_state":{}}
          for i in range(n)]
 def balances(self,n):
  return [{"venue":"orca","address":"pool"+str(i),
           "mints":["A"+str(i),"A"+str(i+1)],
           "snapshot_slot":77,"vault_base_units":[10**8,2*10**8]}
          for i in range(n)]
 @patch("arb.fixture_config_quote_projection.extract")
 @patch("arb.fixture_config_quote_projection.extract_pool_states")
 def test_actual_source_four_to_six_pool_inventory_is_projected(self,states,extract):
  for n in (4,5,6):
   states.return_value=self.states(n)
   extract.return_value={"fundamentals":self.balances(n)}
   result=derive(self.fixture(n),observed_unix=12)
   self.assertEqual(len(result["snapshots"]),n)
   self.assertEqual(len(result["blocked_or_indicative"]),n)
   self.assertFalse(result["full_seven_venue_pricing_verified"])
 @patch("arb.fixture_config_quote_projection.extract")
 @patch("arb.fixture_config_quote_projection.extract_pool_states")
 def test_mismatched_inventory_fails_before_any_price_model(self,states,extract):
  states.return_value=self.states(4)
  extract.return_value={"fundamentals":self.balances(3)}
  with self.assertRaisesRegex(ValueError,"size mismatch"):
   derive(self.fixture(4),observed_unix=12)
 @patch("arb.fixture_config_quote_projection.extract")
 @patch("arb.fixture_config_quote_projection.extract_pool_states")
 def test_duplicate_source_pools_rejected_even_if_account_order_valid(self,states,extract):
  fixture=self.fixture(4)
  fixture["route_pool_addresses"][3]="pool0"
  with self.assertRaisesRegex(ValueError,"source pool inventory"):
   derive(fixture,observed_unix=12)
if __name__=="__main__":unittest.main()
