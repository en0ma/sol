import unittest
from arb.venue_quote_adapter import quote_pumpswap_source_bound,quote
class Tests(unittest.TestCase):
 def test_fee_version_bound_to_pool_snapshot(self):
  s={"venue":"pumpswap","verified":True,"fee_verified_onchain":True,
     "effective_fee_verified":True,
     "global_config":{"effective_fee_verified":True,"sell_enabled":True,"buy_enabled":True},
     "base_reserve":1000000,"quote_vault_balance":2000000,
     "virtual_quote_reserves":100000,"protocol_fees_accrued":100,
     "creator_fees_accrued":20,"base_mint":"A","quote_mint":"B"}
  with self.assertRaises(ValueError):
   quote_pumpswap_source_bound(s,"A",1000,pool_slot=10,fee_slot=9,
      effective_total_fee_ppm=2500,fee_tier_provenance="SOURCE_DECODED_EFFECTIVE_TIER")
  with self.assertRaises(ValueError):
   quote_pumpswap_source_bound(s,"A",1000,pool_slot=10,fee_slot=10,
      effective_total_fee_ppm=2500,fee_tier_provenance="ASSUMED_FEE_TIER")
  v=quote_pumpswap_source_bound(s,"A",1000,pool_slot=10,fee_slot=10,
      effective_total_fee_ppm=2500,fee_tier_provenance="SOURCE_DECODED_EFFECTIVE_TIER")
  self.assertGreater(v["amount_out"],0)
  self.assertEqual(v["pool_and_fee_snapshot_slot"],10)
  self.assertFalse(v["protocol_exact_verified"])
 def test_dlmm_damm_not_quoted_from_raw_vaults(self):
  for venue in ("meteora_dlmm","meteora_damm_v2"):
   with self.assertRaises(ValueError):
    quote(venue,{"vault_base_units":[100,200]},"A",10,
          evidence={"source_authenticated":True})
if __name__=="__main__":unittest.main()
