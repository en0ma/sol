import unittest
from arb.fixture_quote_binding import bind
from arb.source_snapshot_manifest import digest
def make():
 a={"first":{"owner":"o","data":["AA==","base64"]},
    "second":{"owner":"o","data":["AQ==","base64"]}}
 f={"accounts":a,"state_account_addresses":["first","second"],
    "state_accounts_observed_slot":44,"first_pool":"first","second_pool":"second",
    "first_venue":"orca","second_venue":"raydium_cpmm",
    "route_mints":["A","B","A"],"state_account_count":2}
 f["state_account_manifest_sha256"]=digest(a,f["state_account_addresses"],44)
 r={"legs":[{"venue":"orca","pool":"first","input_mint":"A","output_mint":"B"},
            {"venue":"raydium_cpmm","pool":"second","input_mint":"B","output_mint":"A"}]}
 q=[dict(r["legs"][0],snapshot_slot=44,source_authenticated=True,amount_in=100,amount_out=50),
    dict(r["legs"][1],snapshot_slot=44,source_authenticated=True,amount_in=50,amount_out=101)]
 return f,r,q
class Tests(unittest.TestCase):
 def test_manifest_and_route_accepted_without_accuracy_promotion(self):
  f,r,q=make();x=bind(f,r,q)
  self.assertEqual(x["status"],"FIXTURE_QUOTE_IDENTITY_BOUND_ONLY")
  self.assertFalse(x["signed_execution_quote_accuracy_verified"])
 def test_mutation_and_bad_source_slot_blocked(self):
  f,r,q=make();f["accounts"]["first"]["owner"]="changed"
  with self.assertRaises(ValueError):bind(f,r,q)
  f,r,q=make();q[0]["snapshot_slot"]=43
  with self.assertRaises(ValueError):bind(f,r,q)
 def test_pool_identity_and_intermediate_amount_mismatch_blocked(self):
  f,r,q=make();q[0]["pool"]="other"
  with self.assertRaises(ValueError):bind(f,r,q)
  f,r,q=make();q[1]["amount_in"]=49
  with self.assertRaises(ValueError):bind(f,r,q)
 def test_invalid_route_mints_blocked(self):
  f,r,q=make();f["route_mints"]=["A","B","C"]
  with self.assertRaises(ValueError):bind(f,r,q)
if __name__=="__main__":unittest.main()
