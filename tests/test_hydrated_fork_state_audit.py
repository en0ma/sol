import base64,unittest
from unittest.mock import patch
from arb.source_snapshot_manifest import digest
from arb.hydrated_fork_state_audit import verify_hydrated_state
def fixture():
 v={"owner":"token","executable":False,"lamports":123,"data":[base64.b64encode(b"abc").decode(),"base64"]}
 a={"x":v}
 return {"accounts":a,"state_account_addresses":["x"],"state_account_count":1,
  "state_accounts_observed_slot":11,"state_account_manifest_sha256":digest(a,["x"],11)}
class Tests(unittest.TestCase):
 def test_matches_byte_exact_and_retains_provenance_limit(self):
  f=fixture()
  with patch("arb.hydrated_fork_state_audit.local_rpc_only"),patch(
   "arb.hydrated_fork_state_audit.call",return_value={"context":{"slot":99},"value":[f["accounts"]["x"]]}):
   r=verify_hydrated_state("http://127.0.0.1:8899",f)
  self.assertEqual(r["status"],"HYDRATED_FORK_ACCOUNT_BYTES_MATCH")
  self.assertEqual(r["fork_readback_slot"],99)
  self.assertFalse(r["source_mainnet_slot_independently_attested"])
 def test_mismatched_bytes_rejected(self):
  f=fixture();bad=dict(f["accounts"]["x"],data=["eHl6","base64"])
  with patch("arb.hydrated_fork_state_audit.local_rpc_only"),patch(
   "arb.hydrated_fork_state_audit.call",return_value={"context":{"slot":99},"value":[bad]}):
   with self.assertRaises(ValueError):verify_hydrated_state("http://127.0.0.1:8899",f)
 def test_invalid_batch_rejected(self):
  with patch("arb.hydrated_fork_state_audit.local_rpc_only"):
   with self.assertRaises(ValueError):verify_hydrated_state("http://127.0.0.1:8899",fixture(),batch_size=101)
if __name__=="__main__":unittest.main()
