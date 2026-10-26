import base64,unittest
from unittest.mock import patch
from arb.m5_signed_message_fee_estimate import estimate_signed_message_fee
class Message:
    def __bytes__(self):return b"exact-signed-message"
class Transaction:
    message=Message()
    signatures=[b"signed"]
class Tests(unittest.TestCase):
    @patch("arb.m5_signed_message_fee_estimate.call",return_value={"value":8000})
    def test_exact_signed_message_fee_estimate_never_paid(self,call):
        result=estimate_signed_message_fee("http://127.0.0.1:8899",Transaction())
        self.assertEqual(result["estimated_fee_lamports"],8000)
        self.assertFalse(result["paid_fee_verified"])
        self.assertFalse(result["broadcast"])
        self.assertEqual(call.call_args.args[1],"getFeeForMessage")
        self.assertEqual(base64.b64decode(call.call_args.args[2][0]),b"exact-signed-message")
    @patch("arb.m5_signed_message_fee_estimate.call",return_value={"result":{"value":23}})
    def test_nested_rpc_result_envelope(self,_):
        x=estimate_signed_message_fee("http://127.0.0.1:8899",Transaction())
        self.assertEqual(x["estimated_fee_lamports"],23)
    @patch("arb.m5_signed_message_fee_estimate.call",return_value={"value":None})
    def test_absent_fee_does_not_become_zero(self,_):
        self.assertEqual(estimate_signed_message_fee("http://127.0.0.1:8899",Transaction())["status"],
                         "FEE_ESTIMATE_UNAVAILABLE")
if __name__=="__main__":unittest.main()
