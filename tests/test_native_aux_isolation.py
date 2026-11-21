import unittest
from unittest.mock import patch
from arb.fixture_native_aux_inventory import inspect_isolated
class Tests(unittest.TestCase):
 @patch("arb.fixture_native_aux_inventory.verify",return_value=True)
 @patch("arb.fixture_native_aux_inventory.extract_pool_states")
 @patch("arb.fixture_native_aux_inventory.inspect")
 def test_individual_pool_decode_failure_preserves_sibling(self,decode,pools,_verify):
  pools.return_value=[
   {"venue":"raydium_clmm","address":"CL","snapshot_slot":19},
   {"venue":"meteora_dlmm","address":"DL","snapshot_slot":19},
   {"venue":"pumpswap","address":"PU","snapshot_slot":19}]
  def source(_,*,pool_filter=None):
   if pool_filter=="DL":raise ValueError("unavailable native dynamic fee")
   return {"venues":[{"venue":"raydium_clmm" if pool_filter=="CL" else "pumpswap",
     "pool":pool_filter,"source_slot":19,
     "decoded_auxiliary":[],"missing":[],"fully_priced":False}]}
  decode.side_effect=source
  result=inspect_isolated({"state_accounts_observed_slot":19})
  self.assertEqual(len(result["venues"]),3)
  self.assertEqual(result["venues"][0]["pool"],"CL")
  self.assertEqual(result["venues"][1]["status"],"AUXILIARY_DECODE_BLOCKED")
  self.assertEqual(result["venues"][2]["pool"],"PU")
  self.assertFalse(result["full_native_fee_pricing_verified"])
if __name__=="__main__":unittest.main()
