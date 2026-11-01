import base64
import hashlib
import unittest
from unittest.mock import patch
from arb.original_source_snapshot_audit import (inspect_original_source_batch,
    corroborate_original_source_batches,capture_original_source_two_observers)
class OriginalSnapshotTests(unittest.TestCase):
    def test_source_slot_owner_bytes_and_digest(self):
        raw=b"actual account bytes"
        encoded=base64.b64encode(raw).decode()
        ids=[{"address":"a"*44,"owner":"program","sha256":hashlib.sha256(raw).hexdigest()}]
        snap={"context":{"slot":120},"value":[{"owner":"program","executable":False,
               "data":[encoded,"base64"]}]}
        r=inspect_original_source_batch(snap,ids,required_slot=100)
        self.assertEqual(r["source_slot"],120)
        self.assertFalse(r["upstream_rpc_operator_trust_independently_proven"])
        for bad in ([{**ids[0],"owner":"forgery"}],
                    [{**ids[0],"sha256":"0"*64}]):
            with self.assertRaises(ValueError):
                inspect_original_source_batch(snap,bad)
        with self.assertRaises(ValueError):
            inspect_original_source_batch(snap,ids,required_slot=121)

    def test_two_observer_original_bytes_require_same_slot_and_content(self):
        raw=b"verified bytes at exact snapshot"
        ids=[{"address":"a"*44,"owner":"program",
              "sha256":hashlib.sha256(raw).hexdigest()}]
        account={"owner":"program","executable":False,
                 "data":[base64.b64encode(raw).decode(),"base64"]}
        snap={"context":{"slot":200},"value":[account]}
        result=corroborate_original_source_batches(snap,snap,ids)
        self.assertTrue(result["cross_observer_byte_agreement"])
        self.assertFalse(result["upstream_rpc_operator_trust_independently_proven"])
        self.assertFalse(result["solana_bank_hash_cryptographically_verified"])
        with self.assertRaises(ValueError):
            corroborate_original_source_batches(
                snap,{"context":{"slot":201},"value":[account]},ids)
        changed={"context":{"slot":200},"value":[
            {**account,"data":[base64.b64encode(b"changed").decode(),"base64"]}]}
        with self.assertRaises(ValueError):
            corroborate_original_source_batches(snap,changed,ids)
    def test_same_bytes_but_different_lamport_state_rejected(self):
        raw=b"same onchain data"
        account={"owner":"program","executable":False,
                 "data":[base64.b64encode(raw).decode(),"base64"],
                 "lamports":100,"rentEpoch":4}
        ids=[{"address":"a"*44,"owner":"program"}]
        left={"context":{"slot":300},"value":[account]}
        right={"context":{"slot":300},"value":[{**account,"lamports":101}]}
        with self.assertRaisesRegex(ValueError,"lamports or rent"):
            corroborate_original_source_batches(left,right,ids)
        right={"context":{"slot":300},"value":[{**account,"rentEpoch":5}]}
        with self.assertRaisesRegex(ValueError,"lamports or rent"):
            corroborate_original_source_batches(left,right,ids)
    def test_rpc_account_count_matches_official_maximum(self):
        # Solana getMultipleAccounts accepts at most 100 keys per request.
        too_many=[{"address":str(i),"owner":"program"} for i in range(101)]
        with self.assertRaises(ValueError):
            capture_original_source_two_observers(
                "https://rpc-a.example","https://rpc-b.example",too_many)
        with self.assertRaises(ValueError):
            inspect_original_source_batch(
                {"context":{"slot":1},"value":[]},too_many)

    def test_bounded_read_only_remote_corrob_and_adversarial_endpoints(self):
        raw=b"raw account original"
        ids=[{"address":"a"*44,"owner":"program",
              "sha256":hashlib.sha256(raw).hexdigest()}]
        account={"owner":"program","executable":False,
                 "data":[base64.b64encode(raw).decode(),"base64"]}
        snap={"context":{"slot":400},"value":[account]}
        with patch("arb.rpc.call",side_effect=[snap,snap]) as rpc:
            result=capture_original_source_two_observers(
                "https://rpc-a.example","https://rpc-b.example",ids,
                required_slot=380)
        self.assertEqual(result["source_slot"],400)
        self.assertEqual(rpc.call_count,2)
        self.assertEqual(rpc.call_args_list[0].args[1],"getMultipleAccounts")
        self.assertEqual(rpc.call_args_list[1].args[2][1]["minContextSlot"],400)
        for left,right in [
            ("http://rpc-a.example","https://rpc-b.example"),
            ("https://rpc-a.example","https://rpc-a.example"),
            ("https://127.0.0.1","https://rpc-b.example"),
            ("https://user:pass@rpc-a.example","https://rpc-b.example")]:
            with self.assertRaises(ValueError):
                capture_original_source_two_observers(left,right,ids)
        with patch("arb.rpc.call",side_effect=[
            snap,{"context":{"slot":401},"value":[account]}]):
            with self.assertRaises(ValueError):
                capture_original_source_two_observers(
                    "https://rpc-a.example","https://rpc-b.example",ids)
if __name__=="__main__":unittest.main()
