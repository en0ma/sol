import unittest,base64
from unittest.mock import patch
from arb.clmm_v0 import load_table,ALT_PROGRAM
class V0TableTests(unittest.TestCase):
    @patch("arb.clmm_v0.call")
    def test_bad_owner_fails(self,call):
        call.return_value={"value":{"owner":"bad","data":["","base64"]}}
        with self.assertRaises(ValueError):load_table("rpc","1"*32)
    @patch("arb.clmm_v0.call")
    def test_malformed_table_fails(self,call):
        call.return_value={"value":{"owner":ALT_PROGRAM,"data":[base64.b64encode(bytes(56)).decode(),"base64"]}}
        with self.assertRaises(ValueError):load_table("rpc","1"*32)
