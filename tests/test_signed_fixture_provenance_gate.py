import unittest
from arb.signed_fixture_provenance_gate import audit
from arb.source_snapshot_manifest import digest
def fixture():
 a={"a":{"data":["AA==","base64"],"owner":"x"}}
 return {"accounts":a,"state_account_addresses":["a"],"state_account_count":1,
  "state_accounts_observed_slot":42,"state_account_manifest_sha256":digest(a,["a"],42),
  "first_pool":"p","second_pool":"q","route_mints":["a","b","a"]}
class Tests(unittest.TestCase):
 def test_legacy_receipt_missing_execution_slot_blocked(self):
  f=fixture()
  r={"route_pool_addresses":["p","q"],"route_mints":["a","b","a"],
    "state_account_manifest_sha256":f["state_account_manifest_sha256"],
    "state_accounts_observed_slot":42,"source_snapshot_slot":None,
    "initial_balances_base_units":[500,0,0],
    "positive_post_balances_base_units":[400,0,90]}
  x=audit(f,r,quoted_first_input=100)
  self.assertEqual(x["status"],"UNVERIFIED")
  self.assertIn("signed receipt execution source slot unauthenticated",x["reasons"])
  self.assertFalse(x["signed_quote_accuracy_verified"])
 def test_matching_fields_not_attestation(self):
  f=fixture()
  r={"route_pool_addresses":["p","q"],"route_mints":["a","b","a"],
    "state_account_manifest_sha256":f["state_account_manifest_sha256"],
    "state_accounts_observed_slot":42,"source_snapshot_slot":42,
    "initial_balances_base_units":[500,0,0],
    "positive_post_balances_base_units":[400,0,90]}
  x=audit(f,r,quoted_first_input=100)
  self.assertEqual(x["status"],"UNVERIFIED")
  self.assertIn("hydrated fork readback evidence missing",x["reasons"])
  r["hydrated_fork_state_readback"]={"status":"HYDRATED_FORK_ACCOUNT_BYTES_MATCH",
    "captured_source_slot":42,"fork_readback_slot":98,"accounts_checked":1,
    "source_mainnet_slot_independently_attested":False}
  x=audit(f,r,quoted_first_input=100)
  self.assertEqual(x["status"],"PROVENANCE_FIELDS_CONSISTENT_NOT_INDEPENDENTLY_ATTESTED")
  self.assertFalse(x["same_fork_state_independently_attested"])
 def test_tampered_manifest_and_wrong_amount_rejected(self):
  f=fixture();f["state_account_count"]=2
  with self.assertRaises(ValueError):audit(f,{},quoted_first_input=100)
  f=fixture()
  self.assertEqual(audit(f,{},quoted_first_input=100)["status"],"UNVERIFIED")
if __name__=="__main__":unittest.main()
