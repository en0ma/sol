import unittest
from unittest.mock import patch
from arb.m5_source_signed_prefix_quote_parity import compare
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class SourceSignedPrefixParityTests(unittest.TestCase):
 def fixture(self):
  return {"state_accounts_observed_slot":200,"state_account_manifest_sha256":"manifest",
   "route_pool_addresses":["p0","p1","p2","p3"],
   "route_mints":["A","B","C","D","A"],**SAFE}
 def receipt(self):
  f=self.fixture()
  return {"state_accounts_observed_slot":200,"state_account_manifest_sha256":"manifest",
   "route_pool_addresses":f["route_pool_addresses"],"route_mints":f["route_mints"],
   "planned_inputs":[100,95,90,80],
   "signed_prefix_observations":[{"index":i,"venue":v,"pool":"p"+str(i),
       "amount_in":x,"observed_output":y,"compute_units":100}
       for i,(v,x,y) in enumerate((("orca",100,95),
           ("meteora_dlmm",95,90),("meteora_damm_v2",90,80)))],**SAFE}
 def rows(self):
  return [{"venue":v,"address":"p"+str(i)} for i,v in enumerate(
   ("orca","meteora_dlmm","meteora_damm_v2","pumpswap"))]
 @patch("arb.m5_source_signed_prefix_quote_parity.quote_leg")
 @patch("arb.m5_source_signed_prefix_quote_parity.extract_pool_states")
 def test_signed_source_comparison_keeps_accuracy_unverified(self,rows,quote):
  rows.return_value=self.rows()
  quote.side_effect=lambda f,*,leg_index,amount_in,observed_unix:{
   "venue":self.rows()[leg_index]["venue"],"pool":"p"+str(leg_index),
   "source_slot":200,"quote_status":"SOURCE_BOUND_INDICATIVE",
   "predicted_output_base_units":amount_in-5,**SAFE}
  result=compare(self.fixture(),self.receipt(),observed_unix=123)
  self.assertEqual(result["compared_prefix_count"],3)
  self.assertEqual(result["numeric_comparison_count"],3)
  self.assertFalse(result["quote_accuracy_verified"])
 @patch("arb.m5_source_signed_prefix_quote_parity.quote_leg")
 @patch("arb.m5_source_signed_prefix_quote_parity.extract_pool_states")
 def test_real_signed_atomic_terminal_compares_fourth_leg(self,rows,quote):
  rows.return_value=self.rows()
  r=self.receipt()
  r.update(status="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
     signed_atomic_simulation_verified=True,
     signed_cpi_per_leg_verified=True,
     rollback_failure_case_verified=True,
     positive_post_balances_base_units=[0,0,0,0,99],
     initial_balances_base_units=[100,0,0,0,0])
  quote.side_effect=lambda f,*,leg_index,amount_in,observed_unix:{
   "venue":self.rows()[leg_index]["venue"],"pool":"p"+str(leg_index),
   "source_slot":200,"quote_status":"SOURCE_BOUND_INDICATIVE",
   "predicted_output_base_units":99 if leg_index==3 else amount_in-5,**SAFE}
  result=compare(self.fixture(),r,observed_unix=123)
  self.assertEqual(result["compared_signed_legs"],4)
  self.assertEqual(result["signed_atomic_terminal_output_base_units"],99)
  self.assertEqual(result["signed_atomic_gross_delta_start_mint_base_units"],-1)
  self.assertEqual(result["numeric_comparison_count"],4)
  self.assertFalse(result["quote_accuracy_verified"])
  self.assertTrue(result["comparisons"][-1]["signed_atomic_terminal_post_account_authenticated"])
 @patch("arb.m5_source_signed_prefix_quote_parity.extract_pool_states")
 def test_claimed_signed_atomic_terminal_with_missing_account_rejected(self,rows):
  rows.return_value=self.rows()
  r=self.receipt()
  r.update(status="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
     signed_atomic_simulation_verified=True,
     signed_cpi_per_leg_verified=True,
     rollback_failure_case_verified=True,
     initial_balances_base_units=[100,0,0,0,0])
  with self.assertRaisesRegex(ValueError,"final balances"):
   compare(self.fixture(),r,observed_unix=123)
 @patch("arb.m5_source_signed_prefix_quote_parity.extract_pool_states")
 def test_source_replay_manifest_rejected(self,rows):
  rows.return_value=self.rows()
  fake=self.receipt();fake["state_account_manifest_sha256"]="other"
  with self.assertRaisesRegex(ValueError,"reconcile"):
   compare(self.fixture(),fake,observed_unix=123)
 @patch("arb.m5_source_signed_prefix_quote_parity.extract_pool_states")
 def test_intermediate_forgery_rejected(self,rows):
  rows.return_value=self.rows()
  fake=self.receipt();fake["signed_prefix_observations"][1]["observed_output"]=1
  with self.assertRaisesRegex(ValueError,"signed prefix"):
   compare(self.fixture(),fake,observed_unix=123)
 @patch("arb.m5_source_signed_prefix_quote_parity.quote_leg")
 @patch("arb.m5_source_signed_prefix_quote_parity.extract_pool_states")
 def test_scenarios_not_promoted_to_numeric_parity(self,rows,quote):
  rows.return_value=self.rows()
  quote.side_effect=lambda f,*,leg_index,amount_in,observed_unix:{
   "venue":self.rows()[leg_index]["venue"],"pool":"p"+str(leg_index),
   "source_slot":200,"quote_status":"NATIVE_QUOTE_MODELED_NOT_EXACT",**SAFE}
  result=compare(self.fixture(),self.receipt(),observed_unix=123)
  self.assertEqual(result["numeric_comparison_count"],0)
if __name__=="__main__":unittest.main()
