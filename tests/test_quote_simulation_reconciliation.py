import unittest
from arb.quote_simulation_reconciliation import reconcile
ROUTE={"legs":[{"venue":"orca","pool":"pool-1","input_mint":"A","output_mint":"B"},
               {"venue":"raydium_cpmm","pool":"pool-2","input_mint":"B","output_mint":"A"}]}
QUOTES=[dict(ROUTE["legs"][0],amount_in=1000,amount_out=500,snapshot_slot=42),
        dict(ROUTE["legs"][1],amount_in=500,amount_out=1080,snapshot_slot=42)]
def receipt():
    return {"first_venue":"orca","second_venue":"raydium_cpmm",
        "signed_atomic_simulation_verified":True,"intermediate_intra_transaction_consumption_verified":True,
        "rollback_failure_case_verified":True,"instruction_order_verified":True,
        "failed_at_second_instruction_after_successful_first":True,
        "actionable":False,"live_execution_approved":False,"broadcast":False,
        "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
        "signed_transaction_verified":True,"transaction_signature":"sig",
        "signed_packet_bytes":800,"positive_top_level_venues":["orca","raydium_cpmm"],
        "negative_top_level_venues":["orca","raydium_cpmm"],
        "route_mints":["A","B","A"],"route_pool_addresses":["pool-1","pool-2"],
        "source_snapshot_slot":42,"initial_balances_base_units":[1000,0,0],
        "positive_post_balances_base_units":[0,0,1080],
        "negative_persistent_balances_base_units":[1000,0,0],
        "first_leg_intermediate_received_base_units":500,
        "second_leg_intermediate_consumed_base_units":500,
        "positive_error":"None","status":"SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED",
        "negative_error":"InstructionError(1, Custom(1))","second_leg_failure_instruction_index":1,
        "positive_logs":["ok"],"negative_logs":["failed"]}
class Tests(unittest.TestCase):
 def test_exact_quote_vs_signed_delta_accepted_only_with_complete_proof(self):
    result=reconcile(ROUTE,QUOTES,receipt())
    self.assertEqual(result["status"],"RECONCILED_SIGNED_SIMULATION")
    self.assertFalse(result["profitability_confirmed"])
    self.assertFalse(result["actionable"])
 def test_self_certified_receipt_not_enough(self):
    r=receipt();r["signed_transaction_verified"]=False
    self.assertEqual(reconcile(ROUTE,QUOTES,r)["status"],"UNVERIFIED")
 def test_no_pool_or_slot_binding_cannot_pass(self):
    for field in ("route_pool_addresses","source_snapshot_slot"):
      r=receipt();r.pop(field)
      self.assertEqual(reconcile(ROUTE,QUOTES,r)["status"],"UNVERIFIED")
 def test_price_mismatch_fails(self):
    r=receipt();r["positive_post_balances_base_units"]=[0,0,900]
    self.assertEqual(reconcile(ROUTE,QUOTES,r)["status"],"UNVERIFIED")
 def test_input_mismatch_fails(self):
    q=[dict(x) for x in QUOTES];q[0]["amount_in"]=999
    self.assertEqual(reconcile(ROUTE,q,receipt())["status"],"UNVERIFIED")
 def test_invalid_tolerance_rejected(self):
    with self.assertRaises(ValueError):reconcile(ROUTE,QUOTES,receipt(),tolerance_bps=-1)
if __name__=="__main__":unittest.main()
