import unittest
from unittest.mock import patch
from arb.m5_signed_message_fee_estimate import estimate_signed_message_fee
class Packet:
    signatures=[b"x"]
    message=b"signed-message"
    def verify(self):raise ValueError("invalid signature")
class Tests(unittest.TestCase):
    @patch("arb.m5_signed_message_fee_estimate.call")
    def test_invalid_signed_packet_never_queries_rpc(self,call):
        with self.assertRaisesRegex(ValueError,"invalid signature"):
            estimate_signed_message_fee("http://127.0.0.1:8899",Packet())
        call.assert_not_called()
if __name__=="__main__":unittest.main()
