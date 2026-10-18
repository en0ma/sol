import io,json,unittest,os,tempfile
from unittest.mock import patch,MagicMock
from urllib.error import HTTPError
from arb.rpc import call,RPCError
class RPCRetryTests(unittest.TestCase):
    @patch("arb.rpc.random.uniform",return_value=0.001)
    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.urlopen")
    def test_http_429_retries(self,open,sleep,jitter):
        good=MagicMock()
        good.__enter__.return_value=io.BytesIO(b'{"result":{"ok":true}}')
        open.side_effect=[HTTPError("url",429,"Too Many Requests",None,None),good]
        self.assertEqual(call("http://rpc","getBalance",retries=1),{"ok":True})
        self.assertEqual(open.call_count,2)
        sleep.assert_called_once()
    @patch("arb.rpc.random.uniform",return_value=0.001)
    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.urlopen")
    def test_rpc_embedded_429_retries(self,open,sleep,jitter):
        def response(payload):
            item=MagicMock()
            item.__enter__.return_value=io.BytesIO(json.dumps(payload).encode())
            return item
        open.side_effect=[response({"error":{"message":"429 Too Many Requests"}}),
                          response({"result":17})]
        self.assertEqual(call("http://rpc","getSlot",retries=1),17)
        self.assertEqual(open.call_count,2)
    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.urlopen",side_effect=HTTPError("url",429,"limit",None,None))
    def test_exhaustion_raises(self,open,sleep):
        with self.assertRaises(HTTPError):call("http://rpc","getSlot",retries=2)
        self.assertEqual(open.call_count,3)
    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.urlopen")
    def test_non_rate_limit_no_retry(self,open,sleep):
        item=MagicMock()
        item.__enter__.return_value=io.BytesIO(b'{"error":{"code":-32602,"message":"invalid params"}}')
        open.return_value=item
        with self.assertRaises(RPCError):call("http://rpc","getSlot")
        self.assertEqual(open.call_count,1)
        sleep.assert_not_called()

class RPCPacingTests(unittest.TestCase):
    @patch("arb.rpc.urlopen")
    def test_pacing_is_opt_in_and_shared_by_calls(self,open):
        from arb.rpc import _pace_request
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/"pacing")
            with patch.dict(os.environ,{"SOLANA_RPC_MIN_INTERVAL_SECONDS":"0.01",
                                        "SOLANA_RPC_PACING_FILE":path}):
                _pace_request()
                first=float(Path(path).read_text())
                _pace_request()
                second=float(Path(path).read_text())
                self.assertGreaterEqual(second-first,0.009)
            open.assert_not_called()

    def test_invalid_interval_fails_closed(self):
        from arb.rpc import _pace_request
        with patch.dict(os.environ,{"SOLANA_RPC_MIN_INTERVAL_SECONDS":"not-a-number"}):
            with self.assertRaises(ValueError):
                _pace_request()
