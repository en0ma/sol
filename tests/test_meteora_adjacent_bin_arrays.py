import base64
import hashlib
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dlmm_bin_preflight import inspect_adjacent_bin_arrays, BIN_ARRAY_DISC
from arb.meteora_dlmm import PROGRAM

POOL=str(Pubkey.new_unique())

def account(index, pool=POOL):
    data=(BIN_ARRAY_DISC + index.to_bytes(8,"little",signed=True) +
          bytes(8) + bytes(Pubkey.from_string(pool)) + bytes(80))
    return {"owner":PROGRAM,"executable":False,
            "data":[base64.b64encode(data).decode(),"base64"]}

class AdjacentDlmmArraysTests(unittest.TestCase):
    @patch("arb.meteora_dlmm_bin_preflight.call")
    def test_authenticated_active_and_missing_neighbor(self,rpc):
        rpc.return_value={"value":[None,account(10),account(11)]}
        rows=inspect_adjacent_bin_arrays("http://127.0.0.1:8899",POOL,10)
        self.assertEqual([x["index"] for x in rows],[9,10,11])
        self.assertFalse(rows[0]["present"])
        self.assertTrue(rows[1]["authenticated"])
        self.assertTrue(rows[2]["authenticated"])
        self.assertEqual(rpc.call_args.args[1],"getMultipleAccounts")

    @patch("arb.meteora_dlmm_bin_preflight.call")
    def test_reject_wrong_parent_or_array_index(self,rpc):
        for wrong in (account(7),account(10,str(Pubkey.new_unique()))):
            rpc.return_value={"value":[None,wrong,None]}
            with self.assertRaisesRegex(ValueError,"index/parent mismatch"):
                inspect_adjacent_bin_arrays("http://127.0.0.1:8899",POOL,10)

    @patch("arb.meteora_dlmm_bin_preflight.call")
    def test_reject_incomplete_snapshot(self,rpc):
        rpc.return_value={"value":[None,account(10)]}
        with self.assertRaisesRegex(ValueError,"incomplete"):
            inspect_adjacent_bin_arrays("http://127.0.0.1:8899",POOL,10)
