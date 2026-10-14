import unittest
from unittest.mock import patch
from arb.rpc import RPCError, call, inspect_account

class RPCUnitTests(unittest.TestCase):
    @patch("arb.rpc.call")
    def test_account_owner_check(self, mock_call):
        mock_call.return_value = {"value": {"owner": "program1", "executable": False, "lamports": 10, "space": 512}}
        self.assertTrue(inspect_account("http://localhost", "pool1", "program1")["owner_matches"])
        self.assertFalse(inspect_account("http://localhost", "pool1", "program2")["owner_matches"])

    @patch("arb.rpc.call", return_value={"value": None})
    def test_missing_account(self, _):
        self.assertFalse(inspect_account("http://localhost", "missing")["exists"])

    @patch("arb.rpc.urlopen")
    def test_rpc_error(self, mock_urlopen):
        from io import BytesIO
        mock_urlopen.return_value.__enter__.return_value = BytesIO(b'{"jsonrpc":"2.0","id":1,"error":{"code":-1}}')
        with self.assertRaises(RPCError):
            call("http://localhost", "getSlot")
