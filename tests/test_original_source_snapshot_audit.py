import base64
import hashlib
import unittest
from arb.original_source_snapshot_audit import inspect_original_source_batch
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
if __name__=="__main__":unittest.main()
