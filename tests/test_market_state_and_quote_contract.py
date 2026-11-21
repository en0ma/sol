import unittest
from arb.market_state_registry import normalize
from arb.venue_quote_contract import validate
POOL={"venue":"orca","address":"pool1","mints":["A","B"],"slot":500,
      "observed_unix":1000,"source_authenticated":True,"verified":True,
      "account_owner_verified":True,"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL"}
QUOTE={"venue":"orca","pool":"pool1","input_mint":"A","output_mint":"B",
       "amount_in":1000,"amount_out":950,"fee_input_units":3,
       "liquidity_input_units":100000,"price_impact_bps":4,"snapshot_slot":500,
       "observed_unix":1000,"source_authenticated":True,"quote_model":"whirlpool-exact-input"}
class Tests(unittest.TestCase):
 def test_valid_registry_and_quote(self):
    r=normalize([POOL],as_of_unix=1001)
    self.assertEqual(r["pool_count"],1)
    self.assertEqual(validate(QUOTE,POOL,requested_input=1000,now=1001)["status"],"VALIDATED_INDICATIVE_QUOTE")
 def test_registry_does_not_trust_unattested_api_hint(self):
    r=normalize([dict(POOL,account_owner_verified=False)],as_of_unix=1001)
    self.assertEqual(r["pool_count"],0)
 def test_registry_fails_stale_and_cross_slot(self):
    r=normalize([POOL,dict(POOL,address="pool2",slot=400)],as_of_unix=1001)
    self.assertEqual(r["pool_count"],1)
    self.assertEqual(normalize([dict(POOL,observed_unix=1)],as_of_unix=1001)["pool_count"],0)
 def test_quote_requires_snapshot_slot_and_fee_and_depth(self):
    for override in ({"snapshot_slot":499},{"fee_input_units":None},{"liquidity_input_units":999}):
       self.assertEqual(validate(dict(QUOTE,**override),POOL,requested_input=1000,now=1001)["status"],"UNASSESSABLE")
 def test_quote_rejects_spot_quote_without_model(self):
    self.assertEqual(validate(dict(QUOTE,quote_model=""),POOL,requested_input=1000,now=1001)["status"],"UNASSESSABLE")
if __name__=="__main__":unittest.main()
