import io,json,unittest
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
