import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO
from arb.rpc import call, RPCError, _retry_after


class RateLimitBackoffTests(unittest.TestCase):
    def throttle(self,retry_after=None):
        headers={} if retry_after is None else {"Retry-After":retry_after}
        return HTTPError("http://127.0.0.1:8899",429,"throttled",headers,BytesIO())

    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.random.uniform",return_value=0.1)
    @patch("arb.rpc.urlopen")
    def test_recovers_after_retry_after(self,urlopen,jitter,sleep):
        urlopen.side_effect=[self.throttle("1"),BytesIO(b'{"result": []}')]
        self.assertEqual(call("http://127.0.0.1:8899","getProgramAccounts",
                              retries=2,max_delay=3),[])
        self.assertEqual(urlopen.call_count,2)
        sleep.assert_called_once_with(1.0)

    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.urlopen")
    def test_aborts_when_server_wait_exceeds_budget(self,urlopen,sleep):
        urlopen.side_effect=self.throttle("60")
        with self.assertRaisesRegex(RPCError,"exceeds backoff budget"):
            call("http://127.0.0.1:8899","getProgramAccounts",max_delay=3)
        self.assertEqual(urlopen.call_count,1)
        sleep.assert_not_called()

    @patch("arb.rpc.time.sleep")
    @patch("arb.rpc.random.uniform",return_value=0)
    @patch("arb.rpc.urlopen")
    def test_retries_exhaust_without_silent_success(self,urlopen,jitter,sleep):
        urlopen.side_effect=self.throttle()
        with self.assertRaises(HTTPError):
            call("http://127.0.0.1:8899","getProgramAccounts",retries=2)
        self.assertEqual(urlopen.call_count,3)
        self.assertEqual(sleep.call_count,2)

    def test_invalid_retry_after_ignored(self):
        self.assertIsNone(_retry_after(self.throttle("garbage")))
