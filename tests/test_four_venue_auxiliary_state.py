import unittest
from unittest.mock import patch
from arb.fixture_native_aux_inventory import inspect

class Tests(unittest.TestCase):
 @patch("arb.fixture_native_aux_inventory.verify",return_value=True)
 @patch("arb.fixture_native_aux_inventory.extract_pool_states")
 @patch("arb.fixture_pool_fundamentals.extract")
 def test_pump_net_reserves_decode_and_dynamic_fee_stays_blocked(self,extract,states,_verify):
  extract.return_value={"fundamentals":[{"venue":"pumpswap","address":"P",
     "vault_base_units":[1000,2000]}]}
  states.return_value=[{"venue":"pumpswap","address":"P","snapshot_slot":12,
    "decoded_pool_state":{"protocol_fees":13,"creator_fees":7,
      "virtual_quote_reserves":400}}]
  result=inspect({"state_accounts_observed_slot":12,
      "state_account_addresses":[],"accounts":{}})
  row=result["venues"][0]
  net=next(x for x in row["decoded_auxiliary"]
      if x["type"]=="pool_net_quote_liquidity")
  self.assertEqual(net["spendable_quote_base_units"],1980)
  self.assertEqual(net["priced_quote_base_units"],2400)
  self.assertFalse(row["fully_priced"])
  self.assertIn("source_authenticated_market_cap_fee_tier_and_fee_mode",row["missing"])
if __name__=="__main__":unittest.main()
